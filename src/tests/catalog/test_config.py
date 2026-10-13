"""Tests for obs_monitor.config (obs-space YAML and run config)."""

from __future__ import annotations

from datetime import datetime

import pytest
import yaml

from obs_monitor.config import ConfigError, RunConfig, load_obs_spaces, load_run_config
from obs_monitor.io.catalog import ComTarballLocator, GlobLocator


def write_yaml(path, data):
    path.write_text(yaml.safe_dump(data))
    return path


# ---------------------------------------------------------------------------
# Obs-space YAML
# ---------------------------------------------------------------------------

class TestObsSpaces:

    def test_shipped_config_loads(self):
        spaces = load_obs_spaces()
        assert {"prepbufr_adpsfc", "prepbufr_adpupa", "prepbufr_sfcshp", "radiance_atms_n20"} <= set(spaces)
        adpsfc = spaces["prepbufr_adpsfc"]
        assert adpsfc.component == "atmos"
        assert adpsfc.variables == ("stationPressure",)
        assert adpsfc.label == "prepbufr_adpsfc"
        assert spaces["radiance_atms_n20"].variables is None

    def test_full_entry(self, tmp_path):
        f = write_yaml(tmp_path / "x.yaml", {"obs_spaces": {"radiance_atms_n20": {
            "component": "atmos", "channels": [7, 1, 15], "web_name": "atms_n20",
            "group_map": {"qc_bg": "EffectiveQC"}}}})
        o = load_obs_spaces(f)["radiance_atms_n20"]
        assert o.channels == (1, 7, 15)
        assert o.label == "atms_n20"
        assert o.group_map == {"qc_bg": "EffectiveQC"}

    @pytest.mark.parametrize("spec, match", [
        ({"component": "atmos", "chanels": [1]}, "unknown key"),
        ({"variables": ["x"]}, "component"),
        ({"component": "atmos", "variables": "stationPressure"}, "variables"),
        ({"component": "atmos", "channels": [0, 1]}, "channels"),
        ({"component": "atmos", "channels": [1, 1]}, "duplicates"),
        ({"component": "atmos", "group_map": {"hofx_final": "hofx2"}}, "unknown field"),
        ({"component": "atmos", "description": "no longer a key"}, "unknown key"),
    ])
    def test_invalid_entries(self, tmp_path, spec, match):
        f = write_yaml(tmp_path / "x.yaml", {"obs_spaces": {"foo": spec}})
        with pytest.raises(ConfigError, match=match):
            load_obs_spaces(f)

    def test_duplicate_across_files(self, tmp_path):
        write_yaml(tmp_path / "a.yaml", {"obs_spaces": {"foo": {"component": "atmos"}}})
        write_yaml(tmp_path / "b.yaml", {"obs_spaces": {"foo": {"component": "chem"}}})
        with pytest.raises(ConfigError, match="defined in both"):
            load_obs_spaces(tmp_path)

    def test_bad_top_level(self, tmp_path):
        f = write_yaml(tmp_path / "x.yaml", {"ob_types": {}})
        with pytest.raises(ConfigError, match="obs_spaces"):
            load_obs_spaces(f)

    def test_missing_path(self, tmp_path):
        with pytest.raises(ConfigError, match="does not exist"):
            load_obs_spaces(tmp_path / "nope")


# ---------------------------------------------------------------------------
# Run config
# ---------------------------------------------------------------------------

def base(tmp_path, **over):
    cfg = {
        "cycles": {"start": 2026093000, "end": 2026100100, "interval_hours": 6},
        "source": {"type": "com", "comroot": str(tmp_path / "com")},
        "obs_spaces": "all",
        "output_dir": str(tmp_path / "out"),
        "work_dir": str(tmp_path / "work"),
    }
    cfg.update(over)
    return cfg


class TestRunConfig:

    def test_com_source(self, tmp_path):
        rc = RunConfig.from_dict(base(tmp_path))
        assert len(rc.cycles) == 5 and rc.cycles[-1] == datetime(2026, 10, 1, 0)
        assert "prepbufr_adpsfc" in rc.obs_space_names
        loc = rc.locators["prepbufr_adpsfc"]
        assert isinstance(loc, ComTarballLocator)
        assert loc.work_dir == tmp_path / "work" / "diags"
        # one locator per component, shared by its obs spaces (tarball read once per cycle)
        assert rc.locators["radiance_atms_n20"] is loc
        assert rc.keep_work is False

    def test_trailing_window(self, tmp_path):
        rc = RunConfig.from_dict(base(tmp_path, cycles={"end": "2026100100", "n_cycles": 4}))
        assert [c.hour for c in rc.cycles] == [6, 12, 18, 0]

    def test_glob_source_and_subset(self, tmp_path):
        tmpl = str(tmp_path) + "/expt/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"
        rc = RunConfig.from_dict(base(tmp_path, source={"type": "glob", "template": tmpl},
                                      obs_spaces=["prepbufr_adpsfc"]))
        assert rc.obs_space_names == ["prepbufr_adpsfc"]
        assert isinstance(rc.locators["prepbufr_adpsfc"], GlobLocator)

    def test_env_and_home_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OBSMON_TEST_ROOT", str(tmp_path))
        rc = RunConfig.from_dict(base(tmp_path, output_dir="$OBSMON_TEST_ROOT/out"))
        assert rc.output_dir == tmp_path / "out"

    def test_extra_obs_space_config(self, tmp_path):
        extra = write_yaml(tmp_path / "mine.yaml", {"obs_spaces": {"my_new_space": {"component": "atmos"}}})
        rc = RunConfig.from_dict(base(tmp_path, obs_space_config=str(extra), obs_spaces=["my_new_space"]))
        assert rc.obs_space_names == ["my_new_space"]

    @pytest.mark.parametrize("over, match", [
        ({"output_dir": "relative/out"}, "absolute"),
        ({"work_dir": "$OBSMON_SURELY_UNSET_VAR/work"}, "unset environment variable"),
        ({"cycles": {"start": 2026093000, "end": 2026093017}}, "whole number"),
        ({"cycles": {"start": 2026093000}}, "start\\+end or end\\+n_cycles"),
        ({"obs_spaces": ["prepbufr_adpsfc", "made_up"]}, "unknown obs space"),
        ({"obs_spaces": ["prepbufr_adpsfc", "prepbufr_adpsfc"]}, "more than once"),
        ({"source": {"type": "ftp"}}, "com' or 'glob"),
        ({"source": {"type": "com"}}, "comroot"),
        ({"source": {"type": "com", "comroot": "/x", "compnent": "atmos"}}, "unknown key"),
        ({"source": {"type": "glob", "template": "/x/diag_{cycle:%Y%m%d%H}.nc"}}, "obs_space"),
        ({"keep_work": "yes"}, "keep_work"),
        ({"outputdir": "/x"}, "unknown key"),
    ])
    def test_invalid(self, tmp_path, over, match):
        with pytest.raises(ConfigError, match=match):
            RunConfig.from_dict(base(tmp_path, **over))

    def test_missing_required(self, tmp_path):
        cfg = base(tmp_path)
        del cfg["work_dir"]
        with pytest.raises(ConfigError, match="work_dir"):
            RunConfig.from_dict(cfg)

    def test_load_from_file(self, tmp_path):
        f = write_yaml(tmp_path / "run.yaml", base(tmp_path))
        assert load_run_config(f).output_dir == tmp_path / "out"
        with pytest.raises(ConfigError, match="not found"):
            load_run_config(tmp_path / "missing.yaml")
