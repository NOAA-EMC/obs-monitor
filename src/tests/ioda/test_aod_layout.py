"""VIIRS AOD diag layout (Channel dimension of size 1) through reader, stats and figures."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from obs_monitor.config import load_obs_spaces
from obs_monitor.io import list_simulated_variables, read_ioda
from obs_monitor.plotting.summary_figures import plot_obs_space
from obs_monitor.stats import load_regions, reduce_cycle, stack_cycles

from ioda_fixtures import write_aod

CYCLES = [datetime(2024, 5, 14) + timedelta(hours=6 * i) for i in range(3)]


def test_aod_reads_and_reduces(tmp_path):
    p = tmp_path / "diag_retrieval_aod_viirs_npp_2024051400.nc"
    w = write_aod(p, cycle=CYCLES[0])
    assert list_simulated_variables(p) == ["aerosolOpticalDepth"]
    ds = read_ioda(p, "aerosolOpticalDepth")
    assert list(ds["channel"].values) == [w["channel"]]
    domains, grid = load_regions()
    s = reduce_cycle(ds, CYCLES[0], domains, grid)
    assert int(s["oman_count"].sel(channel=w["channel"], qc_class="assimilated", domain="Global")) == \
        int((w["qc"] == 0).sum())


def test_aod_figures_keep_website_names(tmp_path):
    domains, grid = load_regions()
    sums = {}
    for c in CYCLES:
        p = tmp_path / f"diag_{c:%Y%m%d%H}.nc"
        write_aod(p, cycle=c)
        sums[c] = reduce_cycle(read_ioda(p, "aerosolOpticalDepth"), c, domains, grid)
    obs = load_obs_spaces()["retrieval_aod_viirs_npp"]
    with patch("emcpy.plots.create_plots.CreatePlot.add_map_features", lambda self, *a, **k: None):
        r = plot_obs_space(stack_cycles(sums, CYCLES), obs.label, obs.figures, tmp_path / "out")
    assert sorted(p.name for p in r.written) == [
        "viirs_npp_aerosolOpticalDepth_assimilated_mean_oman_Global_timeseries.png",
        "viirs_npp_aerosolOpticalDepth_assimilated_mean_oman_map.png",
    ]
    assert not r.failed and not r.skipped


def test_shipped_aod_spaces():
    spaces = load_obs_spaces()
    assert {spaces[f"retrieval_aod_viirs_{s}"].label for s in ("npp", "n20", "n21")} == \
        {"viirs_npp", "viirs_n20", "viirs_n21"}
    assert all(spaces[f"retrieval_aod_viirs_{s}"].component == "chem" for s in ("npp", "n20", "n21"))
