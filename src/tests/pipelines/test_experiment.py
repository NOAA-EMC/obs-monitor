"""Tests for obs_monitor.pipelines.experiment (the obs-monitor-exp command)."""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from obs_monitor.pipelines import experiment, run as runmod
from obs_monitor.pipelines.run import STATUS_FILE

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ioda"))
from ioda_fixtures import write_adpsfc  # noqa: E402

CYCLES = [datetime(2026, 10, 11) + timedelta(hours=6 * i) for i in range(4)]
START, END = f"{CYCLES[0]:%Y%m%d%H}", f"{CYCLES[-1]:%Y%m%d%H}"
TS_PNG = "prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_Global_timeseries.png"


@pytest.fixture(autouse=True)
def no_coastlines():
    """Coastlines need a cartopy download; not available in CI."""
    with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda self, *a, **k: None):
        yield


def write_diags(folder: Path, obs_space="prepbufr_adpsfc", skip=(), subdirs=False):
    for c in CYCLES:
        if c in skip:
            continue
        p = folder / (f"{c:%Y%m%d%H}/" if subdirs else "") / f"diag_{obs_space}_{c:%Y%m%d%H}.nc"
        p.parent.mkdir(parents=True, exist_ok=True)
        write_adpsfc(p, cycle=c, n=300)


def write_yaml(tmp_path, input_folder, out="out") -> Path:
    cfg = tmp_path / f"run_{input_folder}.yaml"
    cfg.write_text(
        f"cycles: {{start: {START}, end: {END}, interval_hours: 6}}\n"
        f"source: {{type: glob, template: '{tmp_path}/{input_folder}/diag_{{obs_space}}_{{cycle:%Y%m%d%H}}.nc'}}\n"
        f"obs_spaces: [prepbufr_adpsfc]\n"
        f"output_dir: {tmp_path}/{out}\n"
        f"work_dir: {tmp_path}/work\n")
    return cfg


def exp(*args) -> int:
    return experiment.main([str(a) for a in args])


def basic(tmp_path, *extra, inp=None, out=None):
    return exp("--input", inp or tmp_path / "diags", "--start", START, "--end", END,
               "--output", out or tmp_path / "out", *extra)


