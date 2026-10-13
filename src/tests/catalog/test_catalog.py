"""
Tests for obs_monitor.io.catalog against synthetic COM trees.

Tarball contents are small dummy files: the catalog never opens diag files,
it only finds and extracts them (reading is tested in tests/ioda).
"""

from __future__ import annotations

import io
import tarfile
from datetime import datetime
from pathlib import Path

import pytest

from obs_monitor.io.catalog import (
    CatalogError,
    ComTarballLocator,
    GlobLocator,
    build_inventory,
)
from obs_monitor.io.timewindow import cycle_range

ATMOS = ["prepbufr_adpsfc", "prepbufr_adpupa", "prepbufr_sfcshp", "radiance_atms_n20"]


def _payload(obs_space: str, cycle: datetime) -> bytes:
    return f"{obs_space} {cycle:%Y%m%d%H}\n".encode() * 100


def make_com_tarball(comroot: Path, cycle: datetime, obs_spaces=ATMOS, component="atmos", run="gdas",
                     extra_members: dict[str, bytes] | None = None) -> Path:
    """Write {comroot}/{run}.YYYYMMDD/HH/analysis/{component}/{run}.tHHz.{component}_analysis.ioda_hofx.tar.gz"""
    d = comroot / f"{run}.{cycle:%Y%m%d}" / f"{cycle:%H}" / "analysis" / component
    d.mkdir(parents=True, exist_ok=True)
    tar_path = d / f"{run}.t{cycle:%H}z.{component}_analysis.ioda_hofx.tar.gz"
    members = {f"diag_{s}_{cycle:%Y%m%d%H}.nc": _payload(s, cycle) for s in obs_spaces}
    members.update(extra_members or {})
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


CYCLES = cycle_range("2026093000", "2026093018", 6)


@pytest.fixture
def com(tmp_path):
    comroot = tmp_path / "COMROOT" / "prjedi"
    for c in CYCLES:
        if c == CYCLES[1]:
            continue                                     # 06Z tarball missing entirely
        spaces = ATMOS if c != CYCLES[2] else ATMOS[:2]  # 12Z missing sfcshp and atms
        make_com_tarball(comroot, c, spaces)
    return comroot


# ---------------------------------------------------------------------------
# ComTarballLocator
# ---------------------------------------------------------------------------

