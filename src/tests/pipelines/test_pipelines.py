"""Tests for obs_monitor.pipelines (run_window, operational, stage) and the workflow pieces around them."""

from __future__ import annotations

import json
import os
import sys
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Environment, FileSystemLoader

from obs_monitor.config import RunConfig
from obs_monitor.pipelines import run as runmod
from obs_monitor.pipelines import operational, stage
from obs_monitor.pipelines.run import STATUS_FILE, run_window

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ioda"))
from ioda_fixtures import write_adpsfc, write_snow  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CYCLES = [datetime(2026, 10, 11) + timedelta(hours=6 * i) for i in range(4)]
END = CYCLES[-1]
DIAG = "{root}/gdas.{c:%Y%m%d}/{c:%H}/analysis/atmos/diag_{o}_{c:%Y%m%d%H}.nc"


@pytest.fixture(autouse=True)
def no_coastlines():
    """Coastlines need a cartopy download; not available in CI."""
    with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda self, *a, **k: None):
        yield


def stage_diags(root: Path, obs_space="prepbufr_adpsfc", cycles=CYCLES, skip=()):
    for c in cycles:
        if c in skip:
            continue
        p = Path(DIAG.format(root=root, c=c, o=obs_space))
        p.parent.mkdir(parents=True, exist_ok=True)
        write_adpsfc(p, cycle=c, n=300)


def run_config(tmp_path, obs_spaces=("prepbufr_adpsfc",)):
    return RunConfig.from_dict({
        "cycles": {"end": f"{END:%Y%m%d%H}", "n_cycles": len(CYCLES)},
        "source": {"type": "glob",
                   "template": str(tmp_path / "data") + "/gdas.{cycle:%Y%m%d}/{cycle:%H}/analysis/{component}/"
                   "diag_{obs_space}_{cycle:%Y%m%d%H}.nc"},
        "obs_spaces": list(obs_spaces),
        "output_dir": str(tmp_path / "out"),
        "work_dir": str(tmp_path / "work"),
        "summary_template": str(tmp_path / "data") + "/gdas.{cycle:%Y%m%d}/{cycle:%H}/products/{component}/anlmon/"
        "summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc",
    })


# ---------------------------------------------------------------------------
# run_window
# ---------------------------------------------------------------------------

