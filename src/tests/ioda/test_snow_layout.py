"""Snow diag layouts (IMS, SNOMAD, sfcsno) through the reader and the stats step."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from obs_monitor.io import list_simulated_variables, read_ioda
from obs_monitor.stats import load_regions, reduce_cycle

from ioda_fixtures import write_snow

CYCLE = datetime(2024, 12, 19, 0)


@pytest.mark.parametrize("ims", [True, False])
def test_snow_reads_and_reduces(tmp_path, ims):
    p = tmp_path / ("diag_ims_snow_2024121900.nc" if ims else "diag_snocvr_snomad_2024121900.nc")
    w = write_snow(p, cycle=CYCLE, ims=ims)
    assert list_simulated_variables(p) == ["totalSnowDepth"]       # snowCoverFraction is not simulated
    ds = read_ioda(p, "totalSnowDepth")
    # dateTime decoded from the file's own epoch (IMS counts from the cycle, not 1970)
    expected = np.datetime64(CYCLE, "ns") + w["offsets"].astype("timedelta64[s]")
    np.testing.assert_array_equal(ds["dateTime"].values, expected)
    assert ds.attrs["units"] == "mm"
    domains, grid = load_regions()
    s = reduce_cycle(ds, CYCLE, domains, grid)
    assert int(s["ombg_count"].sel(qc_class="assimilated", domain="Global")) == int((w["qc"] == 0).sum())
