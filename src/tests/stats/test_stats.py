"""Tests for obs_monitor.stats (regions, reduce_cycle, stack_cycles, cache)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

from obs_monitor.config import ConfigError
from obs_monitor.io import QC_MISSING, read_ioda
from obs_monitor.stats import (
    QC_CLASSES,
    Domain,
    load_regions,
    read_summary,
    reduce_cycle,
    stack_cycles,
    summary_path,
    write_summary,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ioda"))
from ioda_fixtures import write_adpsfc, write_atms  # noqa: E402

CYCLE = datetime(2026, 10, 1, 0)
DOMAINS, GRID = load_regions()


def conv_ds(ombg, qc_bg, lat, lon, oman=None, qc_an=None):
    data = {"obs": ("Location", np.asarray(ombg, float) + 1000.0),
            "ombg": ("Location", np.asarray(ombg, float)),
            "qc_bg": ("Location", np.asarray(qc_bg, np.int32))}
    if oman is not None:
        data["oman"] = ("Location", np.asarray(oman, float))
    if qc_an is not None:
        data["qc_an"] = ("Location", np.asarray(qc_an, np.int32))
    return xr.Dataset(data, coords={"latitude": ("Location", np.asarray(lat, float)),
                                    "longitude": ("Location", np.asarray(lon, float))},
                      attrs={"obs_space": "prepbufr_adpsfc", "variable": "stationPressure", "units": "Pa"})


def pick(s, var, qc, domain, channel=None):
    sel = {"qc_class": qc, "domain": domain}
    if channel is not None:
        sel["channel"] = channel
    return float(s[var].sel(sel))


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

class TestRegions:

    def test_shipped_regions(self):
        assert [d.name for d in DOMAINS] == ["SH", "NH", "CONUS", "Europe", "Africa", "Asia", "Global"]
        assert GRID.shape == (72, 144)
        # same bin centres as the old stat files' griddedBins
        assert GRID.lat_centers[0] == -88.75 and GRID.lon_centers[-1] == 178.75

    def test_domain_edges(self):
        nh = Domain("NH", 0, 90, -180, 180)
        lat = np.array([0.0, 90.0, -0.1, 45.0])
        lon = np.array([0.0, 180.0, 0.0, -180.0])
        assert nh.mask(lat, lon).tolist() == [True, True, False, True]

    def test_dateline_wrap(self):
        pac = Domain("Pacific", -10, 10, 170, -170)
        lon = np.array([175.0, -175.0, 0.0, 169.9])
        assert pac.mask(np.zeros(4), lon).tolist() == [True, True, False, False]

    def test_grid_index(self):
        lat = np.array([-90.0, 90.0, 0.0, np.nan])
        lon = np.array([-180.0, 180.0, 0.0, 0.0])
        idx = GRID.flat_index(lat, lon)
        assert idx[0] == 0
        assert idx[1] == 72 * 144 - 1
        assert idx[2] == 36 * 144 + 72
        assert idx[3] == -1

    @pytest.mark.parametrize("doc, match", [
        ({"domains": {"X": {"lat": [10, 0], "lon": [0, 1]}}, "grid": {"lat": [-90, 90, 2.5], "lon": [-180, 180, 2.5]}},
         "south < north"),
        ({"domains": {"X": {"lat": [0, 100], "lon": [0, 1]}}, "grid": {"lat": [-90, 90, 2.5], "lon": [-180, 180, 2.5]}},
         "within"),
        ({"domains": {"X": {"lat": [0, 10]}}, "grid": {"lat": [-90, 90, 2.5], "lon": [-180, 180, 2.5]}},
         "exactly 'lat' and 'lon'"),
        ({"domains": {"X": {"lat": [0, 10], "lon": [0, 1]}}, "grid": {"lat": [-90, 90, 7], "lon": [-180, 180, 2.5]}},
         "whole number"),
        ({"domains": {}}, "exactly the keys"),
    ])
    def test_invalid(self, tmp_path, doc, match):
        f = tmp_path / "regions.yaml"
        f.write_text(yaml.safe_dump(doc))
        with pytest.raises(ConfigError, match=match):
            load_regions(f)


# ---------------------------------------------------------------------------
# reduce_cycle
# ---------------------------------------------------------------------------

class TestReduceCycle:

    @pytest.fixture
    def summary(self):
        # NH points: ombg 1, 3 (assimilated), 10 (monitored), 100 (rejected, flag 12), NaN (missing)
        # SH point:  -2 (assimilated)
        ds = conv_ds(ombg=[1.0, 3.0, 10.0, 100.0, np.nan, -2.0],
                     qc_bg=[0, 0, 1, 12, 10, 0],
                     lat=[40.0, 40.0, 41.0, 60.0, 50.0, -30.0],
                     lon=[-100.0, -100.0, -100.0, 10.0, 10.0, 20.0])
        return reduce_cycle(ds, CYCLE, DOMAINS, GRID)

    def test_contract(self, summary):
        assert list(summary["qc_class"].values) == list(QC_CLASSES)
        assert summary["ombg_mean"].dims == ("qc_class", "domain")
        assert summary["ombg_gridded_mean"].dims == ("lat", "lon")
        assert summary["cycle"].values == np.datetime64(CYCLE, "ns")
        assert summary.attrs["obs_space"] == "prepbufr_adpsfc"
        assert "oman_mean" not in summary          # field absent in input -> skipped

    def test_counts_by_class(self, summary):
        assert pick(summary, "ombg_count", "assimilated", "NH") == 2
        assert pick(summary, "ombg_count", "monitored", "NH") == 1
        assert pick(summary, "ombg_count", "rejected", "NH") == 1     # missing (NaN) obs not counted
        assert pick(summary, "ombg_count", "all", "NH") == 4
        assert pick(summary, "ombg_count", "assimilated", "Global") == 3
        assert pick(summary, "ombg_count", "assimilated", "CONUS") == 2

    def test_stats(self, summary):
        assert pick(summary, "ombg_mean", "assimilated", "NH") == pytest.approx(2.0)
        assert pick(summary, "ombg_rms", "assimilated", "NH") == pytest.approx(np.sqrt(5.0))
        assert pick(summary, "ombg_std", "assimilated", "NH") == pytest.approx(1.0)
        assert pick(summary, "ombg_mean", "assimilated", "Global") == pytest.approx(2.0 / 3.0)
        assert pick(summary, "obs_mean", "assimilated", "SH") == pytest.approx(998.0)

    def test_empty_domain_is_nan_with_zero_count(self, summary):
        assert pick(summary, "ombg_count", "assimilated", "Asia") == 0
        assert np.isnan(pick(summary, "ombg_mean", "assimilated", "Asia"))

    def test_gridded_assimilated_only(self, summary):
        g = summary["ombg_gridded_mean"].sel(lat=40, lon=-100, method="nearest")
        assert float(g) == pytest.approx(2.0)
        assert int(summary["ombg_gridded_count"].sum()) == 3
        assert summary.attrs["gridded_qc"] == "assimilated"

    def test_oman_uses_final_qc(self):
        ds = conv_ds(ombg=[1.0, 2.0], qc_bg=[0, 0], lat=[10, 10], lon=[0, 0],
                     oman=[0.5, 0.7], qc_an=[0, 19])
        s = reduce_cycle(ds, CYCLE, DOMAINS, GRID)
        assert pick(s, "ombg_count", "assimilated", "NH") == 2
        assert pick(s, "oman_count", "assimilated", "NH") == 1
        assert pick(s, "oman_mean", "assimilated", "NH") == pytest.approx(0.5)

    def test_oman_falls_back_to_bg_qc(self):
        ds = conv_ds(ombg=[1.0, 2.0], qc_bg=[0, 12], lat=[10, 10], lon=[0, 0], oman=[0.5, 0.7])
        s = reduce_cycle(ds, CYCLE, DOMAINS, GRID)
        assert pick(s, "oman_count", "assimilated", "NH") == 1

    def test_bad_gridded_qc(self):
        ds = conv_ds(ombg=[1.0], qc_bg=[0], lat=[0], lon=[0])
        with pytest.raises(ValueError, match="gridded_qc"):
            reduce_cycle(ds, CYCLE, DOMAINS, GRID, gridded_qc="passed")

    def test_matches_brute_force_on_ioda_file(self, tmp_path):
        """Through the real reader: stats equal a plain numpy loop over the raw arrays."""
        path = tmp_path / "diag_prepbufr_adpsfc_2026100100.nc"
        write_adpsfc(path, cycle=CYCLE, n=400)
        ds = read_ioda(path, "stationPressure")
        s = reduce_cycle(ds, CYCLE, DOMAINS, GRID)
        lat, lon = ds["latitude"].values, ds["longitude"].values
        for d in DOMAINS:
            m = d.mask(lat, lon) & np.isfinite(ds["ombg"].values) & (ds["qc_bg"].values == 0)
            vals = ds["ombg"].values[m]
            assert pick(s, "ombg_count", "assimilated", d.name) == m.sum()
            if m.any():
                assert pick(s, "ombg_mean", "assimilated", d.name) == pytest.approx(vals.mean())
                assert pick(s, "ombg_rms", "assimilated", d.name) == pytest.approx(np.sqrt((vals ** 2).mean()))

    def test_radiance_channels(self, tmp_path):
        path = tmp_path / "diag_radiance_atms_n20_2026100100.nc"
        write_atms(path, cycle=CYCLE)
        ds = read_ioda(path, "brightnessTemperature", channels=[1, 7])
        s = reduce_cycle(ds, CYCLE, DOMAINS, GRID)
        assert s["ombg_mean"].dims == ("channel", "qc_class", "domain")
        assert s["ombg_gridded_mean"].dims == ("channel", "lat", "lon")
        assert list(s["channel"].values) == [1, 7]
        for ch in (1, 7):
            col = ds["ombg"].sel(channel=ch).values
            ok = np.isfinite(col) & (ds["qc_bg"].sel(channel=ch).values == 0)
            assert pick(s, "ombg_count", "assimilated", "Global", channel=ch) == ok.sum()

    def test_qc_missing_not_assimilated(self):
        ds = conv_ds(ombg=[1.0, 2.0], qc_bg=[0, QC_MISSING], lat=[10, 10], lon=[0, 0])
        s = reduce_cycle(ds, CYCLE, DOMAINS, GRID)
        assert pick(s, "ombg_count", "assimilated", "NH") == 1
        assert pick(s, "ombg_count", "rejected", "NH") == 0
        assert pick(s, "ombg_count", "all", "NH") == 2


# ---------------------------------------------------------------------------
# stack_cycles and cache
# ---------------------------------------------------------------------------

class TestStackAndCache:

    def one(self, cycle, value):
        ds = conv_ds(ombg=[value], qc_bg=[0], lat=[10], lon=[0])
        return reduce_cycle(ds, cycle, DOMAINS, GRID)

    def test_gaps_from_expected_cycles(self):
        cycles = [datetime(2026, 10, 1, h) for h in (0, 6, 12, 18)]
        summaries = {cycles[0]: self.one(cycles[0], 1.0), cycles[2]: self.one(cycles[2], 3.0)}
        st = stack_cycles(summaries, cycles)
        series = st["ombg_mean"].sel(qc_class="assimilated", domain="NH").values
        assert series[0] == 1.0 and series[2] == 3.0
        assert np.isnan(series[1]) and np.isnan(series[3])
        assert st.sizes["cycle"] == 4

    def test_nothing_present(self):
        assert stack_cycles({}, [CYCLE]) is None

    def test_cache_roundtrip(self, tmp_path):
        s = self.one(CYCLE, 2.5)
        p = summary_path(tmp_path, "prepbufr_adpsfc", "stationPressure", CYCLE)
        assert p.name == "summary_prepbufr_adpsfc_stationPressure_2026100100.nc"
        write_summary(s, p)
        back = read_summary(p)
        xr.testing.assert_allclose(back, s)
        assert back.attrs["variable"] == "stationPressure"
        assert not list(p.parent.glob(".*.tmp"))

    def test_cache_missing_or_corrupt(self, tmp_path):
        assert read_summary(tmp_path / "nope.nc") is None
        bad = tmp_path / "bad.nc"
        bad.write_text("not netcdf")
        assert read_summary(bad) is None