class TestRunWindow:

    def test_end_to_end_with_gap(self, tmp_path):
        stage_diags(tmp_path / "data", skip=[CYCLES[1]])
        res = run_window(run_config(tmp_path))
        st = res.obs_spaces[0]
        assert st.status == "partial"
        assert st.missing_cycles == [f"{CYCLES[1]:%Y%m%d%H}"]
        assert st.cycles_with_data == 3 and st.variables == ["stationPressure"]
        assert st.figures_written == 10 and not st.figures_failed
        names = {p.name for p in (tmp_path / "out").glob("*.png")}
        assert "prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_Global_timeseries.png" in names
        status = json.loads((tmp_path / "out" / STATUS_FILE).read_text())
        assert status["obs_spaces"][0]["status"] == "partial" and status["cycles"][0] == f"{CYCLES[0]:%Y%m%d%H}"
        assert "1 partial" in status["summary"]

    def test_summaries_cached_where_configured(self, tmp_path):
        stage_diags(tmp_path / "data")
        run_window(run_config(tmp_path))
        for c in CYCLES:
            assert (tmp_path / f"data/gdas.{c:%Y%m%d}/{c:%H}/products/atmos/anlmon/"
                    f"summary_prepbufr_adpsfc_stationPressure_{c:%Y%m%d%H}.nc").is_file()

    def test_second_run_reads_cache_not_diags(self, tmp_path):
        stage_diags(tmp_path / "data")
        run_window(run_config(tmp_path))
        with patch.object(runmod, "read_ioda", side_effect=AssertionError("diag file re-read")) as m:
            res = run_window(run_config(tmp_path))
        assert m.call_count == 0 and res.obs_spaces[0].status == "ok"

    def test_cached_cycle_survives_diag_cleanup(self, tmp_path):
        stage_diags(tmp_path / "data")
        run_window(run_config(tmp_path))
        Path(DIAG.format(root=tmp_path / "data", c=CYCLES[0], o="prepbufr_adpsfc")).unlink()
        assert run_window(run_config(tmp_path)).obs_spaces[0].status == "ok"

    def test_unreadable_file_is_a_gap(self, tmp_path):
        stage_diags(tmp_path / "data")
        Path(DIAG.format(root=tmp_path / "data", c=CYCLES[2], o="prepbufr_adpsfc")).write_text("not netcdf")
        st = run_window(run_config(tmp_path)).obs_spaces[0]
        assert st.status == "partial" and list(st.unreadable_cycles) == [f"{CYCLES[2]:%Y%m%d%H}"]
        assert st.figures_written == 10

    def test_obs_space_failures_isolated(self, tmp_path):
        stage_diags(tmp_path / "data", "prepbufr_adpsfc")
        stage_diags(tmp_path / "data", "prepbufr_adpupa")
        real = runmod.plot_obs_space

        def flaky(stacked, ob_type, *a, **k):
            if ob_type == "prepbufr_adpupa":
                raise RuntimeError("boom")
            return real(stacked, ob_type, *a, **k)

        with patch.object(runmod, "plot_obs_space", flaky):
            res = run_window(run_config(tmp_path, ("prepbufr_adpupa", "prepbufr_adpsfc")))
        by = {s.obs_space: s for s in res.obs_spaces}
        assert by["prepbufr_adpupa"].status == "failed" and "boom" in by["prepbufr_adpupa"].error
        assert by["prepbufr_adpsfc"].status == "ok"

    def test_no_data(self, tmp_path):
        res = run_window(run_config(tmp_path))
        assert res.obs_spaces[0].status == "no_data" and res.figures_written == 0
        assert len(res.obs_spaces[0].missing_cycles) == len(CYCLES)

    def test_variables_discovered_when_not_configured(self, tmp_path):
        stage_diags(tmp_path / "data", "radiance_atms_n20")         # atms entry has no `variables`
        p = Path(DIAG.format(root=tmp_path / "data", c=CYCLES[0], o="radiance_atms_n20"))
        assert p.is_file()
        st = run_window(run_config(tmp_path, ("radiance_atms_n20",))).obs_spaces[0]
        assert st.variables == ["airTemperatureAt2M", "stationPressure"]   # adpsfc layout written under that name

    def test_all_figures_skipped_is_not_failed(self, tmp_path):
        stage_diags(tmp_path / "data")
        with patch.object(runmod, "plot_obs_space",
                          return_value=MagicMock(written=[], failed=[], skipped=[("x", "not implemented")])):
            st = run_window(run_config(tmp_path)).obs_spaces[0]
        assert st.status == "ok" and st.figures_skipped

    def test_all_figures_failed_is_failed(self, tmp_path):
        stage_diags(tmp_path / "data")
        with patch.object(runmod, "plot_obs_space",
                          return_value=MagicMock(written=[], failed=[("x", "boom")], skipped=[])):
            st = run_window(run_config(tmp_path)).obs_spaces[0]
        assert st.status == "failed"

    def test_snow_keeps_website_names(self, tmp_path):
        for c in CYCLES:
            p = tmp_path / f"data/gdas.{c:%Y%m%d}/{c:%H}/analysis/snow/diag_snocvr_snomad_{c:%Y%m%d%H}.nc"
            p.parent.mkdir(parents=True, exist_ok=True)
            write_snow(p, cycle=c)
        res = run_window(run_config(tmp_path, ("snocvr_snomad",)))
        assert res.obs_spaces[0].status == "ok"
        names = sorted(p.name for p in (tmp_path / "out").glob("*.png"))
        assert names == sorted([f"snocvr_totalSnowDepth_assimilated_mean_{f}_Global_timeseries.png" for f in
                                ("ombg", "oman")] + [f"snocvr_totalSnowDepth_assimilated_mean_{f}_map.png"
                                                     for f in ("ombg", "oman")])

    def test_only_extracted_diags_removed_from_work_dir(self, tmp_path):
        (tmp_path / "work" / "diags").mkdir(parents=True)
        (tmp_path / "work" / "keep.txt").write_text("x")
        run_window(run_config(tmp_path))
        assert not (tmp_path / "work" / "diags").exists() and (tmp_path / "work" / "keep.txt").exists()


# ---------------------------------------------------------------------------
# operational
# ---------------------------------------------------------------------------

