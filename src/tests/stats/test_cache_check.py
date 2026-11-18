"""Tests for obs_monitor.stats.cache_check and the summary version pin."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from obs_monitor.config import load_obs_spaces
from obs_monitor.io import read_ioda
from obs_monitor.stats import SUMMARY_VERSION, load_regions, read_summary, reduce_cycle, write_summary
from obs_monitor.stats import cache_check as cc
from obs_monitor.stats.regions import Domain

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ioda"))
from ioda_fixtures import write_adpsfc  # noqa: E402

CYCLE = datetime(2026, 9, 30, 18)

# ---------------------------------------------------------------------------
# The version pin
# ---------------------------------------------------------------------------

#: Fingerprint of reduce_cycle's output on a fixed synthetic file, per summary version.
#: If test_summary_version_pinned fails, the summary contents or numbers changed:
#:   1. bump SUMMARY_VERSION in stats/summary.py (cached summaries then get recomputed), and
#:   2. add the new version here with the fingerprint the failure message prints.
#: Never edit an existing entry.
PINNED = {
    1: "86279b5720479842",
}


def summary_fingerprint(ds) -> str:
    """Structure (variables, dims, dtypes, coords, attr names) and values (rounded) of a summary."""
    h = hashlib.sha256()
    for name in sorted(ds.variables):
        v = ds.variables[name]
        h.update(f"{name}|{v.dims}|{v.dtype}|".encode())
        values = np.asarray(v.values)
        if values.dtype.kind in "fiu":
            h.update(np.nan_to_num(np.round(values.astype("float64"), 3), nan=-9999.0).tobytes())
        else:
            h.update(str(values.tolist()).encode())
    h.update(str(sorted(k for k in ds.attrs if k != "source_path")).encode())
    return h.hexdigest()[:16]


def test_summary_version_pinned(tmp_path):
    path = tmp_path / f"diag_prepbufr_adpsfc_{CYCLE:%Y%m%d%H}.nc"
    write_adpsfc(path, cycle=CYCLE, n=500, seed=7)
    domains, grid = load_regions()
    ds = reduce_cycle(read_ioda(path, "stationPressure", obs_space="prepbufr_adpsfc"), CYCLE, domains, grid)
    got = summary_fingerprint(ds)
    assert SUMMARY_VERSION in PINNED, f"Add SUMMARY_VERSION {SUMMARY_VERSION} to PINNED with fingerprint {got}"
    assert got == PINNED[SUMMARY_VERSION], (
        f"reduce_cycle output changed (fingerprint {got}, pinned {PINNED[SUMMARY_VERSION]} for version "
        f"{SUMMARY_VERSION}). Bump SUMMARY_VERSION in stats/summary.py and add {{new version: '{got}'}} to "
        f"PINNED, so cached summaries made the old way are recomputed instead of mixed in.")


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------

@pytest.fixture
def setup(tmp_path):
    diag = tmp_path / f"diag_prepbufr_adpsfc_{CYCLE:%Y%m%d%H}.nc"
    write_adpsfc(diag, cycle=CYCLE, n=50)
    domains, grid = load_regions()
    obs = load_obs_spaces()["prepbufr_adpsfc"]
    ds = reduce_cycle(read_ioda(diag, "stationPressure", obs_space=obs.name), CYCLE, domains, grid)
    want = cc.expected(obs, "stationPressure", domains, grid, diag)
    cache = write_summary(ds, tmp_path / "summary.nc", want)
    return dict(diag=diag, domains=domains, grid=grid, obs=obs, want=want, cached=read_summary(cache), tmp=tmp_path)


def test_matching_summary_is_reused(setup):
    assert cc.check(setup["cached"], setup["want"]) is None


def test_version_mismatch(setup):
    newer = dataclasses.replace(setup["want"], version=SUMMARY_VERSION + 1)
    assert cc.check(setup["cached"], newer) == f"summary version {SUMMARY_VERSION}, current {SUMMARY_VERSION + 1}"


def test_config_mismatch(setup):
    other = dataclasses.replace(setup["want"], config_hash="0" * 16)
    assert cc.check(setup["cached"], other) == "obs-space or region config changed"


def test_diag_file_changed(setup):
    os.utime(setup["diag"], (1_000_000_000, 1_000_000_000))
    want = cc.expected(setup["obs"], "stationPressure", setup["domains"], setup["grid"], setup["diag"])
    assert cc.check(setup["cached"], want) == "diag file changed"


def test_no_diag_file_skips_source_check(setup):
    """Once the diag file is gone, a summary with matching version and config is all there is: use it."""
    os.utime(setup["diag"], (1_000_000_000, 1_000_000_000))
    want = cc.expected(setup["obs"], "stationPressure", setup["domains"], setup["grid"], None)
    assert cc.check(setup["cached"], want) is None


def test_same_file_elsewhere_still_matches(setup):
    """Only name, size and mtime count, so a re-extraction into another scratch folder matches."""
    other = setup["tmp"] / "elsewhere" / setup["diag"].name
    other.parent.mkdir()
    other.write_bytes(setup["diag"].read_bytes())
    st = setup["diag"].stat()
    os.utime(other, (st.st_atime, st.st_mtime))
    want = cc.expected(setup["obs"], "stationPressure", setup["domains"], setup["grid"], other)
    assert cc.check(setup["cached"], want) is None


@pytest.mark.parametrize("attrs, reason", [
    ({}, "made by an older obs-monitor (no cache key)"),
    ({cc.VERSION_ATTR: "x", cc.CONFIG_ATTR: "y"}, "unreadable summary version"),
])
def test_old_or_broken_summaries(setup, attrs, reason):
    ds = setup["cached"].copy()
    ds.attrs = {k: v for k, v in ds.attrs.items() if not k.startswith("obsmon_")} | attrs
    assert cc.check(ds, setup["want"]).startswith(reason)


def test_summary_without_source_needs_recompute_when_diag_present(setup):
    ds = setup["cached"].copy()
    for k in cc.SOURCE_ATTRS:
        ds.attrs.pop(k)
    assert cc.check(ds, setup["want"]) == "no diag file recorded"


# ---------------------------------------------------------------------------
# config_hash(): what counts as "the numbers would change"
# ---------------------------------------------------------------------------

def test_config_hash_changes_with_what_affects_numbers(setup):
    obs, d, g = setup["obs"], setup["domains"], setup["grid"]
    base = cc.config_hash(obs, "stationPressure", d, g)
    assert cc.config_hash(dataclasses.replace(obs, group_map={"obs": "ObsValueX"}), "stationPressure", d, g) != base
    assert cc.config_hash(dataclasses.replace(obs, channels=(1, 2)), "stationPressure", d, g) != base
    assert cc.config_hash(obs, "airTemperature", d, g) != base
    moved = [Domain(x.name, x.lat_min + (1 if x.name == "NH" else 0), x.lat_max, x.lon_min, x.lon_max) for x in d]
    assert cc.config_hash(obs, "stationPressure", moved, g) != base
    finer = dataclasses.replace(g, lat_edges=np.linspace(-90, 90, 145))
    assert cc.config_hash(obs, "stationPressure", d, finer) != base


def test_config_hash_ignores_figure_settings(setup):
    obs, d, g = setup["obs"], setup["domains"], setup["grid"]
    base = cc.config_hash(obs, "stationPressure", d, g)
    assert cc.config_hash(dataclasses.replace(obs, web_name="renamed", figures=()), "stationPressure", d, g) == base
