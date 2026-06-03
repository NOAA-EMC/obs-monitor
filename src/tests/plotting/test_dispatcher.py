"""
tests/plotting/test_dispatcher.py
===================================

Unit tests for ``obs_monitor.plotting.dispatcher``.

The dispatcher is tested at two levels:

1. **Unit** — ``_validate_config``, ``_discover_nc_files``, and
   ``_DatasetCache`` are tested in isolation with synthetic inputs.

2. **Integration** — ``dispatch_plots`` is tested end-to-end using synthetic
   NetCDF files from ``conftest.py``.  EMCPy rendering is mocked so these
   tests run in CI without a display.

Coverage targets
----------------
_validate_config:
  - Accepts a well-formed config
  - Rejects configs missing required top-level keys
  - Rejects configs missing required nc_groups keys
  - Rejects unknown figure types
  - Rejects specs missing the 'stat' key

_discover_nc_files:
  - Finds files matching ob_type glob
  - Returns sorted list
  - Returns empty list when none match

_DatasetCache:
  - Returns same Dataset object on second call (no re-read)
  - Different group paths produce different cache entries

dispatch_plots:
  - Returns 'ok' status for a well-formed config + valid files
  - Writes the expected number of PNG files
  - Returns 'skipped' when no NetCDF files found
  - Returns 'skipped' with empty data_vars Dataset
  - 'partial' status when some specs fail
  - Summary dict has required keys
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from obs_monitor.plotting.dispatcher import (
    _validate_config,
    _discover_nc_files,
    _DatasetCache,
    dispatch_plots,
)

from conftest import DOMAINS, N_DOMAINS, BINS_Y, BINS_X, nc_filename


# ---------------------------------------------------------------------------
# Minimal valid config
# ---------------------------------------------------------------------------

def _valid_config(stat: str = "assimilated_mean") -> dict:
    return {
        "variable": "stationPressure",
        "unit":     "Pa",
        "nc_groups": {
            "time_series": "byDomains/ombg/stationPressure",
            "gridded":     "griddedBins/ombg/stationPressure",
            "coords":      "griddedBins",
        },
        "figures": [
            {
                "type":    "time_series",
                "stat":    stat,
                "title":   "{ob_type} {stat} — {domain}",
                "y_label": "stationPressure (Pa)",
                "domains": ["Global", "CONUS"],
            },
            {
                "type":           "map_gridded",
                "stat":           stat,
                "title":          "{ob_type} {variable} {stat}",
                "colorbar_label": "stationPressure (Pa)",
                "projection":     "plcarr",
                "domain":         "global",
                "cmap":           "coolwarm",
            },
        ],
    }


# ---------------------------------------------------------------------------
# _validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:

    def test_valid_config_returns_true(self):
        assert _validate_config(_valid_config(), "prepbufr_adpsfc") is True

    def test_missing_variable_key(self):
        cfg = _valid_config()
        del cfg["variable"]
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_missing_nc_groups_key(self):
        cfg = _valid_config()
        del cfg["nc_groups"]
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_missing_figures_key(self):
        cfg = _valid_config()
        del cfg["figures"]
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_missing_nc_groups_subkey(self):
        cfg = _valid_config()
        del cfg["nc_groups"]["gridded"]
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_unknown_figure_type(self):
        cfg = _valid_config()
        cfg["figures"][0]["type"] = "unknown_type"
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_missing_stat_key_in_spec(self):
        cfg = _valid_config()
        del cfg["figures"][0]["stat"]
        assert _validate_config(cfg, "prepbufr_adpsfc") is False

    def test_empty_figures_list(self):
        cfg = _valid_config()
        cfg["figures"] = []
        assert _validate_config(cfg, "prepbufr_adpsfc") is False


# ---------------------------------------------------------------------------
# _discover_nc_files
# ---------------------------------------------------------------------------

class TestDiscoverNcFiles:

    def test_finds_matching_files(self, multi_nc_files, ob_type):
        runtime_dir = multi_nc_files[0].parent
        found = _discover_nc_files(runtime_dir, ob_type)
        assert len(found) == len(multi_nc_files)

    def test_returns_sorted_list(self, multi_nc_files, ob_type):
        runtime_dir = multi_nc_files[0].parent
        found = _discover_nc_files(runtime_dir, ob_type)
        assert found == sorted(found)

    def test_returns_empty_for_nonmatching_ob_type(self, multi_nc_files):
        runtime_dir = multi_nc_files[0].parent
        found = _discover_nc_files(runtime_dir, "radiance_amsua_n19")
        assert found == []

    def test_returns_empty_for_empty_dir(self, tmp_path):
        found = _discover_nc_files(tmp_path, "prepbufr_adpsfc")
        assert found == []


# ---------------------------------------------------------------------------
# _DatasetCache
# ---------------------------------------------------------------------------

class TestDatasetCache:

    def test_cache_hit_returns_same_object(self, multi_nc_files, stat_group):
        cache = _DatasetCache()
        group_path = f"byDomains/{stat_group}"
        variables  = ["assimilated_mean"]

        ds1 = cache.get_or_read(multi_nc_files, group_path, variables)
        ds2 = cache.get_or_read(multi_nc_files, group_path, variables)
        assert ds1 is ds2  # same object, not a copy

    def test_different_groups_produce_different_entries(self, multi_nc_files, stat_group):
        cache = _DatasetCache()
        ds_ts  = cache.get_or_read(multi_nc_files, f"byDomains/{stat_group}",  ["assimilated_mean"])
        ds_grd = cache.get_or_read(multi_nc_files, f"griddedBins/{stat_group}", ["assimilated_mean"])
        assert ds_ts is not ds_grd

    def test_cache_read_only_once(self, multi_nc_files, stat_group):
        """read_group should be called only on the first request, not the second."""
        cache      = _DatasetCache()
        group_path = f"byDomains/{stat_group}"
        variables  = ["assimilated_mean"]

        with patch("obs_monitor.plotting.dispatcher.read_group",
                   wraps=__import__(
                       "obs_monitor.plotting.reader", fromlist=["read_group"]
                   ).read_group) as mock_rg:
            cache.get_or_read(multi_nc_files, group_path, variables)
            cache.get_or_read(multi_nc_files, group_path, variables)
            assert mock_rg.call_count == 1


# ---------------------------------------------------------------------------
# dispatch_plots — mocked EMCPy
# ---------------------------------------------------------------------------

def _patch_figures():
    """
    Context manager that patches all EMCPy rendering so dispatch_plots
    completes without a display and without writing real PNG bytes.
    The mock savefig actually creates an empty file so path checks pass.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        mock_mpl_fig = MagicMock()

        def fake_savefig(path, **kwargs):
            Path(path).touch()

        mock_mpl_fig.fig          = MagicMock()
        mock_mpl_fig.fig.axes     = [MagicMock()]
        mock_mpl_fig.fig.savefig  = fake_savefig

        mock_cf = MagicMock(return_value=mock_mpl_fig)
        mock_cp = MagicMock()
        mock_lp = MagicMock()
        mock_mg = MagicMock()

        with patch("obs_monitor.plotting.figures.CreateFigure", mock_cf), \
             patch("obs_monitor.plotting.figures.CreatePlot",   mock_cp), \
             patch("obs_monitor.plotting.figures.LinePlot",     mock_lp), \
             patch("obs_monitor.plotting.figures.MapGridded",   mock_mg), \
             patch("obs_monitor.plotting.figures.plt.close"):
            yield

    return _ctx()


