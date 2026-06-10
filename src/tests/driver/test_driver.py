"""
tests/driver/test_driver.py
============================

Unit tests for obs_monitor.driver.

Coverage targets
----------------
MonitoringConfig:
  - Correct ob_type construction for conventional and radiance monitor types
  - Timing window (end_time, start_time) derived correctly from PDY + CYC
  - runtime_dir is computed but NOT created during __init__
  - setup_runtime_dir() creates the directory
  - setup_runtime_dir() raises FileExistsError on collision (no silent overwrite)
  - Each instance gets a unique runtime_dir (uuid suffix)
  - Unknown monitor_type raises ValueError
  - Missing component raises ValueError
  - Malformed PDY raises ValueError
  - INTERVAL_HOURS=0 raises ValueError

build_expected_times_for_window:
  - Single cycle returns [t_end]
  - Four 6-hourly cycles: correct start, end, and count
  - Sixteen cycles: correct spacing throughout
  - Times are always monotonically increasing
  - t_end is always the last element

load_plot_config:
  - Returns config dict for a known ob_type
  - Returns None for an ob_type absent from the YAML
  - Returns None when the YAML file does not exist
  - Returns None when the YAML parses to a non-dict (list)
  - Returns None for an empty YAML file

cleanup_path:
  - Deletes an existing directory tree including contents
  - No-op (no exception) when path does not exist
  - Removes partial output from a failed job

run_monitoring_job:
  - Successful dispatch returns {"status": "ok"} with coverage key
  - Partial dispatch (some figures failed) returns {"status": "ok"} with warnings
  - Failed dispatch returns {"status": "failed"} with error key
  - Unhandled exception from dispatch_plots returns {"status": "failed"}
  - No .nc files after extraction returns {"status": "skipped_no_input"}
  - Missing plot config entry returns {"status": "skipped_no_plot_config"}
  - Runtime directory is cleaned up after success (KEEP_DATA=False)
  - Runtime directory is cleaned up after failure (KEEP_DATA=False)
  - Runtime directory is preserved when KEEP_DATA=True
"""

from __future__ import annotations

import os
import yaml
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from obs_monitor.driver import (
    MonitoringConfig,
    build_expected_times_for_window,
    load_plot_config,
    run_monitoring_job,
    cleanup_path,
)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

BASE_ENV = {
    "PDY":            "20240101",
    "CYC":            "06",
    "INTERVAL_HOURS": "6",
    "CYCLES":         "4",
    "EXPDIR":         "/tmp/expdir",
    "DATAROOT":       "/tmp/dataroot",
    "COMROOT":        "/tmp/comroot",
    "RUN":            "gdas",
    "COPY_DATA":      "False",
    "KEEP_DATA":      "False",
    "CREATE_STUBS":   "False",
}

CONVENTIONAL_JOB = {
    "monitor_type": "conventional",
    "variable":     "stationPressure",
    "component":    "atmos",
}

RADIANCE_JOB = {
    "monitor_type": "radiance",
    "satellite":    "aqua",
    "sensor":       "airs",
    "component":    "atmos",
}


@pytest.fixture
def runtime_root(tmp_path):
    d = tmp_path / "runtime"
    d.mkdir()
    return d


@pytest.fixture
def env(runtime_root, monkeypatch):
    """Patch the full environment required by MonitoringConfig."""
    full_env = {**BASE_ENV, "RUNTIME_DIR": str(runtime_root)}
    for k, v in full_env.items():
        monkeypatch.setenv(k, v)
    return full_env


@pytest.fixture
def plot_config_yaml(tmp_path):
    """Minimal PLOT_CONFIG_YAML with one ob_type entry."""
    data = {
        "stationPressure": {
            "figures": [{"type": "time_series", "variable": "stationPressure"}]
        }
    }
    p = tmp_path / "plot_config.yaml"
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# MonitoringConfig
# ---------------------------------------------------------------------------

