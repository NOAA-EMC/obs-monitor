"""Tests for figures from summaries (obs_monitor.plotting.summary_figures) and figure specs (config.figures)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr
import yaml

import obs_monitor.stats as stats
from obs_monitor.config import ConfigError, load_default_figures, load_obs_spaces
from obs_monitor.config import figures as figcfg
from obs_monitor.config.figures import parse_figure_spec
from obs_monitor.plotting import summary_figures as sf
from obs_monitor.plotting.summary_figures import gridded_dataset, plot_obs_space, time_series_dataset

DOMAINS, GRID = stats.load_regions()
CYCLES = [datetime(2026, 10, 11) + timedelta(hours=6 * i) for i in range(4)]


def summary(cycle, ombg, lat=10.0, lon=0.0, qc=0, oman=True):
    """One-cycle summary from a few obs at one location."""
    ombg = np.asarray(ombg, float)
    data = {"obs": ("Location", ombg + 1000), "ombg": ("Location", ombg),
            "qc_bg": ("Location", np.full(ombg.size, qc, np.int32))}
    if oman:
        data["oman"] = ("Location", ombg / 2)
    ds = xr.Dataset(data, coords={"latitude": ("Location", np.full(ombg.size, lat)),
                                  "longitude": ("Location", np.full(ombg.size, lon))},
                    attrs={"obs_space": "prepbufr_adpsfc", "variable": "stationPressure", "units": "Pa"})
    return stats.reduce_cycle(ds, cycle, DOMAINS, GRID)


@pytest.fixture
def stacked():
    # cycle 2 missing -> gap
    sums = {CYCLES[0]: summary(CYCLES[0], [1.0]),
            CYCLES[1]: summary(CYCLES[1], [3.0, 3.0, 3.0]),
            CYCLES[3]: summary(CYCLES[3], [-2.0])}
    return stats.stack_cycles(sums, CYCLES)


def latest_points(n=400, seed=3, channel=False):
    """(cycle, read_ioda-like Dataset) for the latest-cycle maps."""
    rng = np.random.default_rng(seed)
    qc_bg = rng.choice([-1, 0, 1, 2, 10], n)
    ombg = rng.normal(0, 50, n)
    ombg[:5] = np.nan
    data = {"obs": ("Location", rng.normal(1e5, 500, n)), "ombg": ("Location", ombg),
            "oman": ("Location", rng.normal(0, 40, n)), "qc_bg": ("Location", qc_bg),
            "qc_an": ("Location", rng.choice([0, 1, 2], n))}
    ds = xr.Dataset(data, coords={"latitude": ("Location", rng.uniform(-80, 80, n)),
                                  "longitude": ("Location", rng.uniform(-179, 179, n))},
                    attrs={"obs_space": "x", "variable": "stationPressure", "units": "Pa"})
    if channel:                                       # data vars get a size-1 channel dim; lat/lon stay 1-D
        ds = ds.expand_dims(channel=[4], axis=-1)
    return CYCLES[-1], ds


@pytest.fixture
def no_coastlines():
    """Coastlines need a cartopy download; not available in CI."""
    with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda self, *a, **k: None):
        yield


# ---------------------------------------------------------------------------
# Figure specs
# ---------------------------------------------------------------------------

class TestFigureSpecs:

    def test_defaults_reproduce_website_set(self):
        specs = load_default_figures()
        assert [(s.type, s.field, s.stat, s.qc) for s in specs[:4]] == [
            ("time_series", "ombg", "mean", "assimilated"),
            ("time_series", "oman", "mean", "assimilated"),
            ("map_gridded", "ombg", "mean", "assimilated"),
            ("map_gridded", "oman", "mean", "assimilated"),
        ]
        assert specs[0].domains == ("Global", "NH", "SH", "CONUS")
        assert [(s.type, s.field, s.qc, s.qcs, s.domains) for s in specs[4:]] == [
            ("count_series", "ombg", "", ("all", "assimilated", "monitored", "rejected"), ("Global",)),
            ("coverage_map", "ombg", "", ("assimilated",), None),
            ("scatter_map", "ombg", "assimilated", (), None),
            ("scatter_map", "oman", "assimilated", (), None),
        ]

    def test_names_mirror_stats_package(self):
        assert figcfg.FIELDS == tuple(stats.FIELD_QC)
        assert figcfg.STATS == stats.STATS
        assert figcfg.QC_CLASSES == stats.QC_CLASSES

    @pytest.mark.parametrize("spec, match", [
        ({"type": "histogram", "field": "ombg", "stat": "mean", "qc": "all"}, "type must be"),
        ({"type": "time_series", "field": "omb", "stat": "mean", "qc": "all"}, "field must be"),
        ({"type": "time_series", "field": "ombg", "stat": "median", "qc": "all"}, "stat for time_series"),
        ({"type": "map_gridded", "field": "ombg", "stat": "rms", "qc": "assimilated"}, "stat for map_gridded"),
        ({"type": "map_gridded", "field": "ombg", "stat": "mean", "qc": "rejected"}, "qc for map_gridded"),
        ({"type": "time_series", "field": "ombg", "stat": "mean"}, "missing"),
        ({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "all", "domain": ["NH"]}, "unknown key"),
        ({"type": "map_gridded", "field": "ombg", "stat": "mean", "qc": "assimilated", "domains": ["NH"]},
         "unknown key"),
        ({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "all", "domains": "NH"}, "domains"),
    ])
    def test_invalid(self, spec, match):
        with pytest.raises(ConfigError, match=match):
            parse_figure_spec(spec, "test")

    def test_options_kept(self):
        s = parse_figure_spec({"type": "map_gridded", "field": "oman", "stat": "mean", "qc": "assimilated",
                               "cmap": "viridis", "title": "T"}, "test")
        assert s.options == {"cmap": "viridis", "title": "T"}

    def test_obs_space_override(self, tmp_path):
        f = tmp_path / "x.yaml"
        f.write_text(yaml.safe_dump({"obs_spaces": {"viirs_npp": {
            "component": "chem",
            "figures": [{"type": "time_series", "field": "oman", "stat": "mean", "qc": "assimilated",
                         "domains": ["Global"]}]}}}))
        o = load_obs_spaces(f)["viirs_npp"]
        assert len(o.figures) == 1 and o.figures[0].domains == ("Global",)
        assert load_obs_spaces()["prepbufr_adpsfc"].figures is None      # uses defaults

    def test_obs_space_bad_figures(self, tmp_path):
        f = tmp_path / "x.yaml"
        f.write_text(yaml.safe_dump({"obs_spaces": {"x": {"component": "atmos", "figures": []}}}))
        with pytest.raises(ConfigError, match="figures"):
            load_obs_spaces(f)


# ---------------------------------------------------------------------------
# Summary -> figure Datasets
# ---------------------------------------------------------------------------

class TestDatasets:

    def test_time_series_shape_and_gap(self, stacked):
        ds = time_series_dataset(stacked, "ombg", "mean", "assimilated")
        assert ds["assimilated_mean"].dims == ("analysisCycle", "dim_0")
        assert list(ds["statisticDomain"].values) == [d.name for d in DOMAINS]
        g = ds["assimilated_mean"].values[:, [d.name for d in DOMAINS].index("Global")]
        assert g[0] == 1.0 and g[1] == 3.0 and np.isnan(g[2]) and g[3] == -2.0

    def test_time_series_other_stat_and_class(self, stacked):
        ds = time_series_dataset(stacked, "ombg", "count", "rejected")
        assert "rejected_count" in ds and np.nansum(ds["rejected_count"].values) == 0

    def test_gridded_mean_is_count_weighted(self, stacked):
        ds = gridded_dataset(stacked, "ombg", "mean", "assimilated")
        v = ds["assimilated_mean"].values
        finite = v[np.isfinite(v)]
        # all obs in one box: (1*1 + 3*3 + (-2)*1) / 5 = 1.6 ; unweighted mean of cycle means would be 0.667
        assert finite.size == 1 and finite[0] == pytest.approx(1.6)
        assert int(ds["n_cycles"]) == 3
        assert ds["latitude"].shape == (72, 144) and ds["longitude"].shape == (72, 144)

    def test_gridded_count_total(self, stacked):
        v = gridded_dataset(stacked, "ombg", "count", "assimilated")["assimilated_count"].values
        assert np.nansum(v) == 5 and np.isnan(v).sum() == v.size - 1

    def test_gridded_wrong_qc(self, stacked):
        with pytest.raises(ValueError, match="gridded fields"):
            gridded_dataset(stacked, "ombg", "mean", "rejected")

    def test_missing_field(self):
        st = stats.stack_cycles({CYCLES[0]: summary(CYCLES[0], [1.0], oman=False)}, CYCLES[:1])
        with pytest.raises(KeyError):
            time_series_dataset(st, "oman", "mean", "assimilated")


# ---------------------------------------------------------------------------
# plot_obs_space (real rendering with EMCPy)
# ---------------------------------------------------------------------------

class TestPlotObsSpace:

    def test_default_figures_and_names(self, stacked, tmp_path, no_coastlines):
        r = plot_obs_space(stacked, "prepbufr_adpsfc", load_default_figures(), tmp_path, latest=latest_points())
        names = sorted(p.name for p in r.written)
        expected = sorted(
            [f"prepbufr_adpsfc_stationPressure_assimilated_mean_{f}_{d}_timeseries.png"
             for f in ("ombg", "oman") for d in ("Global", "NH", "SH", "CONUS")]
            + [f"prepbufr_adpsfc_stationPressure_assimilated_mean_{f}_map.png" for f in ("ombg", "oman")]
            + ["prepbufr_adpsfc_stationPressure_count_ombg_Global_timeseries.png",
               "prepbufr_adpsfc_stationPressure_coverage_map.png",
               "prepbufr_adpsfc_stationPressure_assimilated_scatter_ombg_map.png",
               "prepbufr_adpsfc_stationPressure_assimilated_scatter_oman_map.png"])
        assert names == expected
        assert not r.failed and not r.skipped

    def test_latest_maps_skipped_without_a_diag_file(self, stacked, tmp_path, no_coastlines):
        r = plot_obs_space(stacked, "x", load_default_figures(), tmp_path)
        assert len(r.written) == 11
        assert [d for d, why in r.skipped] == ["coverage_map ombg assimilated",
                                               "scatter_map ombg assimilated", "scatter_map oman assimilated"]
        assert all("no diag file" in why for d, why in r.skipped)
        assert all(p.stat().st_size > 1000 for p in r.written)

    def test_web_name_used(self, stacked, tmp_path):
        spec = parse_figure_spec({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "assimilated",
                                  "domains": ["Global"]}, "t")
        r = plot_obs_space(stacked, "adpsfc_web", [spec], tmp_path)
        assert [p.name for p in r.written] == ["adpsfc_web_stationPressure_assimilated_mean_ombg_Global_timeseries.png"]

    def test_unknown_domain_skipped(self, stacked, tmp_path):
        spec = parse_figure_spec({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "assimilated",
                                  "domains": ["Global", "Mars"]}, "t")
        r = plot_obs_space(stacked, "x", [spec], tmp_path)
        assert len(r.written) == 1
        assert r.skipped == [("time_series ombg assimilated mean Mars", "domain not in regions.yaml")]

    def test_missing_field_skipped_not_failed(self, tmp_path):
        st = stats.stack_cycles({CYCLES[0]: summary(CYCLES[0], [1.0], oman=False)}, CYCLES[:1])
        r = plot_obs_space(st, "x", load_default_figures()[:2], tmp_path)
        assert len(r.written) == 4 and len(r.skipped) == 1 and not r.failed

    def test_no_data(self, tmp_path):
        r = plot_obs_space(None, "x", load_default_figures(), tmp_path)
        assert not r.written and len(r.skipped) == 8

    def test_one_failure_does_not_stop_others(self, stacked, tmp_path, no_coastlines):
        real = sf.build_figure

        def flaky(ftype, *a, **k):
            if ftype == "map_gridded":
                raise RuntimeError("boom")
            return real(ftype, *a, **k)

        with patch.object(sf, "build_figure", flaky):
            r = plot_obs_space(stacked, "x", load_default_figures(), tmp_path, latest=latest_points())
        assert len(r.written) == 12 and len(r.failed) == 2 and "boom" in r.failed[0][1]

    def test_save_failure_reported(self, stacked, tmp_path):
        spec = parse_figure_spec({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "assimilated",
                                  "domains": ["Global"]}, "t")
        with patch("matplotlib.figure.Figure.savefig", side_effect=OSError("disk full")):
            r = plot_obs_space(stacked, "x", [spec], tmp_path)
        assert not r.written and len(r.failed) == 1 and "disk full" in r.failed[0][1]


def test_single_channel_plotted_multi_channel_skipped(stacked, tmp_path):
    spec = parse_figure_spec({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "assimilated",
                              "domains": ["Global"]}, "t")
    one = stacked.expand_dims(channel=[4]).transpose("cycle", "channel", ...)
    assert len(plot_obs_space(one, "x", [spec], tmp_path / "one").written) == 1
    two = xr.concat([stacked, stacked], dim=xr.DataArray([1, 2], dims="channel", name="channel"))
    r = plot_obs_space(two, "x", [spec], tmp_path / "two")
    assert not r.written and r.skipped and "not implemented" in r.skipped[0][1]


# ---------------------------------------------------------------------------
# New figure types: count_series, coverage_map, scatter_map
# ---------------------------------------------------------------------------

class TestNewFigureSpecs:

    @pytest.mark.parametrize("spec, match", [
        ({"type": "count_series"}, "missing"),
        ({"type": "count_series", "field": "ombg", "qc": ["assimilated", "bogus"]}, "list of distinct"),
        ({"type": "count_series", "field": "ombg", "qc": ["all", "all"]}, "list of distinct"),
        ({"type": "count_series", "field": "ombg", "stat": "mean"}, "unknown key"),
        ({"type": "count_series", "field": "ombg", "log_scale": "yes"}, "log_scale"),
        ({"type": "coverage_map", "domains": ["Global"]}, "unknown key"),
        ({"type": "coverage_map", "marker_size": 0}, "marker_size"),
        ({"type": "scatter_map", "field": "ombg"}, "missing"),
        ({"type": "scatter_map", "field": "ombg", "qc": ["assimilated"]}, "qc for scatter_map"),
    ])
    def test_invalid(self, spec, match):
        with pytest.raises(ConfigError, match=match):
            parse_figure_spec(spec, "t")

    def test_qc_accepts_single_class(self):
        assert parse_figure_spec({"type": "count_series", "field": "ombg", "qc": "rejected"}, "t").qcs == ("rejected",)

    def test_latest_flag(self):
        assert parse_figure_spec({"type": "coverage_map"}, "t").latest
        assert parse_figure_spec({"type": "scatter_map", "field": "ombg", "qc": "all"}, "t").latest
        assert not parse_figure_spec({"type": "count_series", "field": "ombg"}, "t").latest


class TestNewFigureData:

    def test_count_series_dataset(self, stacked):
        ds = sf.count_series_dataset(stacked, "ombg", ("all", "assimilated"))
        assert list(ds.data_vars) == ["all", "assimilated"]
        assert ds["all"].dims == ("analysisCycle", "dim_0")
        np.testing.assert_array_equal(
            ds["assimilated"].values,
            stacked["ombg_count"].sel(qc_class="assimilated").transpose("cycle", "domain").values.astype(float))

    def test_latest_points_match_summary_qc_classes(self):
        """Coverage-map classes use exactly the summaries' QC rules."""
        cycle, raw = latest_points()
        pts = sf.latest_points_dataset(raw, "ombg", cycle)
        domains, grid = stats.load_regions()
        summ = stats.reduce_cycle(raw, cycle, domains, grid)
        for qc in stats.QC_CLASSES:
            assert int(pts[qc].sum()) == int(summ["ombg_count"].sel(qc_class=qc, domain="Global"))
        assert pts.attrs["cycle"] == f"{cycle:%Y%m%d%H}"
        v = pts["assimilated_ombg"].values
        assert np.isfinite(v).sum() == int(pts["assimilated"].sum())

    def test_latest_points_single_channel_squeezed(self):
        cycle, raw = latest_points(channel=True)
        assert "channel" not in sf.latest_points_dataset(raw, "ombg", cycle).dims

    def test_latest_points_multi_channel_not_yet(self):
        cycle, raw = latest_points()
        raw = xr.concat([raw.expand_dims(channel=[1]), raw.expand_dims(channel=[2])], dim="channel")
        with pytest.raises(ValueError, match="multi-channel"):
            sf.latest_points_dataset(raw, "ombg", cycle)


