"""
tests/plotting/test_figures.py
================================

Unit tests for ``obs_monitor.plotting.figures``.

EMCPy's rendering classes (``CreateFigure``, ``CreatePlot``, ``LinePlot``,
``MapGridded``) are mocked throughout so these tests run cleanly in CI
without a display or a full EMCPy + cartopy installation.

What is tested (without EMCPy rendering):
  - ``build_figure`` registry lookup and correct class instantiation
  - ``build_figure`` raises ValueError for unknown types
  - Filename construction helpers
  - Domain resolution logic (all domains, subset, missing label warning)
  - ``TimeSeriesFigure.save`` writes one PNG per requested domain
  - ``MapGriddedFigure.save`` writes one PNG per spec
  - Missing stat variable → empty return, no exception
  - Missing lat/lon coords → empty return, no exception
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from obs_monitor.plotting.figures import (
    FigureBase,
    TimeSeriesFigure,
    MapGriddedFigure,
    build_figure,
    FIGURE_REGISTRY,
    build_timeseries_filename,
    build_map_filename,
)

from conftest import DOMAINS, N_DOMAINS, BINS_Y, BINS_X


# ---------------------------------------------------------------------------
# Helpers — minimal prepared Datasets
# ---------------------------------------------------------------------------

def _domain_ds(n_cycles: int = 4, domains: list[str] = DOMAINS) -> xr.Dataset:
    """Minimal time-series Dataset as returned by prepare_time_series."""
    times = np.array(
        [np.datetime64(f"2025-11-13T{h*6:02d}:00:00", "ns") for h in range(n_cycles)]
    )
    data  = np.random.default_rng(0).uniform(-100, 100, (n_cycles, len(domains)))
    ds    = xr.Dataset(
        {"assimilated_mean": xr.Variable(("analysisCycle", "dim_0"), data)},
        coords={
            "analysisCycle":   times,
            "statisticDomain": xr.Variable("dim_0", np.array(domains, dtype=object)),
        },
    )
    return ds


def _gridded_ds() -> xr.Dataset:
    """Minimal gridded Dataset as returned by prepare_gridded."""
    lat_1d = np.linspace(-88.75,  88.75,  BINS_Y)
    lon_1d = np.linspace(-178.75, 178.75, BINS_X)
    lon2d, lat2d = np.meshgrid(lon_1d, lat_1d)
    data = np.random.default_rng(1).uniform(-200, 200, (BINS_Y, BINS_X))
    ds = xr.Dataset(
        {"assimilated_mean": xr.Variable(("dim_2", "dim_3"), data)},
        coords={
            "latitude":  xr.Variable(("dim_2", "dim_3"), lat2d),
            "longitude": xr.Variable(("dim_2", "dim_3"), lon2d),
        },
    )
    return ds


# ---------------------------------------------------------------------------
# Minimal spec dicts
# ---------------------------------------------------------------------------

TS_SPEC = {
    "type":    "time_series",
    "stat":    "assimilated_mean",
    "title":   "{ob_type} {stat} — {domain}",
    "y_label": "stationPressure (Pa)",
    "domains": ["Global", "CONUS"],
}

MAP_SPEC = {
    "type":           "map_gridded",
    "stat":           "assimilated_mean",
    "title":          "{ob_type} {variable} {stat} — Cycle Mean",
    "colorbar_label": "stationPressure (Pa)",
    "projection":     "plcarr",
    "domain":         "global",
    "cmap":           "coolwarm",
}


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

class TestFilenameHelpers:

    def test_timeseries_filename_format(self):
        name = build_timeseries_filename(
            "prepbufr_adpsfc", "stationPressure", "assimilated_mean", "Global"
        )
        assert name == "prepbufr_adpsfc_stationPressure_assimilated_mean_Global_timeseries.png"

    def test_map_filename_format(self):
        name = build_map_filename(
            "prepbufr_adpsfc", "stationPressure", "assimilated_mean"
        )
        assert name == "prepbufr_adpsfc_stationPressure_assimilated_mean_map.png"

    def test_timeseries_filename_safe_chars(self):
        """Special characters in inputs must be replaced with underscores."""
        name = build_timeseries_filename("ob/type", "var name", "stat.val", "dom-ain")
        assert "/" not in name
        assert " " not in name
        assert "." not in name

    def test_map_filename_ends_with_png(self):
        name = build_map_filename("prepbufr_adpsfc", "stationPressure", "assimilated_mean")
        assert name.endswith(".png")

    def test_timeseries_filename_ends_with_png(self):
        name = build_timeseries_filename(
            "prepbufr_adpsfc", "stationPressure", "assimilated_mean", "NH"
        )
        assert name.endswith(".png")


# ---------------------------------------------------------------------------
# build_figure registry
# ---------------------------------------------------------------------------

class TestBuildFigureRegistry:

    def test_time_series_returns_correct_class(self, tmp_path):
        ds  = _domain_ds()
        fig = build_figure(
            "time_series", ds, TS_SPEC, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        assert isinstance(fig, TimeSeriesFigure)

    def test_map_gridded_returns_correct_class(self, tmp_path):
        ds  = _gridded_ds()
        fig = build_figure(
            "map_gridded", ds, MAP_SPEC, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        assert isinstance(fig, MapGriddedFigure)

    def test_unknown_type_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown figure type"):
            build_figure(
                "zonal_mean", xr.Dataset(), {}, "ob", "var", "stat", tmp_path
            )

    def test_all_registry_keys_map_to_figure_base_subclasses(self):
        for key, cls in FIGURE_REGISTRY.items():
            assert issubclass(cls, FigureBase), (
                f"FIGURE_REGISTRY['{key}'] = {cls} is not a FigureBase subclass"
            )


# ---------------------------------------------------------------------------
# TimeSeriesFigure — domain resolution
# ---------------------------------------------------------------------------

class TestTimeSeriesDomainResolution:

    def _make_fig(self, spec: dict, ds: xr.Dataset | None = None, tmp_path=None):
        return TimeSeriesFigure(
            ds or _domain_ds(),
            spec,
            ob_type="prepbufr_adpsfc",
            variable="stationPressure",
            stat="assimilated_mean",
            output_dir=tmp_path or Path("/tmp"),
        )

    def test_requested_domains_resolved(self, tmp_path):
        fig     = self._make_fig(TS_SPEC, tmp_path=tmp_path)
        domains = fig._resolve_domains()
        labels  = [d for _, d in domains]
        assert "Global" in labels
        assert "CONUS"  in labels

    def test_unknown_domain_excluded_with_warning(self, tmp_path, caplog):
        import logging
        spec = {**TS_SPEC, "domains": ["Global", "Mars"]}
        fig  = self._make_fig(spec, tmp_path=tmp_path)
        with caplog.at_level(logging.WARNING, logger="obs_monitor.plotting.figures"):
            domains = fig._resolve_domains()
        labels = [d for _, d in domains]
        assert "Global" in labels
        assert "Mars"   not in labels
        assert "Mars" in caplog.text

    def test_none_domains_returns_all(self, tmp_path):
        spec    = {**TS_SPEC, "domains": None}
        fig     = self._make_fig(spec, tmp_path=tmp_path)
        domains = fig._resolve_domains()
        assert len(domains) == N_DOMAINS

    def test_missing_stat_returns_empty_render(self, tmp_path):
        spec = {**TS_SPEC, "stat": "nonexistent_stat"}
        fig  = TimeSeriesFigure(
            _domain_ds(), spec, "prepbufr_adpsfc",
            "stationPressure", "nonexistent_stat", tmp_path,
        )
        result = fig._render()
        assert result == []


# ---------------------------------------------------------------------------
# TimeSeriesFigure — save (EMCPy mocked)
# ---------------------------------------------------------------------------

EMCPY_TARGETS = [
    "obs_monitor.plotting.figures.LinePlot",
    "obs_monitor.plotting.figures.CreatePlot",
    "obs_monitor.plotting.figures.CreateFigure",
]


class TestTimeSeriesFigureSave:

    def _mock_emcpy(self):
        """Return a context manager that patches all three EMCPy classes."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            mock_fig  = MagicMock()
            mock_fig.fig = MagicMock()
            mock_fig.fig.axes = [MagicMock()]
            mock_fig.fig.savefig = MagicMock()

            mock_create_figure = MagicMock(return_value=mock_fig)
            mock_create_plot   = MagicMock()
            mock_line_plot     = MagicMock()

            with patch("obs_monitor.plotting.figures.CreateFigure", mock_create_figure), \
                 patch("obs_monitor.plotting.figures.CreatePlot",   mock_create_plot), \
                 patch("obs_monitor.plotting.figures.LinePlot",     mock_line_plot), \
                 patch("obs_monitor.plotting.figures.plt.close"):
                yield mock_fig

        return _ctx()

    def test_save_produces_one_file_per_domain(self, tmp_path):
        spec = {**TS_SPEC, "domains": ["Global", "CONUS"]}
        fig  = TimeSeriesFigure(
            _domain_ds(), spec, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        assert len(paths) == 2

    def test_save_filenames_contain_domain(self, tmp_path):
        spec  = {**TS_SPEC, "domains": ["Global", "CONUS"]}
        fig   = TimeSeriesFigure(
            _domain_ds(), spec, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        names = [p.name for p in paths]
        assert any("Global" in n for n in names)
        assert any("CONUS"  in n for n in names)

    def test_output_dir_created(self, tmp_path):
        new_dir = tmp_path / "plots" / "subdir"
        spec    = {**TS_SPEC, "domains": ["Global"]}
        fig     = TimeSeriesFigure(
            _domain_ds(), spec, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", new_dir,
        )
        with self._mock_emcpy():
            fig.save()
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# MapGriddedFigure — save (EMCPy mocked)
# ---------------------------------------------------------------------------

class TestMapGriddedFigureSave:

    def _mock_emcpy(self):
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            mock_fig = MagicMock()
            mock_fig.fig = MagicMock()
            mock_fig.fig.savefig = MagicMock()

            mock_create_figure = MagicMock(return_value=mock_fig)
            mock_create_plot   = MagicMock()
            mock_map_gridded   = MagicMock()

            with patch("obs_monitor.plotting.figures.CreateFigure", mock_create_figure), \
                 patch("obs_monitor.plotting.figures.CreatePlot",   mock_create_plot), \
                 patch("obs_monitor.plotting.figures.MapGridded",   mock_map_gridded), \
                 patch("obs_monitor.plotting.figures.plt.close"):
                yield mock_fig

        return _ctx()

    def test_save_produces_one_file(self, tmp_path):
        fig = MapGriddedFigure(
            _gridded_ds(), MAP_SPEC, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        assert len(paths) == 1

    def test_output_filename_contains_map(self, tmp_path):
        fig = MapGriddedFigure(
            _gridded_ds(), MAP_SPEC, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        assert "map" in paths[0].name

    def test_missing_stat_returns_no_paths(self, tmp_path):
        fig = MapGriddedFigure(
            _gridded_ds(), MAP_SPEC, "prepbufr_adpsfc",
            "stationPressure", "nonexistent_stat", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        assert paths == []

    def test_missing_coords_returns_no_paths(self, tmp_path):
        ds_no_coords = xr.Dataset(
            {"assimilated_mean": xr.Variable(("y", "x"), np.ones((BINS_Y, BINS_X)))}
        )
        fig = MapGriddedFigure(
            ds_no_coords, MAP_SPEC, "prepbufr_adpsfc",
            "stationPressure", "assimilated_mean", tmp_path,
        )
        with self._mock_emcpy():
            paths = fig.save()
        assert paths == []