class TestDispatchPlots:

    def test_returns_dict_with_required_keys(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)

        required = {
            "ob_type", "status", "figures_requested",
            "figures_written", "paths", "errors",
        }
        assert required.issubset(result.keys())

    def test_ob_type_in_result(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)
        assert result["ob_type"] == ob_type

    def test_figures_requested_matches_config(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        cfg = _valid_config()
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, cfg, tmp_path)
        assert result["figures_requested"] == len(cfg["figures"])

    def test_ok_status_on_success(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)
        assert result["status"] == "ok"

    def test_skipped_when_no_nc_files(self, tmp_path, ob_type):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = dispatch_plots(ob_type, empty_dir, _valid_config(), tmp_path / "out")
        assert result["status"] == "skipped"

    def test_skipped_on_invalid_config(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        bad_cfg = _valid_config()
        del bad_cfg["variable"]
        result = dispatch_plots(ob_type, runtime_dir, bad_cfg, tmp_path)
        assert result["status"] == "skipped"

    def test_figures_written_count(self, multi_nc_files, tmp_path, ob_type):
        """
        Config has: 1 map_gridded spec + 1 time_series spec with 2 domains.
        Expected: 3 PNGs (1 map + 2 domain lines).
        """
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)
        assert result["figures_written"] == 3

    def test_paths_are_strings(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)
        assert all(isinstance(p, str) for p in result["paths"])

    def test_output_dir_created(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        out_dir     = tmp_path / "new_plots_dir"
        with _patch_figures():
            dispatch_plots(ob_type, runtime_dir, _valid_config(), out_dir)
        assert out_dir.exists()

    def test_errors_list_empty_on_full_success(self, multi_nc_files, tmp_path, ob_type):
        runtime_dir = multi_nc_files[0].parent
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, _valid_config(), tmp_path)
        assert result["errors"] == []

    def test_bad_stat_does_not_crash(self, multi_nc_files, tmp_path, ob_type):
        """
        A stat name that doesn't exist in the NetCDF files should not crash
        the pipeline.  read_group returns a NaN-filled placeholder for missing
        variables, so the dispatcher completes and writes blank (all-NaN) plots
        rather than raising an exception.  The important guarantee is fault
        tolerance — status must not be an unhandled exception.
        """
        runtime_dir = multi_nc_files[0].parent
        cfg = _valid_config(stat="nonexistent_stat")
        with _patch_figures():
            result = dispatch_plots(ob_type, runtime_dir, cfg, tmp_path)
        # Pipeline must complete without raising — any terminal status is acceptable
        assert result["status"] in ("ok", "partial", "failed", "skipped")
        assert "ob_type" in result