class TestNewFigureRendering:

    def test_count_series_one_png_per_domain(self, stacked, tmp_path):
        spec = parse_figure_spec({"type": "count_series", "field": "ombg", "domains": ["Global", "NH"],
                                  "log_scale": True}, "t")
        r = plot_obs_space(stacked, "adpsfc", [spec], tmp_path)
        assert sorted(p.name for p in r.written) == [
            "adpsfc_stationPressure_count_ombg_Global_timeseries.png",
            "adpsfc_stationPressure_count_ombg_NH_timeseries.png"]

    def test_coverage_map_qc_colours(self, stacked, tmp_path, no_coastlines):
        spec = parse_figure_spec({"type": "coverage_map", "qc": ["assimilated", "monitored", "rejected"]}, "t")
        captured = {}
        real_save = sf.build_figure

        def keep(*a, **k):
            fig = real_save(*a, **k)
            render = fig._render
            fig._render = lambda: captured.setdefault("pairs", render())
            return fig

        with patch.object(sf, "build_figure", keep):
            r = plot_obs_space(stacked, "adpsfc", [spec], tmp_path, latest=latest_points())
        assert [p.name for p in r.written] == ["adpsfc_stationPressure_coverage_map.png"]
        (mpl_fig, _), = captured["pairs"]
        from matplotlib.colors import to_hex
        from obs_monitor.plotting.figures import QC_COLORS
        colours = {c.get_label().split(" ")[0]: to_hex(c.get_facecolor()[0])
                   for ax in mpl_fig.axes for c in ax.collections if c.get_label()}
        assert colours == {qc: QC_COLORS[qc].lower() for qc in ("assimilated", "monitored", "rejected")}
        ax = next(a for a in mpl_fig.axes if a.collections)
        drawn = [c.get_label().split(" ")[0] for c in ax.collections if c.get_label()]
        assert drawn == ["rejected", "monitored", "assimilated"]                 # first listed drawn last = on top
        legend = [t.get_text().split(" ")[0] for t in ax.get_legend().get_texts()]
        assert legend == ["assimilated", "monitored", "rejected"]               # legend in the order listed

    def test_coverage_map_default_is_assimilated_only(self, stacked, tmp_path, no_coastlines):
        spec = parse_figure_spec({"type": "coverage_map"}, "t")
        assert spec.qcs == ("assimilated",)
        with patch.object(sf, "build_figure", wraps=sf.build_figure) as bf:
            r = plot_obs_space(stacked, "adpsfc", [spec], tmp_path, latest=latest_points())
        assert len(r.written) == 1
        assert bf.call_args.args[2]["title"] == "{ob_type} coverage, assimilated obs, {cycle}"

    def test_scatter_map_limits_value(self):
        from obs_monitor.plotting.figures import ScatterMapFigure
        cycle, raw = latest_points()
        raw["ombg"].values[10] = 1e6
        pts = sf.latest_points_dataset(raw, "ombg", cycle)
        fig = ScatterMapFigure(pts, {"field": "ombg"}, "x", "stationPressure", "all_ombg", "/tmp")
        with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda *a, **k: None), \
                patch("obs_monitor.plotting.figures._map_figure") as mf:
            fig._render()
        layer = mf.call_args.args[0][0]
        finite = np.abs(pts["all_ombg"].values[np.isfinite(pts["all_ombg"].values)])
        assert layer.vmax == pytest.approx(np.percentile(finite, 98)) and layer.vmin == -layer.vmax
        assert layer.vmax < 1e6

    def test_scatter_map_obs_uses_full_range(self):
        from obs_monitor.plotting.figures import ScatterMapFigure
        cycle, raw = latest_points()
        pts = sf.latest_points_dataset(raw, "obs", cycle)
        fig = ScatterMapFigure(pts, {"field": "obs"}, "x", "stationPressure", "all_obs", "/tmp")
        with patch("obs_monitor.plotting.figures._map_figure") as mf:
            fig._render()
        layer = mf.call_args.args[0][0]
        assert layer.vmin is None and layer.vmax is None and layer.cmap == "viridis"

    def test_empty_class_draws_nothing(self, tmp_path):
        from obs_monitor.plotting.figures import ScatterMapFigure
        cycle, raw = latest_points()
        raw["qc_bg"].values[:] = 0                                            # nothing rejected
        pts = sf.latest_points_dataset(raw, "ombg", cycle)
        assert ScatterMapFigure(pts, {"field": "ombg"}, "x", "v", "rejected_ombg", tmp_path)._render() == []