def env(tmp_path, **over):
    e = {"PDY": f"{END:%Y%m%d}", "CYC": f"{END:%H}", "CYCLES": str(len(CYCLES)), "INTERVAL_HOURS": "6",
         "RUN": "gdas", "COMPONENT": "atmos", "DATAROOT": str(tmp_path / "data"),
         "COMROOT": str(tmp_path / "com"), "RUNTIME_DIR": str(tmp_path / "run"), "KEEP_DATA": "False"}
    e.update(over)
    return {k: v for k, v in e.items() if v is not None}


class TestOperational:

    def test_layout(self, tmp_path):
        rc = operational.build_run_configs(env(tmp_path))["atmos"]
        assert rc.output_dir == tmp_path / f"com/gdas.{END:%Y%m%d}/{END:%H}/atmos"
        assert rc.cycles[0] == CYCLES[0] and rc.cycles[-1] == END
        obs = {o.name: o for o in rc.obs_spaces}["prepbufr_adpsfc"]
        assert rc.locators["prepbufr_adpsfc"].template == str(tmp_path) + \
            "/data/gdas.{cycle:%Y%m%d}/{cycle:%H}/analysis/atmos/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"
        anlmon = tmp_path / f"data/gdas.{END:%Y%m%d}/{END:%H}/products/atmos/anlmon"
        assert rc.summary_path(obs, "stationPressure", END) == \
            anlmon / f"summary_prepbufr_adpsfc_stationPressure_{END:%Y%m%d%H}.nc"

    def test_cdate_and_unconfigured_component(self, tmp_path):
        cfgs = operational.build_run_configs(env(tmp_path, PDY=None, CYC=None, CDATE=f"{END:%Y%m%d%H}",
                                                 COMPONENT="atmos, ice"))
        assert list(cfgs) == ["atmos"]

    @pytest.mark.parametrize("over", [{"DATAROOT": None}, {"PDY": None, "CYC": None}, {"CYCLES": "four"},
                                      {"COMROOT": "relative/com"}, {"CDATE": "2026101", "PDY": None}])
    def test_bad_environment_exits_2(self, tmp_path, over):
        assert operational.main(env(tmp_path, **over)) == 2

    def test_exit_codes(self, tmp_path):
        assert operational.main(env(tmp_path)) == 1                 # nothing produced
        stage_diags(tmp_path / "data")
        assert operational.main(env(tmp_path)) == 0
        status = json.loads((tmp_path / f"com/gdas.{END:%Y%m%d}/{END:%H}/atmos" / STATUS_FILE).read_text())
        assert {s["obs_space"]: s["status"] for s in status["obs_spaces"]}["prepbufr_adpsfc"] == "ok"

    def test_nothing_configured_exits_0(self, tmp_path):
        assert operational.main(env(tmp_path, COMPONENT="ocean")) == 0


# ---------------------------------------------------------------------------
# stage (copy step)
# ---------------------------------------------------------------------------

def make_tarball(src: Path, cycle, members=("prepbufr_adpsfc", "prepbufr_adpupa", "radiance_atms_n20"),
                 component="atmos", age_minutes=30):
    d = src / f"gdas.{cycle:%Y%m%d}/{cycle:%H}/analysis/{component}"
    d.mkdir(parents=True, exist_ok=True)
    tb = d / f"gdas.t{cycle:%H}z.{component}_analysis.ioda_hofx.tar.gz"
    with tarfile.open(tb, "w:gz") as tar:
        for m in members:
            f = d / f"diag_{m}_{cycle:%Y%m%d%H}.nc"
            f.write_bytes(os.urandom(64))
            tar.add(f, arcname=f.name)
            f.unlink()
    t = time.time() - age_minutes * 60
    os.utime(tb, (t, t))
    return tb


