"""
Tests for obs_monitor.io.ioda against synthetic files that mirror real GDAS
JEDI diag layouts (see ioda_fixtures.py).
"""

from __future__ import annotations

import netCDF4 as nc4
import numpy as np
import pytest

from obs_monitor.io.ioda import (
    FIELDS,
    QC_MISSING,
    ChannelNotFoundError,
    IodaFormatError,
    VariableNotSimulatedError,
    list_simulated_variables,
    read_ioda,
    resolve_group_map,
)

from ioda_fixtures import ADPSFC_SIMULATED, write_adpsfc, write_atms


@pytest.fixture
def adpsfc(tmp_path):
    path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
    return path, write_adpsfc(path)


@pytest.fixture
def atms(tmp_path):
    path = tmp_path / "diag_radiance_atms_n20_2026093018.nc"
    return path, write_atms(path)


# ---------------------------------------------------------------------------
# list_simulated_variables
# ---------------------------------------------------------------------------

class TestListSimulatedVariables:

    def test_conventional_uses_ombg_not_obsvalue(self, adpsfc):
        path, _ = adpsfc
        assert list_simulated_variables(path) == sorted(ADPSFC_SIMULATED)

    def test_radiance(self, atms):
        path, _ = atms
        assert list_simulated_variables(path) == ["brightnessTemperature"]

    def test_no_ombg_group_raises(self, tmp_path):
        path = tmp_path / "diag_x_2026093018.nc"
        write_adpsfc(path, drop_groups=("ombg",))
        with pytest.raises(IodaFormatError, match="ombg"):
            list_simulated_variables(path)


# ---------------------------------------------------------------------------
# read_ioda — conventional
# ---------------------------------------------------------------------------

class TestReadConventional:

    def test_structure(self, adpsfc):
        path, w = adpsfc
        ds = read_ioda(path, "stationPressure")
        assert dict(ds.sizes) == {"Location": w["n"]}
        assert list(ds.data_vars) == list(FIELDS)
        assert set(ds.coords) == {"latitude", "longitude", "dateTime"}

    def test_attrs(self, adpsfc):
        path, _ = adpsfc
        ds = read_ioda(path, "stationPressure")
        assert ds.attrs["obs_space"] == "prepbufr_adpsfc"
        assert ds.attrs["variable"] == "stationPressure"
        assert ds.attrs["units"] == "Pa"
        assert ds.attrs["source_path"] == str(path)
        assert ds.attrs["ioda_layout"] == "ObsGroup"

    def test_obs_space_override(self, adpsfc):
        path, _ = adpsfc
        assert read_ioda(path, "stationPressure", obs_space="sfc_ps").attrs["obs_space"] == "sfc_ps"

    def test_values_match_file(self, adpsfc):
        path, w = adpsfc
        ds = read_ioda(path, "airTemperatureAt2M")
        np.testing.assert_allclose(ds["obs"].values, w["obs"]["airTemperatureAt2M"], rtol=1e-6)
        np.testing.assert_allclose(ds["ombg"].values, w["groups"]["ombg"]["airTemperatureAt2M"], rtol=1e-6)
        np.testing.assert_array_equal(ds["qc_an"].values, w["groups"]["EffectiveQC1"]["airTemperatureAt2M"])
        assert ds["obs"].dtype == np.float64
        assert ds["qc_bg"].dtype == np.int32

    def test_float_fill_becomes_nan(self, adpsfc):
        path, _ = adpsfc
        ds = read_ioda(path, "stationPressure")
        assert np.isnan(ds["ombg"].values[0])
        assert np.isnan(ds["oman"].values[0])
        assert np.isfinite(ds["ombg"].values[1:]).all()

    def test_qc_fill_becomes_qc_missing(self, adpsfc):
        path, w = adpsfc
        ds = read_ioda(path, "stationPressure")
        assert ds["qc_bg"].values[1] == QC_MISSING
        expected = w["groups"]["EffectiveQC0"]["stationPressure"].copy()
        expected[1] = QC_MISSING
        np.testing.assert_array_equal(ds["qc_bg"].values, expected)

    def test_datetime_decoded_and_fill_is_nat(self, adpsfc):
        path, w = adpsfc
        ds = read_ioda(path, "stationPressure")
        t = ds["dateTime"].values
        assert t.dtype == np.dtype("datetime64[ns]")
        assert np.isnat(t[2])
        good = np.arange(w["n"]) != 2
        expected = (np.datetime64("1970-01-01T00:00:00", "s") + w["times"][good].astype("timedelta64[s]"))
        np.testing.assert_array_equal(t[good], expected.astype("datetime64[ns]"))
        # every valid time is within +/-3h of the cycle
        cyc = np.datetime64(w["cycle"], "ns")
        assert (np.abs(t[good] - cyc) <= np.timedelta64(3, "h")).all()

    def test_longitude_normalised(self, adpsfc):
        path, w = adpsfc
        lon = read_ioda(path, "stationPressure")["longitude"].values
        assert lon[3] == pytest.approx(-170.0)
        assert ((lon >= -180) & (lon < 180)).all()
        np.testing.assert_allclose(lon[:3], w["lon"][:3], rtol=1e-6)

    def test_unsimulated_variable_raises(self, adpsfc):
        path, _ = adpsfc
        with pytest.raises(VariableNotSimulatedError) as exc:
            read_ioda(path, "specificHumidityAt2M")
        assert exc.value.available == sorted(ADPSFC_SIMULATED)

    def test_fields_subset_always_includes_required(self, adpsfc):
        path, _ = adpsfc
        ds = read_ioda(path, "stationPressure", fields=["ombg", "qc_bg"])
        assert list(ds.data_vars) == ["obs", "ombg", "qc_bg"]

    def test_unknown_field_raises(self, adpsfc):
        path, _ = adpsfc
        with pytest.raises(ValueError, match="Unknown field"):
            read_ioda(path, "stationPressure", fields=["omf"])

    def test_missing_optional_group_is_omitted(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path, drop_groups=("oman", "hofx1", "EffectiveQC1"))
        ds = read_ioda(path, "stationPressure")
        assert {"oman", "hofx_an", "qc_an"}.isdisjoint(ds.data_vars)
        assert {"obs", "ombg", "qc_bg"} <= set(ds.data_vars)

    def test_group_map_override(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path)
        # Point qc_bg at the analysis QC group, as an app with one QC group would
        ds = read_ioda(path, "airTemperatureAt2M", group_map={"qc_bg": "EffectiveQC1"})
        np.testing.assert_array_equal(ds["qc_bg"].values, ds["qc_an"].values)
        assert ds["qc_bg"].attrs["ioda_group"] == "EffectiveQC1"