class TestMonitoringConfig:

    def test_conventional_ob_type(self, env):
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        assert cfg.ob_type == "stationPressure"
        assert cfg.monitor_type == "conventional"
        assert cfg.component == "atmos"

    def test_radiance_ob_type(self, env):
        cfg = MonitoringConfig(RADIANCE_JOB, "20240101_060000")
        assert cfg.ob_type == "airs_aqua"
        assert cfg.monitor_type == "radiance"

    def test_end_time_matches_pdy_cyc(self, env):
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        assert cfg.end_time == datetime(2024, 1, 1, 6, tzinfo=timezone.utc)

    def test_start_time_is_cycles_minus_one_intervals_before_end(self, env):
        # 4 cycles at 6h spacing → start is 18h before end
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        assert cfg.start_time == datetime(2023, 12, 31, 12, tzinfo=timezone.utc)

    def test_runtime_dir_not_created_on_init(self, env):
        """__init__ must not touch the filesystem."""
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        assert not cfg.runtime_dir.exists()

    def test_setup_runtime_dir_creates_directory(self, env):
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        cfg.setup_runtime_dir()
        assert cfg.runtime_dir.exists()
        assert cfg.runtime_dir.is_dir()

    def test_setup_runtime_dir_raises_on_collision(self, env):
        cfg = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        cfg.runtime_dir.mkdir(parents=True)   # pre-create to force collision
        with pytest.raises(FileExistsError):
            cfg.setup_runtime_dir()

    def test_multiple_instances_have_distinct_runtime_dirs(self, env):
        cfg1 = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        cfg2 = MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")
        assert cfg1.runtime_dir != cfg2.runtime_dir

    def test_unknown_monitor_type_raises(self, env):
        bad_job = {**CONVENTIONAL_JOB, "monitor_type": "bogus"}
        with pytest.raises(ValueError, match="Unknown monitor_type"):
            MonitoringConfig(bad_job, "20240101_060000")

    def test_missing_component_raises(self, env):
        bad_job = {**CONVENTIONAL_JOB, "component": None}
        with pytest.raises(ValueError, match="component"):
            MonitoringConfig(bad_job, "20240101_060000")

    def test_malformed_pdy_raises(self, monkeypatch, env):
        monkeypatch.setenv("PDY", "2024-01-01")
        with pytest.raises(ValueError, match="PDY must be YYYYMMDD"):
            MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")

    def test_zero_interval_hours_raises(self, monkeypatch, env):
        monkeypatch.setenv("INTERVAL_HOURS", "0")
        with pytest.raises(ValueError, match="INTERVAL_HOURS"):
            MonitoringConfig(CONVENTIONAL_JOB, "20240101_060000")


# ---------------------------------------------------------------------------
# build_expected_times_for_window
# ---------------------------------------------------------------------------

def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestBuildExpectedTimesForWindow:

    def test_single_cycle_returns_only_t_end(self):
        t_end = _utc(2024, 1, 1, 6)
        times = build_expected_times_for_window(t_end, interval_hours=6, cycles=1)
        assert times == [t_end]

    def test_four_cycles_correct_start_and_end(self):
        t_end = _utc(2024, 1, 1, 18)
        times = build_expected_times_for_window(t_end, interval_hours=6, cycles=4)
        assert times[0] == _utc(2024, 1, 1, 0)
        assert times[-1] == t_end

    def test_four_cycles_correct_count(self):
        t_end = _utc(2024, 1, 1, 18)
        times = build_expected_times_for_window(t_end, interval_hours=6, cycles=4)
        assert len(times) == 4

    def test_sixteen_cycles_spacing_is_uniform(self):
        t_end = _utc(2024, 1, 4, 18)
        times = build_expected_times_for_window(t_end, interval_hours=6, cycles=16)
        gaps = [
            (times[i + 1] - times[i]).total_seconds() / 3600
            for i in range(len(times) - 1)
        ]
        assert all(g == 6.0 for g in gaps)

    def test_times_are_monotonically_increasing(self):
        t_end = _utc(2024, 6, 15, 12)
        times = build_expected_times_for_window(t_end, interval_hours=6, cycles=8)
        assert times == sorted(times)

    def test_t_end_is_always_last(self):
        t_end = _utc(2024, 3, 10, 0)
        for cycles in (1, 4, 16):
            times = build_expected_times_for_window(t_end, interval_hours=6,
                                                    cycles=cycles)
            assert times[-1] == t_end