class TestComTarballLocator:

    def test_tarball_path_matches_gw_layout(self, tmp_path):
        loc = ComTarballLocator(tmp_path / "c", tmp_path / "w", component="atmos")
        assert loc.tarball(datetime(2026, 9, 30, 18)) == (
            tmp_path / "c/gdas.20260930/18/analysis/atmos/gdas.t18z.atmos_analysis.ioda_hofx.tar.gz")

    def test_extracts_only_requested(self, com, tmp_path):
        work = tmp_path / "work"
        loc = ComTarballLocator(com, work, component="atmos")
        found = loc.locate(CYCLES[0], ["prepbufr_adpsfc", "radiance_atms_n20"])
        assert set(found) == {"prepbufr_adpsfc", "radiance_atms_n20"}
        assert found["prepbufr_adpsfc"] == work / "2026093000" / "diag_prepbufr_adpsfc_2026093000.nc"
        assert found["prepbufr_adpsfc"].read_bytes() == _payload("prepbufr_adpsfc", CYCLES[0])
        assert sorted(p.name for p in (work / "2026093000").iterdir()) == [
            "diag_prepbufr_adpsfc_2026093000.nc", "diag_radiance_atms_n20_2026093000.nc"]

    def test_all_available_when_none_requested(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        assert set(loc.locate(CYCLES[0])) == set(ATMOS)
        assert set(loc.locate(CYCLES[2])) == set(ATMOS[:2])

    def test_missing_tarball_and_member(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        assert loc.locate(CYCLES[1], ATMOS) == {}
        assert set(loc.locate(CYCLES[2], ATMOS)) == {"prepbufr_adpsfc", "prepbufr_adpupa"}

    def test_reuses_extracted_file(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        p = loc.locate(CYCLES[0], ["prepbufr_adpsfc"])["prepbufr_adpsfc"]
        mtime = p.stat().st_mtime_ns
        assert loc.locate(CYCLES[0], ["prepbufr_adpsfc"])["prepbufr_adpsfc"].stat().st_mtime_ns == mtime

    def test_re_extracts_truncated_file(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        p = loc.locate(CYCLES[0], ["prepbufr_adpsfc"])["prepbufr_adpsfc"]
        p.write_bytes(b"partial")
        loc.locate(CYCLES[0], ["prepbufr_adpsfc"])
        assert p.read_bytes() == _payload("prepbufr_adpsfc", CYCLES[0])

    def test_unsafe_members_never_written_outside_work_dir(self, tmp_path):
        comroot, work = tmp_path / "c", tmp_path / "w"
        c = CYCLES[0]
        evil = f"../../diag_prepbufr_adpsfc_{c:%Y%m%d%H}.nc"
        make_com_tarball(comroot, c, obs_spaces=[], extra_members={evil: b"evil"})
        found = ComTarballLocator(comroot, work, component="atmos").locate(c, ["prepbufr_adpsfc"])
        assert found == {}
        assert not (tmp_path / f"diag_prepbufr_adpsfc_{c:%Y%m%d%H}.nc").exists()

    def test_member_in_subdirectory_is_found(self, tmp_path):
        comroot, work = tmp_path / "c", tmp_path / "w"
        c = CYCLES[0]
        name = f"diag_prepbufr_adpsfc_{c:%Y%m%d%H}.nc"
        make_com_tarball(comroot, c, obs_spaces=[], extra_members={f"./diags/{name}": b"x"})
        found = ComTarballLocator(comroot, work, component="atmos").locate(c, ["prepbufr_adpsfc"])
        assert found["prepbufr_adpsfc"] == work / "2026093000" / name

    def test_corrupt_tarball_is_treated_as_missing(self, tmp_path, caplog):
        comroot, work = tmp_path / "c", tmp_path / "w"
        tar_path = make_com_tarball(comroot, CYCLES[0])
        tar_path.write_bytes(b"not a tarball")
        assert ComTarballLocator(comroot, work, component="atmos").locate(CYCLES[0], ATMOS) == {}
        assert "Could not read" in caplog.text

    def test_relative_paths_rejected(self, tmp_path):
        with pytest.raises(CatalogError, match="absolute"):
            ComTarballLocator("relative/com", tmp_path, component="atmos")
        with pytest.raises(CatalogError, match="absolute"):
            ComTarballLocator(tmp_path, "relative/work", component="atmos")

    def test_bad_member_template(self, tmp_path):
        with pytest.raises(CatalogError, match="must not contain '/'"):
            ComTarballLocator(tmp_path, tmp_path, component="atmos", member_template="x/{obs_space}_{cycle:%H}.nc")
        with pytest.raises(CatalogError, match="obs_space"):
            ComTarballLocator(tmp_path, tmp_path, component="atmos", member_template="diag_{cycle:%H}.nc")


# ---------------------------------------------------------------------------
# GlobLocator
# ---------------------------------------------------------------------------

class TestGlobLocator:

    @pytest.fixture
    def expt(self, tmp_path):
        root = tmp_path / "expt"
        for c in CYCLES[:2]:
            d = root / f"{c:%Y%m%d%H}"
            d.mkdir(parents=True)
            for s in ATMOS[:3]:
                (d / f"diag_{s}_{c:%Y%m%d%H}.nc").write_bytes(b"x")
        (root / f"{CYCLES[0]:%Y%m%d%H}" / "notes.txt").write_text("not a diag")
        return root

    def test_locate_named(self, expt):
        loc = GlobLocator(str(expt) + "/{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc")
        found = loc.locate(CYCLES[0], ["prepbufr_adpsfc", "radiance_atms_n20"])
        assert set(found) == {"prepbufr_adpsfc"}
        assert found["prepbufr_adpsfc"] == expt / "2026093000" / "diag_prepbufr_adpsfc_2026093000.nc"

    def test_locate_all(self, expt):
        loc = GlobLocator(str(expt) + "/{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc")
        assert set(loc.locate(CYCLES[0])) == set(ATMOS[:3])
        assert loc.locate(CYCLES[3]) == {}

    def test_template_validation(self, tmp_path):
        with pytest.raises(CatalogError, match="obs_space"):
            GlobLocator(str(tmp_path) + "/diag_{cycle:%Y%m%d%H}.nc")
        with pytest.raises(CatalogError, match="absolute"):
            GlobLocator("expt/diag_{obs_space}_{cycle:%Y%m%d%H}.nc")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class TestInventory:

    def test_coverage_and_missing(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        inv = build_inventory(loc, CYCLES, ATMOS)
        assert inv.found_cycles("prepbufr_adpsfc") == [CYCLES[0], CYCLES[2], CYCLES[3]]
        assert inv.missing_cycles("prepbufr_adpsfc") == [CYCLES[1]]
        assert inv.missing_cycles("radiance_atms_n20") == [CYCLES[1], CYCLES[2]]
        assert inv.coverage("prepbufr_adpsfc") == pytest.approx(0.75)
        assert inv.path("prepbufr_adpupa", CYCLES[1]) is None
        row = {r["obs_space"]: r for r in inv.summary()}["prepbufr_sfcshp"]
        assert row == {"obs_space": "prepbufr_sfcshp", "found": 2, "expected": 4,
                       "missing": ["2026093006", "2026093012"]}

    def test_tarball_read_once_per_cycle(self, com, tmp_path, monkeypatch):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        calls = []
        real_open = tarfile.open
        monkeypatch.setattr(tarfile, "open", lambda *a, **k: calls.append(a[0]) or real_open(*a, **k))
        build_inventory({s: loc for s in ATMOS}, CYCLES, ATMOS)
        assert len(calls) == 3                       # 3 tarballs exist; each opened once for all 4 obs spaces

    def test_missing_locator_raises(self, com, tmp_path):
        loc = ComTarballLocator(com, tmp_path / "work", component="atmos")
        with pytest.raises(CatalogError, match="No locator"):
            build_inventory({"prepbufr_adpsfc": loc}, CYCLES, ["prepbufr_adpsfc", "radiance_atms_n20"])