# ---------------------------------------------------------------------------
# Outer-loop groups: *_bg = lowest index, *_an = highest index
# ---------------------------------------------------------------------------

class TestOuterLoops:

    def test_real_layout_one_outer_loop(self, adpsfc):
        path, _ = adpsfc
        gmap = resolve_group_map(path)
        assert gmap["hofx_bg"] == "hofx0" and gmap["hofx_an"] == "hofx1"
        assert gmap["qc_an"] == "EffectiveQC1" and gmap["err_an"] == "EffectiveError1"
        assert gmap["bias_an"] == "ObsBias1"
        assert read_ioda(path, "stationPressure").attrs["n_outer_loops"] == 1

    @pytest.mark.parametrize("iterations, an", [((0, 1, 2), 2), (tuple(range(50)), 49), ((0, 1, 7), 7)])
    def test_analysis_is_highest_index(self, tmp_path, iterations, an):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        w = write_adpsfc(path, iterations=iterations)
        ds = read_ioda(path, "airTemperatureAt2M")
        for field, prefix in [("hofx", "hofx"), ("qc", "EffectiveQC"), ("err", "EffectiveError"),
                              ("bias", "ObsBias")]:
            assert ds[f"{field}_bg"].attrs["ioda_group"] == f"{prefix}0"
            assert ds[f"{field}_an"].attrs["ioda_group"] == f"{prefix}{an}"
        np.testing.assert_allclose(ds["hofx_an"].values, w["groups"][f"hofx{an}"]["airTemperatureAt2M"], rtol=1e-6)
        np.testing.assert_array_equal(ds["qc_an"].values, w["groups"][f"EffectiveQC{an}"]["airTemperatureAt2M"])
        assert ds.attrs["n_outer_loops"] == an

    def test_single_iteration_has_no_analysis_fields(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path, iterations=(0,), drop_groups=("oman",))
        ds = read_ioda(path, "stationPressure")
        assert {"hofx_bg", "qc_bg", "err_bg", "bias_bg"} <= set(ds.data_vars)
        assert {"hofx_an", "qc_an", "err_an", "bias_an", "oman"}.isdisjoint(ds.data_vars)
        assert ds.attrs["n_outer_loops"] == 0

    def test_lookalike_group_names_ignored(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path)
        with nc4.Dataset(path, "a") as ds:
            for name in ("hofx9_old", "hofxPredictor", "EffectiveQC_extra"):
                ds.createGroup(name)
        gmap = resolve_group_map(path)
        assert gmap["hofx_an"] == "hofx1" and gmap["qc_an"] == "EffectiveQC1"

    def test_override_wins(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path, iterations=(0, 1, 2))
        ds = read_ioda(path, "airTemperatureAt2M", group_map={"hofx_an": "hofx1"})
        assert ds["hofx_an"].attrs["ioda_group"] == "hofx1"
        assert ds["qc_an"].attrs["ioda_group"] == "EffectiveQC2"

    def test_override_unknown_field_raises(self, adpsfc):
        path, _ = adpsfc
        with pytest.raises(ValueError, match="Unknown field"):
            read_ioda(path, "stationPressure", group_map={"hofx_final": "hofx1"})