class TestRuns:

    def test_flat_folder_defaults(self, tmp_path):
        write_diags(tmp_path / "diags", skip=[CYCLES[1]])
        assert basic(tmp_path) == 0
        out = tmp_path / "out"
        assert (out / TS_PNG).is_file()
        status = json.loads((out / STATUS_FILE).read_text())
        st = status["obs_spaces"]
        assert [s["obs_space"] for s in st] == ["prepbufr_adpsfc"]          # only what was found
        assert st[0]["status"] == "partial" and st[0]["missing_cycles"] == [f"{CYCLES[1]:%Y%m%d%H}"]
        assert (out / "summaries").is_dir()
        record = json.loads((out / "summaries" / experiment.RUN_RECORD).read_text())
        assert record["input"] == "glob:" + str(tmp_path / "diags" / experiment.DEFAULT_PATTERN)

    def test_subfolder_pattern(self, tmp_path):
        write_diags(tmp_path / "diags", subdirs=True)
        pattern = "{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"
        assert basic(tmp_path, "--pattern", pattern) == 0
        assert (tmp_path / "out" / TS_PNG).is_file()

    def test_relative_paths(self, tmp_path, monkeypatch):
        write_diags(tmp_path / "diags")
        monkeypatch.chdir(tmp_path)
        assert basic(tmp_path, inp="diags", out="out") == 0
        assert (tmp_path / "out" / TS_PNG).is_file()

    def test_rerun_uses_cache(self, tmp_path):
        write_diags(tmp_path / "diags")
        assert basic(tmp_path) == 0
        with patch.object(runmod, "read_ioda", side_effect=AssertionError("diag file re-read")):
            assert basic(tmp_path) == 0

    def test_explicit_obs_space(self, tmp_path):
        write_diags(tmp_path / "diags")
        write_diags(tmp_path / "diags", obs_space="prepbufr_sfcshp")
        assert basic(tmp_path, "--obs-space", "prepbufr_adpsfc") == 0
        status = json.loads((tmp_path / "out" / STATUS_FILE).read_text())
        assert [s["obs_space"] for s in status["obs_spaces"]] == ["prepbufr_adpsfc"]

    def test_config_yaml(self, tmp_path):
        write_diags(tmp_path / "diags")
        assert exp("--config", write_yaml(tmp_path, "diags")) == 0
        assert (tmp_path / "out" / TS_PNG).is_file()
        assert (tmp_path / "out" / "summaries" / experiment.RUN_RECORD).is_file()     # YAML runs record too

    def test_config_yaml_com_source(self, tmp_path):
        """source: {type: com} reads g-w tarballs, extracts only what it needs and removes it afterwards."""
        com = tmp_path / "COMROOT"
        for c in CYCLES:
            d = com / f"gdas.{c:%Y%m%d}/{c:%H}/analysis/atmos"
            d.mkdir(parents=True)
            diag = tmp_path / f"diag_prepbufr_adpsfc_{c:%Y%m%d%H}.nc"
            write_adpsfc(diag, cycle=c, n=300)
            with tarfile.open(d / f"gdas.t{c:%H}z.atmos_analysis.ioda_hofx.tar.gz", "w:gz") as tar:
                tar.add(diag, arcname=diag.name)
            diag.unlink()
        cfg = tmp_path / "run.yaml"
        cfg.write_text(f"cycles: {{start: {START}, end: {END}}}\n"
                       f"source: {{type: com, comroot: {com}}}\n"
                       f"obs_spaces: [prepbufr_adpsfc]\n"
                       f"output_dir: {tmp_path}/out\n"
                       f"work_dir: {tmp_path}/work\n")
        assert exp("--config", cfg) == 0
        assert (tmp_path / "out" / TS_PNG).is_file()
        assert not [p for p in (tmp_path / "work").rglob("*") if p.is_file()]     # extracted files removed
        assert len(list(com.rglob("*.tar.gz"))) == len(CYCLES)                     # tarballs untouched
        record = json.loads((tmp_path / "out" / "summaries" / experiment.RUN_RECORD).read_text())
        assert record["input"].startswith(f"com:{com}|gdas|atmos|")

    @pytest.mark.parametrize("value", ["prepbufr_adpsfc,prepbufr_sfcshp", "prepbufr_adpsfc prepbufr_sfcshp"])
    def test_obs_space_list(self, tmp_path, value):
        for o in ("prepbufr_adpsfc", "prepbufr_sfcshp", "prepbufr_adpupa"):
            write_diags(tmp_path / "diags", obs_space=o)
        assert basic(tmp_path, "--obs-space", *value.split(" ")) == 0
        status = json.loads((tmp_path / "out" / STATUS_FILE).read_text())
        assert [s["obs_space"] for s in status["obs_spaces"]] == ["prepbufr_adpsfc", "prepbufr_sfcshp"]

    def test_input_under_output_work_is_never_deleted(self, tmp_path):
        """--input <out>/work/diags --output <out>: the user's diag files must survive the run."""
        inp = tmp_path / "expt" / "work" / "diags"
        write_diags(inp)
        before = sorted(p.name for p in inp.iterdir())
        assert basic(tmp_path, inp=inp, out=tmp_path / "expt") == 0
        assert sorted(p.name for p in inp.iterdir()) == before


class TestObsSpaceDiscovery:

    def test_unconfigured_obs_space_skipped_and_named(self, tmp_path, caplog):
        write_diags(tmp_path / "diags")
        write_diags(tmp_path / "diags", obs_space="mystery_sfc")
        with caplog.at_level(logging.WARNING, logger="obs_monitor.experiment"):
            assert basic(tmp_path) == 0
        assert "mystery_sfc" in caplog.text and "--obs-space-config" in caplog.text
        status = json.loads((tmp_path / "out" / STATUS_FILE).read_text())
        assert [s["obs_space"] for s in status["obs_spaces"]] == ["prepbufr_adpsfc"]

    def test_extra_obs_space_config(self, tmp_path):
        write_diags(tmp_path / "diags", obs_space="mystery_sfc")
        extra = tmp_path / "mine.yaml"
        extra.write_text("obs_spaces:\n  mystery_sfc:\n    component: atmos\n    variables: [stationPressure]\n")
        assert basic(tmp_path, "--obs-space-config", extra) == 0
        assert (tmp_path / "out" / TS_PNG.replace("prepbufr_adpsfc", "mystery_sfc")).is_file()

    def test_discover_obs_spaces(self, tmp_path):
        write_diags(tmp_path / "diags", skip=CYCLES[1:])
        write_diags(tmp_path / "diags", obs_space="prepbufr_sfcshp", skip=CYCLES[:-1])
        template = str(tmp_path / "diags" / experiment.DEFAULT_PATTERN)
        assert experiment.discover_obs_spaces(template, CYCLES) == ["prepbufr_adpsfc", "prepbufr_sfcshp"]


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        experiment.main(["--help"])
    assert exc.value.code == 0
    assert "diag_{obs_space}_{cycle:%Y%m%d%H}.nc" in capsys.readouterr().out


