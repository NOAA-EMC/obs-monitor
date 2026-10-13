"""End to end: run config -> COM tarball -> catalog -> read_ioda, on a realistic synthetic diag file."""

from __future__ import annotations

import tarfile
from datetime import datetime

from obs_monitor.config import RunConfig
from obs_monitor.io.catalog import build_inventory
from obs_monitor.io.ioda import read_ioda

from ioda_fixtures import write_adpsfc, write_atms


def test_run_config_to_dataset(tmp_path):
    cycle = datetime(2026, 10, 1, 0)
    staging = tmp_path / "staging"
    adpsfc = staging / "diag_prepbufr_adpsfc_2026100100.nc"
    atms = staging / "diag_radiance_atms_n20_2026100100.nc"
    w = write_adpsfc(adpsfc, cycle=cycle)
    write_atms(atms, cycle=cycle)

    comroot = tmp_path / "COMROOT" / "prjedi"
    tar_dir = comroot / "gdas.20261001" / "00" / "analysis" / "atmos"
    tar_dir.mkdir(parents=True)
    with tarfile.open(tar_dir / "gdas.t00z.atmos_analysis.ioda_hofx.tar.gz", "w:gz") as tar:
        for p in (adpsfc, atms):
            tar.add(p, arcname=p.name)

    rc = RunConfig.from_dict({
        "cycles": {"start": 2026100100, "end": 2026100100},
        "source": {"type": "com", "comroot": str(comroot)},
        "obs_spaces": ["prepbufr_adpsfc", "radiance_atms_n20"],
        "output_dir": str(tmp_path / "out"),
        "work_dir": str(tmp_path / "work"),
    })
    inv = build_inventory(rc.locators, rc.cycles, rc.obs_space_names)
    assert inv.coverage("prepbufr_adpsfc") == 1.0 and inv.coverage("radiance_atms_n20") == 1.0

    obs_space = {o.name: o for o in rc.obs_spaces}["prepbufr_adpsfc"]
    for var in obs_space.variables:
        ds = read_ioda(inv.path("prepbufr_adpsfc", cycle), var, obs_space=obs_space.name,
                       group_map=obs_space.group_map)
        assert ds.attrs["obs_space"] == "prepbufr_adpsfc"
        assert ds.sizes["Location"] == w["n"]

    rad = read_ioda(inv.path("radiance_atms_n20", cycle), "brightnessTemperature", channels=[1, 7])
    assert list(rad["channel"].values) == [1, 7]