class TestStage:

    def test_extracts_only_monitored_and_marks(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        tgt.mkdir()
        make_tarball(src, END, members=("prepbufr_adpsfc", "radiance_atms_n20", "radiance_cris_n20"))
        out = stage.stage(src, tgt, "gdas", "atmos", ["prepbufr_adpsfc", "prepbufr_adpupa"])
        d = tgt / f"gdas.{END:%Y%m%d}/{END:%H}/analysis/atmos"
        assert out == {f"{END:%Y%m%d%H}": "staged"}
        assert sorted(p.name for p in d.glob("*.nc")) == [f"diag_prepbufr_adpsfc_{END:%Y%m%d%H}.nc"]
        marker = json.loads((d / stage.MARKER).read_text())
        assert marker["missing"] == ["prepbufr_adpupa"] and "prepbufr_adpsfc" in marker["files"]

    def test_already_staged_and_too_new(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        tgt.mkdir()
        make_tarball(src, CYCLES[0])
        make_tarball(src, END, age_minutes=2)
        stage.stage(src, tgt, "gdas", "atmos", ["prepbufr_adpsfc"])
        out = stage.stage(src, tgt, "gdas", "atmos", ["prepbufr_adpsfc"])
        assert out == {f"{CYCLES[0]:%Y%m%d%H}": "already staged", f"{END:%Y%m%d%H}": "too new"}

    def test_missing_and_corrupt_tarballs_retried(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        tgt.mkdir()
        (src / f"gdas.{CYCLES[0]:%Y%m%d}/{CYCLES[0]:%H}").mkdir(parents=True)        # cycle dir, no tarball
        tb = make_tarball(src, END)
        tb.write_bytes(b"not a tarball")
        t = time.time() - 3600
        os.utime(tb, (t, t))
        out = stage.stage(src, tgt, "gdas", "atmos", ["prepbufr_adpsfc"])
        assert out == {f"{CYCLES[0]:%Y%m%d%H}": "no tarball", f"{END:%Y%m%d%H}": "unreadable"}
        assert not list(tgt.rglob(stage.MARKER))

    def test_component_without_obs_spaces_marked_without_reading(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        tgt.mkdir()
        make_tarball(src, END, component="ocean")
        with patch("tarfile.open", side_effect=AssertionError("tarball opened")):
            out = stage.stage(src, tgt, "gdas", "ocean", [])
        assert out == {f"{END:%Y%m%d%H}": "staged"}
        marker = json.loads(next(tgt.rglob(stage.MARKER)).read_text())
        assert marker["files"] == {} and marker["missing"] == []

    def test_cli(self, tmp_path):
        src, tgt = tmp_path / "src", tmp_path / "tgt"
        tgt.mkdir()
        make_tarball(src, END)
        assert stage.main(["--src", str(src), "--target", str(tgt)]) == 0
        assert list(tgt.rglob(stage.MARKER))
        assert stage.main(["--src", "relative", "--target", str(tgt)]) == 2


# ---------------------------------------------------------------------------
# Workflow pieces
# ---------------------------------------------------------------------------

def render(**kw):
    tpl = Environment(loader=FileSystemLoader(str(REPO))).get_template("parm/monitor_rocoto_template.xml.j2")
    base = dict(COMPONENTS=["atmos"], INTERVAL_HOURS=6, SDATE="202610110000", EDATE="202610120000")
    base.update(kw)
    return tpl.render(**base)


class TestWorkflow:

    def test_rocoto_single_component(self):
        xml = render()
        assert "06:00:00</cycledef>" in xml and "<and>" not in xml.split("push_to_server")[0]
        assert "analysis/atmos/obsmon_staged.json" in xml
        for retired in ("CONFIG_YAML", "CREATE_STUBS", "COPY_DATA", "_stats.txt"):
            assert retired not in xml

    def test_rocoto_multi_component_and_interval(self):
        xml = render(COMPONENTS=["atmos", "snow"], INTERVAL_HOURS=3)
        driver = xml.split("push_to_server")[0]
        assert "03:00:00</cycledef>" in xml
        assert "<and>" in driver and "analysis/snow/obsmon_staged.json" in driver

    def test_run_driver_calls_new_pipeline(self):
        sh = (REPO / "jobs/rocoto/run_driver.sh").read_text()
        assert "python -m obs_monitor.pipelines.operational" in sh and "obs_monitor.driver.driver" not in sh

    def test_push_files_fails_on_rsync_error(self, tmp_path, monkeypatch):
        from obs_monitor.driver import push_files
        for k, v in {"CDATE": "2026101200", "PSLOT": "x", "COMROOT": str(tmp_path), "SERVER": "s",
                     "SERVER_PATH": "/p", "SERVER_USER": "u"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(push_files, "Logger", MagicMock())
        bad = MagicMock(returncode=23, stdout="", stderr="permission denied")
        with patch.object(push_files.subprocess, "run", return_value=bad):
            with pytest.raises(SystemExit) as exc:
                push_files.main()
        assert exc.value.code == 23
        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(push_files.subprocess, "run", return_value=ok):
            push_files.main()
        assert json.loads((tmp_path / "latestCycle.json").read_text()) == {"cycleTime": "2026101200"}