class TestErrors:

    def test_no_files_exits_1(self, tmp_path):
        (tmp_path / "diags").mkdir()
        assert basic(tmp_path) == 1

    @pytest.mark.parametrize("args", [
        ["--start", START, "--end", END],                                     # no --input/--output
        ["--end", END, "--input", "{d}", "--output", "{o}"],                  # no --start
        ["--start", END, "--end", START, "--input", "{d}", "--output", "{o}"],  # start after end
        ["--start", START, "--end", END, "--input", "{d}/nope", "--output", "{o}"],
        ["--start", START, "--end", END, "--input", "{d}", "--output", "{o}", "--pattern", "/abs/{obs_space}.nc"],
        ["--start", START, "--end", END, "--input", "{d}", "--output", "{o}", "--pattern", "diag_{obs_space}.nc"],
        ["--start", START, "--end", END, "--input", "{d}", "--output", "{o}",
         "--pattern", "diag_{obs_space}_{cycle:%Y%m%d%H}_{member}.nc"],              # unknown field
        ["--start", START, "--end", END, "--input", "{d}", "--output", "{o}",
         "--pattern", "diag_{obs_space}_{cycle:%Y%m%d%H}}.nc"],                      # unbalanced brace
        ["--start", START, "--end", END, "--input", "{d}", "--output", "{o}", "--obs-space", "not_a_real_one"],
        ["--config", "{d}/run.yaml", "--start", START],                       # --config plus other options
        ["--config", "{d}/missing.yaml"],
    ])
    def test_bad_arguments_exit_2(self, tmp_path, args):
        write_diags(tmp_path / "diags")
        args = [a.replace("{d}", str(tmp_path / "diags")).replace("{o}", str(tmp_path / "out")) for a in args]
        assert exp(*args) == 2

    def test_output_reused_for_other_input_refused(self, tmp_path):
        write_diags(tmp_path / "diags")
        assert basic(tmp_path) == 0
        shutil.copytree(tmp_path / "diags", tmp_path / "other")
        assert basic(tmp_path, inp=tmp_path / "other") == 2
        assert basic(tmp_path, inp=tmp_path / "other", out=tmp_path / "out2") == 0

    def test_yaml_run_reusing_output_refused(self, tmp_path):
        """A --config run for experiment B can't reuse experiment A's cache (command line or YAML)."""
        write_diags(tmp_path / "diags")
        shutil.copytree(tmp_path / "diags", tmp_path / "other")
        assert basic(tmp_path) == 0
        with patch.object(experiment, "run_window", side_effect=AssertionError("ran anyway")):
            assert exp("--config", write_yaml(tmp_path, "other")) == 2
        assert exp("--config", write_yaml(tmp_path, "diags")) == 0                # same input: fine

    @pytest.mark.parametrize("content", ["", "{trunc", "{}", '{"input": ""}', '{"input": 5}', "[1, 2]"])
    def test_unreadable_record_refused(self, tmp_path, content):
        write_diags(tmp_path / "diags")
        assert basic(tmp_path) == 0
        (tmp_path / "out" / "summaries" / experiment.RUN_RECORD).write_text(content)
        with patch.object(experiment, "run_window", side_effect=AssertionError("ran anyway")):
            assert basic(tmp_path) == 2

    def test_record_written_atomically(self, tmp_path):
        write_diags(tmp_path / "diags")
        assert basic(tmp_path) == 0
        assert not list((tmp_path / "out" / "summaries").glob("*.tmp"))
