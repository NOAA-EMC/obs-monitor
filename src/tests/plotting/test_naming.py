"""
Pin the figure file names the website links to. If one of these fails, the
website breaks: change the web pages in the same release, or don't change the name.
"""

from __future__ import annotations

import pytest

from obs_monitor.plotting.naming import build_map_filename, build_timeseries_filename, stat_name

CONV_DOMAINS = ["Global", "NH", "SH", "CONUS"]


@pytest.mark.parametrize("ob_type", ["prepbufr_adpsfc", "prepbufr_adpupa", "prepbufr_sfcshp"])
@pytest.mark.parametrize("field", ["ombg", "oman"])
def test_conventional_names(ob_type, field):
    for domain in CONV_DOMAINS:
        assert build_timeseries_filename(ob_type, "stationPressure", "assimilated_mean", domain, label=field) == \
            f"{ob_type}_stationPressure_assimilated_mean_{field}_{domain}_timeseries.png"
    assert build_map_filename(ob_type, "stationPressure", "assimilated_mean", label=field) == \
        f"{ob_type}_stationPressure_assimilated_mean_{field}_map.png"


def test_exact_examples():
    # Spelled out in full so a reviewer can compare against the website by eye.
    assert build_timeseries_filename("prepbufr_adpsfc", "stationPressure", "assimilated_mean", "Global",
                                     label="ombg") == \
        "prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_Global_timeseries.png"
    assert build_map_filename("prepbufr_adpsfc", "stationPressure", "assimilated_mean", label="oman") == \
        "prepbufr_adpsfc_stationPressure_assimilated_mean_oman_map.png"


@pytest.mark.parametrize("ob_type", ["viirs_npp", "viirs_n20"])
def test_viirs_names(ob_type):
    assert build_timeseries_filename(ob_type, "aerosolOpticalDepth", "assimilated_mean", "Global", label="oman") == \
        f"{ob_type}_aerosolOpticalDepth_assimilated_mean_oman_Global_timeseries.png"
    assert build_map_filename(ob_type, "aerosolOpticalDepth", "assimilated_mean", label="oman") == \
        f"{ob_type}_aerosolOpticalDepth_assimilated_mean_oman_map.png"


@pytest.mark.parametrize("field", ["ombg", "oman"])
def test_snow_names(field):
    assert build_timeseries_filename("snocvr", "totalSnowDepth", "assimilated_mean", "Global", label=field) == \
        f"snocvr_totalSnowDepth_assimilated_mean_{field}_Global_timeseries.png"
    assert build_map_filename("snocvr", "totalSnowDepth", "assimilated_mean", label=field) == \
        f"snocvr_totalSnowDepth_assimilated_mean_{field}_map.png"


def test_stat_name_matches_old_stat_file_variables():
    assert stat_name("assimilated", "mean") == "assimilated_mean"
    assert stat_name("rejected", "rms") == "rejected_rms"