# ---------------------------------------------------------------------------
# load_plot_config
# ---------------------------------------------------------------------------

class TestLoadPlotConfig:

    def test_returns_config_for_known_ob_type(self, plot_config_yaml):
        result = load_plot_config(plot_config_yaml, "stationPressure")
        assert result is not None
        assert "figures" in result

    def test_returns_none_for_missing_ob_type(self, plot_config_yaml):
        result = load_plot_config(plot_config_yaml, "nonexistentType")
        assert result is None

    def test_returns_none_when_file_does_not_exist(self, tmp_path):
        result = load_plot_config(tmp_path / "missing.yaml", "stationPressure")
        assert result is None

    def test_returns_none_for_list_yaml(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n")
        result = load_plot_config(p, "stationPressure")
        assert result is None

    def test_returns_none_for_empty_yaml(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        result = load_plot_config(p, "stationPressure")
        assert result is None


# ---------------------------------------------------------------------------
# cleanup_path
# ---------------------------------------------------------------------------

class TestCleanupPath:

    def test_removes_existing_directory_tree(self, tmp_path):
        d = tmp_path / "to_delete"
        d.mkdir()
        (d / "subdir").mkdir()
        (d / "subdir" / "file.txt").write_text("data")
        cleanup_path(d, MagicMock())
        assert not d.exists()

    def test_noop_when_path_does_not_exist(self, tmp_path):
        # Must not raise
        cleanup_path(tmp_path / "ghost", MagicMock())

    def test_removes_partial_output_from_failed_job(self, tmp_path):
        """Partial output must not block cleanup — no 'only if empty' guard."""
        d = tmp_path / "partial"
        d.mkdir()
        (d / "plots").mkdir()
        (d / "plots" / "figure.png").write_bytes(b"png")
        (d / "coverage.csv").write_text("time_utc,present\n")
        cleanup_path(d, MagicMock())
        assert not d.exists()


# ---------------------------------------------------------------------------
# run_monitoring_job — integration (dispatch_plots mocked)
# ---------------------------------------------------------------------------

DISPATCH_OK = {
    "status": "ok",
    "figures_requested": 2,
    "figures_written": 2,
    "errors": [],
}

DISPATCH_PARTIAL = {
    "status": "partial",
    "figures_requested": 2,
    "figures_written": 1,
    "errors": ["one figure failed to render"],
}

DISPATCH_FAILED = {
    "status": "failed",
    "figures_requested": 2,
    "figures_written": 0,
    "errors": ["catastrophic failure"],
}

MINIMAL_PLOT_CONFIGS = {
    "stationPressure": {
        "nc_groups": {"coords": "griddedBins"},
        "figures": [
            {
                "type": "time_series",
                "group_path": "byDomains/ombg/stationPressure",
                "stat": "assimilated_mean",
            }
        ],
    }
}


def _run_job(
    tmp_path,
    monkeypatch,
    dispatch_return=DISPATCH_OK,
    dispatch_raises=None,
    extra_env=None,
    plot_configs=None,
    seed_nc_file=True,
):
    """
    Set up the environment, patch all I/O, and call run_monitoring_job.

    Parameters
    ----------
    seed_nc_file:
        If True, write a dummy .nc file into the window_dir so stage 5
        (no-input guard) does not short-circuit the job.
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    env = {**BASE_ENV, "RUNTIME_DIR": str(runtime)}
    if extra_env:
        env.update(extra_env)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    configs = plot_configs if plot_configs is not None else MINIMAL_PLOT_CONFIGS
    args = (CONVENTIONAL_JOB, "20240101_060000", configs)

    def fake_find(*a, **kw):
        return [], [datetime(2024, 1, 1, 6, tzinfo=timezone.utc)], []

    def fake_extract(cfg, tarballs_in_runtime, expected_times, logger, window_dir):
        window_dir.mkdir(parents=True, exist_ok=True)
        if seed_nc_file:
            dummy = window_dir / f"{cfg.ob_type}_2024010106.nc"
            dummy.write_text("dummy")
        return (
            [window_dir / f"{cfg.ob_type}_2024010106.nc"] if seed_nc_file else [],
            expected_times,
            expected_times if seed_nc_file else [],
        )

    dispatch_mock = (
        MagicMock(side_effect=dispatch_raises)
        if dispatch_raises
        else MagicMock(return_value=dispatch_return)
    )

    with patch("obs_monitor.driver.find_matching_inputs_for_times",
               side_effect=fake_find), \
         patch("obs_monitor.driver.extract_tarballs_and_find_nc_for_times",
               side_effect=fake_extract), \
         patch("obs_monitor.driver.validate_and_quarantine_nc_files",
               side_effect=lambda nc_files, found_times, **kw: (nc_files, found_times)), \
         patch("obs_monitor.driver.dispatch_plots", dispatch_mock), \
         patch("obs_monitor.driver.copy_plots_to_com"), \
         patch("obs_monitor.driver.copy_plots_to_public"), \
         patch("obs_monitor.driver.write_coverage_report",
               return_value="4/4 (100%)"):
        return run_monitoring_job(args)


class TestRunMonitoringJob:

    def test_successful_job_returns_ok(self, tmp_path, monkeypatch):
        result = _run_job(tmp_path, monkeypatch)
        assert result["status"] == "ok"
        assert result["ob_type"] == "stationPressure"
        assert "coverage" in result

    def test_partial_dispatch_returns_ok_with_warnings(self, tmp_path, monkeypatch):
        result = _run_job(tmp_path, monkeypatch, dispatch_return=DISPATCH_PARTIAL)
        assert result["status"] == "ok"
        assert "warnings" in result

    def test_failed_dispatch_returns_failed(self, tmp_path, monkeypatch):
        result = _run_job(tmp_path, monkeypatch, dispatch_return=DISPATCH_FAILED)
        assert result["status"] == "failed"
        assert "error" in result

    def test_dispatch_exception_returns_failed(self, tmp_path, monkeypatch):
        """Unhandled exception from dispatch_plots must not propagate."""
        result = _run_job(tmp_path, monkeypatch,
                          dispatch_raises=RuntimeError("unexpected crash"))
        assert result["status"] == "failed"
        assert "dispatch_plots" in result["error"]

    def test_no_nc_files_returns_skipped_no_input(self, tmp_path, monkeypatch):
        result = _run_job(tmp_path, monkeypatch, seed_nc_file=False)
        assert result["status"] == "skipped_no_input"

    def test_missing_plot_config_returns_skipped(self, tmp_path, monkeypatch):
        result = _run_job(tmp_path, monkeypatch, plot_configs={})
        assert result["status"] == "skipped_no_plot_config"

    def test_cleanup_on_success(self, tmp_path, monkeypatch):
        """Runtime directory must be removed after a successful job."""
        _run_job(tmp_path, monkeypatch)
        runtime = tmp_path / "runtime"
        assert list(runtime.glob("runtime_*")) == []

    def test_cleanup_on_failure(self, tmp_path, monkeypatch):
        """Runtime directory must also be removed after a failed job."""
        _run_job(tmp_path, monkeypatch, dispatch_return=DISPATCH_FAILED)
        runtime = tmp_path / "runtime"
        assert list(runtime.glob("runtime_*")) == []

    def test_keep_data_preserves_runtime_dir(self, tmp_path, monkeypatch):
        """KEEP_DATA=True must leave the runtime directory on disk."""
        _run_job(tmp_path, monkeypatch, extra_env={"KEEP_DATA": "True"})
        runtime = tmp_path / "runtime"
        assert list(runtime.glob("runtime_*")) != []