# ---------------------------------------------------------------------------
# read_ioda — radiance
# ---------------------------------------------------------------------------

class TestReadRadiance:

    def test_structure_all_channels(self, atms):
        path, w = atms
        ds = read_ioda(path, "brightnessTemperature")
        assert dict(ds.sizes) == {"Location": w["n"], "channel": 22}
        np.testing.assert_array_equal(ds["channel"].values, w["channels"])
        assert ds["ombg"].dims == ("Location", "channel")
        assert ds.attrs["obs_space"] == "radiance_atms_n20"
        assert ds.attrs["units"] == "K"

    def test_channel_subset(self, atms):
        path, w = atms
        ds = read_ioda(path, "brightnessTemperature", channels=[7, 1, 15])
        np.testing.assert_array_equal(ds["channel"].values, [1, 7, 15])
        np.testing.assert_allclose(ds["ombg"].values, w["pattern"][:, [0, 6, 14]], rtol=1e-6)
        np.testing.assert_allclose(ds["obs"].values, 200.0 + w["pattern"][:, [0, 6, 14]], rtol=1e-6)

    def test_unknown_channel_raises(self, atms):
        path, _ = atms
        with pytest.raises(ChannelNotFoundError, match=r"\[23\]"):
            read_ioda(path, "brightnessTemperature", channels=[1, 23])

    def test_channels_on_conventional_raises(self, adpsfc):
        path, _ = adpsfc
        with pytest.raises(ChannelNotFoundError, match="no Channel dimension"):
            read_ioda(path, "stationPressure", channels=[1])

    def test_ignores_predictor_and_derived_groups(self, atms):
        path, _ = atms
        ds = read_ioda(path, "brightnessTemperature")
        assert set(ds.data_vars) == set(FIELDS)


# ---------------------------------------------------------------------------
# Bad files
# ---------------------------------------------------------------------------

class TestBadFiles:

    def test_missing_file(self, tmp_path):
        with pytest.raises(IodaFormatError, match="does not exist"):
            read_ioda(tmp_path / "nope.nc", "stationPressure")

    def test_corrupt_file(self, tmp_path):
        path = tmp_path / "diag_bad_2026093018.nc"
        path.write_bytes(b"not a netcdf file")
        with pytest.raises(IodaFormatError, match="could not be opened"):
            read_ioda(path, "stationPressure")

    def test_missing_obsvalue_variable(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path)
        # netCDF4 can't delete a variable, so rename it out of the way
        with nc4.Dataset(path, "a") as ds:
            ds.groups["ObsValue"].renameVariable("stationPressure", "stationPressure_renamed")
        with pytest.raises(IodaFormatError, match="ObsValue/stationPressure"):
            read_ioda(path, "stationPressure")

    def test_missing_latitude(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path)
        with nc4.Dataset(path, "a") as ds:
            ds.groups["MetaData"].renameVariable("latitude", "lat")
        with pytest.raises(IodaFormatError, match="MetaData/latitude"):
            read_ioda(path, "stationPressure")

    def test_bad_time_units(self, tmp_path):
        path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
        write_adpsfc(path)
        with nc4.Dataset(path, "a") as ds:
            ds.groups["MetaData"].variables["dateTime"].units = "hours since 1970-01-01"
        with pytest.raises(IodaFormatError, match="Unsupported dateTime units"):
            read_ioda(path, "stationPressure")


def test_non_unix_epoch(tmp_path):
    """dateTime units with an epoch other than 1970 are honoured."""
    path = tmp_path / "diag_prepbufr_adpsfc_2026093018.nc"
    write_adpsfc(path)
    with nc4.Dataset(path, "a") as ds:
        t = ds.groups["MetaData"].variables["dateTime"]
        t.units = "seconds since 2026-09-30T18:00:00Z"
        t[3] = 0
        t[4] = -3600
    times = read_ioda(path, "stationPressure")["dateTime"].values
    assert times[3] == np.datetime64("2026-09-30T18:00:00", "ns")
    assert times[4] == np.datetime64("2026-09-30T17:00:00", "ns")
    assert np.isnat(times[2])
