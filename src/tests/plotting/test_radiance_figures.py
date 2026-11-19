"""Radiance (multi-channel) figures: per-channel versions of every type and the website's sensor-page images."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr

from obs_monitor.config import ConfigError, RunConfig, load_obs_spaces
from obs_monitor.config.figures import parse_figure_spec, parse_figure_specs
from obs_monitor.config.obs_spaces import _parse_obs_space
from obs_monitor.pipelines.run import run_window
from obs_monitor.plotting import summary_figures as sf
from obs_monitor.plotting.naming import build_site_radiance_filename, channel_label, site_name
from obs_monitor.plotting.summary_figures import plot_obs_space
from obs_monitor.stats import load_regions, reduce_cycle, stack_cycles

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ioda"))
from ioda_fixtures import write_atms  # noqa: E402

CYCLES = [datetime(2026, 10, 11) + timedelta(hours=6 * i) for i in range(4)]
END = f"{CYCLES[-1]:%Y%m%d%H}"
NCH = 5


@pytest.fixture(autouse=True)
def no_coastlines():
    with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda self, *a, **k: None):
        yield


def fake_cycle(seed: int, n: int = 400, nch: int = NCH) -> xr.Dataset:
    """One cycle of radiance diag data (read_ioda shape) with channel-dependent bias and a QC mix."""
    rng = np.random.default_rng(seed)
    ch = np.arange(1, nch + 1)
    ombg = 0.1 * ch[None, :] + rng.normal(0, 0.5, (n, nch))
    dims = ("Location", "channel")
    return xr.Dataset(
        {"obs": (dims, 250 + rng.normal(0, 5, (n, nch))), "ombg": (dims, ombg), "oman": (dims, 0.5 * ombg),
         "qc_bg": (dims, rng.choice([0, 0, 1, 2], (n, nch))), "qc_an": (dims, rng.choice([0, 1, 2], (n, nch)))},
        coords={"latitude": ("Location", rng.uniform(-80, 80, n)),
                "longitude": ("Location", rng.uniform(-179, 179, n)), "channel": ch},
        attrs={"obs_space": "radiance_x", "variable": "brightnessTemperature", "units": "K"})


@pytest.fixture
def raw():
    return {c: fake_cycle(i) for i, c in enumerate(CYCLES) if i != 1}          # CYCLES[1] missing


@pytest.fixture
def stacked(raw):
    domains, grid = load_regions()
    return stack_cycles({c: reduce_cycle(d, c, domains, grid) for c, d in raw.items()}, CYCLES)


def specs(*items):
    return parse_figure_specs(list(items), "t")


# ---------------------------------------------------------------------------
# Names (the website contract for the sensor pages)
# ---------------------------------------------------------------------------

def test_site_names():
    assert site_name("rad/atms/noaa-20", "atms_n20") == "atms_noaa-20"
    assert site_name(None, "atms_n20") == "atms_n20"
    assert build_site_radiance_filename("channel_summary", "atms_noaa-20", END) == f"atms_noaa-20_summary_{END}.png"
    assert build_site_radiance_filename("channel_heatmap", "atms_noaa-20", END) == f"atms_noaa-20_time_{END}.png"
    assert build_site_radiance_filename("channel_series", "atms_noaa-20", END, 7) == f"atms_noaa-20_chan_7_{END}.png"
    assert channel_label("atms_n20", 7) == "atms_n20_ch7"


def test_shipped_atms_entry():
    atms = load_obs_spaces()["radiance_atms_n20"]
    assert atms.web_path == "rad/atms/noaa-20" and atms.label == "atms_n20"
    assert [s.type for s in atms.figures[:3]] == ["channel_summary", "channel_heatmap", "channel_series"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("web_path", ["/abs/path", "rad//atms", "rad/../x", "rad/at ms", "", 7])
def test_bad_web_path(web_path):
    with pytest.raises(ConfigError, match="web_path"):
        _parse_obs_space("x", {"component": "atmos", "web_path": web_path}, "t")


@pytest.mark.parametrize("spec, match", [
    ({"type": "channel_heatmap", "field": "ombg", "stat": "mean"}, "missing"),
    ({"type": "channel_heatmap", "field": "ombg", "stat": "median", "qc": "all"}, "stat"),
    ({"type": "channel_heatmap", "field": "ombg", "stat": "mean", "qc": "all", "channels": [1]}, "unknown key"),
    ({"type": "channel_summary", "channels": [1]}, "unknown key"),
    ({"type": "channel_summary", "domain": ["Global"]}, "domain"),
    ({"type": "channel_heatmap", "field": "ombg", "stat": "mean", "qc": "all", "annotate": "yes"}, "annotate"),
    ({"type": "channel_series", "channels": [0]}, "channels"),
    ({"type": "channel_series", "channels": [3, 3]}, "channels"),
    ({"type": "time_series", "field": "ombg", "stat": "mean", "qc": "all", "channels": []}, "channels"),
])
def test_invalid_specs(spec, match):
    with pytest.raises(ConfigError, match=match):
        parse_figure_spec(spec, "t")


def test_channels_option():
    spec = parse_figure_spec({"type": "map_gridded", "field": "ombg", "stat": "mean", "qc": "assimilated",
                              "channels": [3, 1]}, "t")
    assert spec.channels == (3, 1)
    assert parse_figure_spec({"type": "coverage_map"}, "t").channels is None


# ---------------------------------------------------------------------------
# Data for the sensor-page images
# ---------------------------------------------------------------------------

def test_channel_matrix(stacked):
    ds = sf.channel_matrix_dataset(stacked, "ombg", "mean", "assimilated", "Global")
    assert ds["value"].dims == ("channel", "cycle") and ds["value"].shape == (NCH, len(CYCLES))
    assert np.isnan(ds["value"].values[:, 1]).all()                          # missing cycle stays a gap


def test_channel_window_is_count_weighted(stacked, raw):
    ds = sf.channel_window_dataset(stacked, "assimilated", "Global")
    for i, ch in enumerate(range(1, NCH + 1)):
        vals = np.concatenate([d["ombg"].values[:, i][d["qc_bg"].values[:, i] == 0] for d in raw.values()])
        assert int(ds["count"].sel(channel=ch)) == vals.size
        assert float(ds["mean_ombg"].sel(channel=ch)) == pytest.approx(vals.mean(), rel=1e-9)


def test_channel_series(stacked):
    ds = sf.channel_series_dataset(stacked, 3, "assimilated", "Global")
    assert {"count_all", "count_assimilated", "count_monitored", "count_rejected",
            "mean_ombg", "mean_oman", "std_ombg"} <= set(ds.data_vars)
    assert ds["count_all"].dims == ("analysisCycle",) and np.isnan(ds["count_all"].values[1])


def test_unknown_domain_is_skipped(stacked, tmp_path):
    r = plot_obs_space(stacked, "x", specs({"type": "channel_summary", "domain": "Mars"}), tmp_path)
    assert not r.written and "Mars" in r.skipped[0][1]


def test_latest_points_by_channel(raw):
    ds = raw[CYCLES[-1]]
    pts = sf.latest_points_dataset(ds, "ombg", CYCLES[-1], channel=2)
    assert int(pts["assimilated"].sum()) == int((ds["qc_bg"].sel(channel=2).values == 0).sum())
    with pytest.raises(KeyError, match="channel 9"):
        sf.latest_points_dataset(ds, "ombg", CYCLES[-1], channel=9)
    with pytest.raises(ValueError, match="pass channel"):
        sf.latest_points_dataset(ds, "ombg", CYCLES[-1])


# ---------------------------------------------------------------------------
# plot_obs_space for a multi-channel obs space
# ---------------------------------------------------------------------------

def test_sensor_page_images(stacked, tmp_path):
    r = plot_obs_space(stacked, "atms_n20", specs({"type": "channel_summary"},
                                                  {"type": "channel_heatmap", "field": "ombg", "stat": "mean",
                                                   "qc": "assimilated"},
                                                  {"type": "channel_series", "channels": [2, 4]}),
                       tmp_path, site="atms_noaa-20")
    assert sorted(p.name for p in r.written) == sorted([
        f"atms_noaa-20_summary_{END}.png", f"atms_noaa-20_time_{END}.png",
        f"atms_noaa-20_chan_2_{END}.png", f"atms_noaa-20_chan_4_{END}.png"])
    assert not r.failed and not r.skipped


def test_every_type_per_channel(stacked, raw, tmp_path):
    r = plot_obs_space(stacked, "atms_n20", specs(
        {"type": "time_series", "field": "ombg", "stat": "mean", "qc": "assimilated", "domains": ["Global"]},
        {"type": "count_series", "field": "ombg"},
        {"type": "map_gridded", "field": "ombg", "stat": "mean", "qc": "assimilated"},
        {"type": "coverage_map"},
        {"type": "scatter_map", "field": "ombg", "qc": "assimilated"}), tmp_path, latest=(CYCLES[-1], raw[CYCLES[-1]]))
    names = {p.name for p in r.written}
    assert len(names) == 5 * NCH and not r.failed and not r.skipped
    for ch in range(1, NCH + 1):
        assert f"atms_n20_ch{ch}_brightnessTemperature_assimilated_mean_ombg_Global_timeseries.png" in names
        assert f"atms_n20_ch{ch}_brightnessTemperature_coverage_map.png" in names


def test_channel_subset_and_unknown_channel(stacked, tmp_path):
    r = plot_obs_space(stacked, "x", specs({"type": "count_series", "field": "ombg", "channels": [2, 99]}), tmp_path)
    assert [p.name for p in r.written] == ["x_ch2_brightnessTemperature_count_ombg_Global_timeseries.png"]
    assert r.skipped == [("count_series ombg all,assimilated,monitored,rejected count ch99",
                          "channel not in the summaries")]


def test_channel_types_skipped_without_channels(tmp_path):
    import test_summary_figures as tsf
    st = stack_cycles({c: tsf.summary(c, [1.0]) for c in tsf.CYCLES}, tsf.CYCLES)
    r = plot_obs_space(st, "x", specs({"type": "channel_summary"}), tmp_path)
    assert not r.written and r.skipped == [("channel_summary assimilated", "needs a multi-channel obs space")]


def test_heatmap_limits_and_gaps(stacked):
    from obs_monitor.plotting.figures import ChannelHeatmapFigure
    ds = sf.channel_matrix_dataset(stacked, "ombg", "mean", "assimilated", "Global")
    fig = ChannelHeatmapFigure(ds, {"diverging": True, "filename": "x.png"}, "x", "v", "s", "/tmp")
    with patch("obs_monitor.plotting.figures.CreatePlot") as cp, \
            patch("obs_monitor.plotting.figures.CreateFigure"):              # only the layer settings matter here
        pairs = fig._render()
    assert len(pairs) == 1 and pairs[0][1].name == "x.png"
    hm = cp.return_value.plot_layers[0]
    finite = np.abs(ds["value"].values[np.isfinite(ds["value"].values)])
    assert hm.vmax == pytest.approx(np.percentile(finite, 98)) and hm.vmin == -hm.vmax
    assert np.isnan(np.asarray(hm.data)[:, 1]).all()


# ---------------------------------------------------------------------------
# End to end: files land where the website looks
# ---------------------------------------------------------------------------

def test_run_window_writes_sensor_pages_to_web_path(tmp_path):
    for c in CYCLES:
        write_atms(tmp_path / "data" / f"diag_radiance_atms_n20_{c:%Y%m%d%H}.nc", cycle=c, n=60)
    rc = RunConfig.from_dict({
        "cycles": {"start": f"{CYCLES[0]:%Y%m%d%H}", "end": END},
        "source": {"type": "glob", "template": str(tmp_path / "data") + "/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"},
        "obs_spaces": ["radiance_atms_n20"], "output_dir": str(tmp_path / "out"), "work_dir": str(tmp_path / "w")})
    st = run_window(rc).obs_spaces[0]
    assert st.status == "ok" and not st.figures_failed, (st.figures_failed, st.figures_skipped)
    page = tmp_path / "out" / "rad" / "atms" / "noaa-20"
    names = {p.name for p in page.glob("*.png")}
    assert {f"atms_noaa-20_summary_{END}.png", f"atms_noaa-20_time_{END}.png",
            f"atms_noaa-20_chan_1_{END}.png", f"atms_noaa-20_chan_22_{END}.png"} <= names
    assert st.figures_written == len(names) and not list((tmp_path / "out").glob("*.png"))
