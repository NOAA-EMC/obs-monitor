"""Tests for obs_monitor.pipelines.experiment (the obs-monitor-exp command)."""

from __future__ import annotations

import json
import logging
import re
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


def cache_folders(out: Path) -> list[Path]:
    """The per-input cache folders under <out>/summaries."""
    return sorted(p.parent for p in (out / "summaries").glob(f"*/{experiment.INPUT_INFO}"))


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
        (cache,) = cache_folders(out)
        info = json.loads((cache / experiment.INPUT_INFO).read_text())
        assert info == {"type": "glob", "template": str(tmp_path / "diags" / experiment.DEFAULT_PATTERN)}
        assert list(cache.rglob("summary_prepbufr_adpsfc_stationPressure_*.nc"))

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
        assert len(cache_folders(tmp_path / "out")) == 1                              # YAML runs are keyed too

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
        (cache,) = cache_folders(tmp_path / "out")
        info = json.loads((cache / experiment.INPUT_INFO).read_text())
        assert info["type"] == "com" and info["comroot"] == str(com) and info["run"] == "gdas"

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


# ---------------------------------------------------------------------------
# Cache folders keyed by input (one per configured source)
# ---------------------------------------------------------------------------

class TestInputKeyedCache:

    def test_two_inputs_one_output_never_mix(self, tmp_path):
        """Experiment B in experiment A's --output reads B's own files and gets B's own cache."""
        write_diags(tmp_path / "diags")
        write_diags(tmp_path / "other", skip=[CYCLES[0]])                  # B differs: no first cycle
        assert basic(tmp_path) == 0
        with patch.object(runmod, "read_ioda", wraps=runmod.read_ioda) as reads:
            assert basic(tmp_path, inp=tmp_path / "other") == 0
        assert reads.call_count == len(CYCLES) - 1                         # nothing taken from A's cache
        status = json.loads((tmp_path / "out" / STATUS_FILE).read_text())["obs_spaces"][0]
        assert status["missing_cycles"] == [f"{CYCLES[0]:%Y%m%d%H}"]      # A's first cycle not borrowed
        assert len(cache_folders(tmp_path / "out")) == 2
        with patch.object(runmod, "read_ioda", side_effect=AssertionError("re-read")):
            assert basic(tmp_path) == 0                                    # A's cache still intact

    def test_unrecorded_old_cache_is_never_read(self, tmp_path):
        """Summaries left by a direct run_window run (no input info) are not adopted."""
        from obs_monitor.config import RunConfig
        from obs_monitor.pipelines.run import run_window
        write_diags(tmp_path / "diags")
        write_diags(tmp_path / "other")
        run_window(RunConfig.from_dict({                                   # old flat layout: summaries/<obs>/...
            "cycles": {"start": START, "end": END},
            "source": {"type": "glob", "template": str(tmp_path / "diags" / experiment.DEFAULT_PATTERN)},
            "obs_spaces": ["prepbufr_adpsfc"], "output_dir": str(tmp_path / "out"),
            "work_dir": str(tmp_path / "work")}))
        assert (tmp_path / "out" / "summaries" / "prepbufr_adpsfc").is_dir()
        with patch.object(runmod, "read_ioda", wraps=runmod.read_ioda) as reads:
            assert basic(tmp_path, inp=tmp_path / "other") == 0
        assert reads.call_count == len(CYCLES)

    def test_two_inputs_never_share_a_path(self, tmp_path):
        """No shared state between different inputs, so two first runs at once can't collide."""
        a, _, _ = experiment.keyed_cache({"source": {"type": "glob", "template": "/a/diag_{obs_space}_{cycle:%Y}.nc"},
                                          "output_dir": "/out"})
        b, _, _ = experiment.keyed_cache({"source": {"type": "glob", "template": "/b/diag_{obs_space}_{cycle:%Y}.nc"},
                                          "output_dir": "/out"})
        assert a["summary_template"] != b["summary_template"]
        assert a["summary_template"].split("{")[0] != b["summary_template"].split("{")[0]

    def test_id_independent_of_obs_spaces_and_components(self, tmp_path):
        com = {"type": "com", "comroot": "/com/expt"}
        ids = {experiment.keyed_cache({"source": com, "output_dir": "/out", "obs_spaces": o})[0]["summary_template"]
               for o in (["prepbufr_adpsfc"], ["prepbufr_adpsfc", "snocvr_snomad"], "all")}
        assert len(ids) == 1
        glob = {"type": "glob", "template": "/e/{component}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"}
        ids = {experiment.keyed_cache({"source": glob, "output_dir": "/out", "obs_spaces": o})[0]["summary_template"]
               for o in (["prepbufr_adpsfc"], ["prepbufr_adpsfc", "snocvr_snomad"])}
        assert len(ids) == 1

    @pytest.mark.parametrize("a, b", [
        ({"type": "com", "comroot": "/com/expt"}, {"type": "com", "comroot": "/com/expt/"}),
        ({"type": "com", "comroot": "/com/expt"}, {"type": "com", "comroot": "/com/expt", "run": "gdas"}),
        ({"type": "glob", "template": "/e//diag_{obs_space}_{cycle:%Y}.nc"},
         {"type": "glob", "template": "/e/diag_{obs_space}_{cycle:%Y}.nc"}),
    ])
    def test_same_source_written_differently_same_id(self, a, b):
        assert experiment.input_id(experiment.describe_source(a)) == experiment.input_id(experiment.describe_source(b))

    @pytest.mark.parametrize("b", [
        {"type": "com", "comroot": "/com/other"},
        {"type": "com", "comroot": "/com/expt", "run": "gfs"},
        {"type": "com", "comroot": "/com/expt", "member_template": "x_{obs_space}_{cycle:%Y}.nc"},
        {"type": "glob", "template": "/com/expt/diag_{obs_space}_{cycle:%Y}.nc"},
    ])
    def test_different_source_different_id(self, b):
        a = {"type": "com", "comroot": "/com/expt"}
        assert experiment.input_id(experiment.describe_source(a)) != experiment.input_id(experiment.describe_source(b))

    def test_custom_summary_template_is_keyed_too(self, tmp_path):
        write_diags(tmp_path / "diags")
        cfg = write_yaml(tmp_path, "diags")
        cfg.write_text(cfg.read_text() + f"summary_template: {tmp_path}/cache/sum_{{obs_space}}_{{variable}}_"
                       "{cycle:%Y%m%d%H}.nc\n")
        assert exp("--config", cfg) == 0
        (info,) = (tmp_path / "cache").glob(f"*/{experiment.INPUT_INFO}")
        assert len(list(info.parent.glob("sum_prepbufr_adpsfc_stationPressure_*.nc"))) == len(CYCLES)
        assert not list((tmp_path / "cache").glob("sum_*.nc"))             # nothing written unkeyed

    def test_folder_names_are_readable(self, tmp_path):
        """<input folder name>-<12-hex id>: people can tell caches apart, ids keep them unique."""
        write_diags(tmp_path / "diags")
        write_diags(tmp_path / "other")
        assert basic(tmp_path) == 0 and basic(tmp_path, inp=tmp_path / "other") == 0
        names = sorted(p.name for p in cache_folders(tmp_path / "out"))
        assert [n.rsplit("-", 1)[0] for n in names] == ["diags", "other"]
        assert all(re.fullmatch(r"[0-9a-f]{12}", n.rsplit("-", 1)[1]) for n in names)

    @pytest.mark.parametrize("source, label", [
        ({"type": "glob", "template": "/s/myexpt/diags/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"}, "diags"),
        ({"type": "glob", "template": "/s/myexpt/diags/{cycle:%Y%m%d%H}/diag_{obs_space}.nc"}, "diags"),
        ({"type": "glob", "template": "/s/myexpt/{obs_space}/diag_{cycle:%Y%m%d%H}.nc"}, "myexpt"),
        ({"type": "glob", "template": "/{obs_space}_{cycle:%Y}.nc"}, "input"),
        ({"type": "com", "comroot": "/scratch/COMROOT/my expt (v2)/"}, "my_expt_v2"),
        ({"type": "com", "comroot": "/s/" + "x" * 60}, "x" * 40),
    ])
    def test_label(self, source, label):
        assert experiment.input_label(experiment.describe_source(source)) == label

    def test_same_name_different_place_never_shares(self):
        a = experiment.describe_source({"type": "glob", "template": "/a/diags/diag_{obs_space}_{cycle:%Y}.nc"})
        b = experiment.describe_source({"type": "glob", "template": "/b/diags/diag_{obs_space}_{cycle:%Y}.nc"})
        assert experiment.input_label(a) == experiment.input_label(b) == "diags"
        assert experiment.cache_folder_name(a) != experiment.cache_folder_name(b)

    def test_input_info_written_atomically(self, tmp_path):
        write_diags(tmp_path / "diags")
        assert basic(tmp_path) == 0
        assert not list((tmp_path / "out" / "summaries").rglob("*.tmp"))

    def test_unwritable_cache_folder_exits_2(self, tmp_path):
        write_diags(tmp_path / "diags")
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "summaries").write_text("a file, not a folder")
        with patch.object(experiment, "run_window", side_effect=AssertionError("ran anyway")):
            assert basic(tmp_path) == 2
