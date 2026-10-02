"""
Synthetic IODA diag files that mirror real GDAS JEDI output.

Layouts are taken from ``ncdump -h`` of:

* ``diag_prepbufr_adpsfc_2026093018.nc`` (conventional; dim ``Location``)
* ``diag_radiance_atms_n20_2026093018.nc`` (radiance; dims ``Location``, ``Channel``)

from ``gdas.t18z.atmos_analysis.ioda_hofx.tar.gz`` (prjedi, 2026-09-30 18Z).
Only structure is copied; all values are synthetic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import netCDF4 as nc4
import numpy as np

FLOAT_FILL = np.float32(-3.368795e+38)
INT_FILL = np.int32(-2147483643)
INT64_FILL = np.int64(-9223372036854775801)
TIME_UNITS = "seconds since 1970-01-01T00:00:00Z"

# adpsfc: ObsValue carries 6 variables but only these 2 are simulated
ADPSFC_OBSVALUE_VARS = [
    "airTemperatureAt2M", "specificHumidityAt2M", "stationPressure",
    "virtualTemperatureAt2M", "windEastward", "windNorthward",
]
ADPSFC_SIMULATED = ["airTemperatureAt2M", "stationPressure"]
ADPSFC_UNITS = {
    "airTemperatureAt2M": "K", "specificHumidityAt2M": "kg kg-1", "stationPressure": "Pa",
    "virtualTemperatureAt2M": "K", "windEastward": "m s-1", "windNorthward": "m s-1",
}

# Per-simulated-variable float groups common to both families
SIM_FLOAT_GROUPS = ["ombg", "oman", "hofx0", "hofx1", "EffectiveError0", "EffectiveError1", "ObsBias0", "ObsBias1"]
SIM_INT_GROUPS = ["EffectiveQC0", "EffectiveQC1"]

ATMS_N_CHANNELS = 22
ATMS_PREDICTOR_GROUPS = [
    "constantPredictor", "emissivityJacobianPredictor", "lapseRatePredictor",
    "lapseRate_order_2Predictor", "sensorScanAnglePredictor", "sensorScanAngle_order_2Predictor",
    "sensorScanAngle_order_3Predictor", "sensorScanAngle_order_4Predictor",
]


def _epoch_seconds(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _fvar(group, name, dims, data, units=None, long_name=None):
    v = group.createVariable(name, "f4", dims, fill_value=FLOAT_FILL)
    v[:] = data
    if long_name:
        v.long_name = long_name
    if units:
        v.units = units
    return v


def _ivar(group, name, dims, data):
    v = group.createVariable(name, "i4", dims, fill_value=INT_FILL)
    v[:] = data
    return v


def _metadata(ds, lat, lon, times):
    meta = ds.createGroup("MetaData")
    _fvar(meta, "latitude", ("Location",), lat, units="degree_north", long_name="Latitude")
    _fvar(meta, "longitude", ("Location",), lon, units="degree_east", long_name="Longitude")
    t = meta.createVariable("dateTime", "i8", ("Location",), fill_value=INT64_FILL)
    t[:] = times
    t.units = TIME_UNITS
    t.long_name = "dateTime"
    return meta


def write_adpsfc(
    path: Path,
    cycle: datetime = datetime(2026, 9, 30, 18),
    n: int = 10,
    drop_groups: tuple[str, ...] = (),
    seed: int = 0,
) -> dict:
    """
    Write a synthetic ``diag_prepbufr_adpsfc_*.nc`` and return the arrays
    written (as float64, before fill) so tests can check exact values.

    Built-in edge cases:
    * location 0: ``ombg``/``oman`` stationPressure = fill
    * location 1: ``EffectiveQC0`` stationPressure = fill
    * location 2: ``dateTime`` = fill
    * location 3: longitude = 190.0 (must normalise to -170.0)
    """
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = _epoch_seconds(cycle)

    lat = rng.uniform(-80, 80, n).astype(np.float32)
    lon = rng.uniform(-179, 179, n).astype(np.float32)
    lon[3] = 190.0
    times = (t0 + rng.integers(-10800, 10800, n)).astype(np.int64)
    times[2] = INT64_FILL

    values = {
        "obs": {v: rng.normal(100000.0 if v == "stationPressure" else 280.0, 5.0, n).astype(np.float32)
                for v in ADPSFC_OBSVALUE_VARS},
        "groups": {},
    }

    with nc4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("Location", None)
        loc = ds.createVariable("Location", "i4", ("Location",), fill_value=INT_FILL)
        loc[:] = np.arange(n)
        ds.converter = "bufr-query"
        ds.platformCommonName = "ADPSFC"
        ds._ioda_layout = "ObsGroup"
        ds._ioda_layout_version = 0

        _metadata(ds, lat, lon, times)
        meta = ds.groups["MetaData"]
        sid = meta.createVariable("stationIdentification", str, ("Location",))
        for i in range(n):
            sid[i] = f"STN{i:02d}"
        _fvar(meta, "pressure", ("Location",), rng.uniform(80000, 103000, n), units="Pa")
        _fvar(meta, "height", ("Location",), rng.uniform(0, 2000, n), units="m")
        _fvar(meta, "stationElevation", ("Location",), rng.uniform(0, 2000, n), units="m")
        _ivar(meta, "observationSubTypeNum", ("Location",), np.zeros(n, dtype=np.int32))

        g = ds.createGroup("ObsValue")
        for v in ADPSFC_OBSVALUE_VARS:
            _fvar(g, v, ("Location",), values["obs"][v], units=ADPSFC_UNITS[v])

        g = ds.createGroup("ObsError")
        for v in ADPSFC_OBSVALUE_VARS:
            _fvar(g, v, ("Location",), np.full(n, 1.0, np.float32))
        for grp in ("ObsType", "ObsSubType", "QualityMarker"):
            g = ds.createGroup(grp)
            for v in ADPSFC_OBSVALUE_VARS:
                _ivar(g, v, ("Location",), np.full(n, 120, np.int32))
        _fvar(ds.createGroup("InputObsError"), "stationPressure", ("Location",), np.ones(n, np.float32))
        _fvar(ds.createGroup("ObsErrorFactorDuplicateCheck"), "stationPressure", ("Location",), np.ones(n, np.float32))

        for grp in SIM_FLOAT_GROUPS:
            if grp in drop_groups:
                continue
            g = ds.createGroup(grp)
            values["groups"][grp] = {}
            for v in ADPSFC_SIMULATED:
                arr = rng.normal(0.0, 1.0, n).astype(np.float32)
                if grp in ("ombg", "oman") and v == "stationPressure":
                    arr[0] = FLOAT_FILL
                _fvar(g, v, ("Location",), arr)
                values["groups"][grp][v] = arr
        for grp in SIM_INT_GROUPS:
            if grp in drop_groups:
                continue
            g = ds.createGroup(grp)
            values["groups"][grp] = {}
            for v in ADPSFC_SIMULATED:
                arr = rng.integers(0, 3, n).astype(np.int32)
                if grp == "EffectiveQC0" and v == "stationPressure":
                    arr[1] = INT_FILL
                _ivar(g, v, ("Location",), arr)
                values["groups"][grp][v] = arr

    values.update(lat=lat, lon=lon, times=times, n=n, cycle=cycle)
    return values


def write_atms(
    path: Path,
    cycle: datetime = datetime(2026, 9, 30, 18),
    n: int = 8,
    n_channels: int = ATMS_N_CHANNELS,
    seed: int = 1,
) -> dict:
    """
    Write a synthetic ``diag_radiance_atms_n20_*.nc`` and return what was
    written. Channel numbers are 1..n_channels. Data value for channel c at
    location i in group ``ombg`` is ``i + c / 100`` so channel selection can be
    checked exactly.
    """
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = _epoch_seconds(cycle)
    chans = np.arange(1, n_channels + 1, dtype=np.int32)

    lat = rng.uniform(-80, 80, n).astype(np.float32)
    lon = rng.uniform(-179, 179, n).astype(np.float32)
    times = (t0 + rng.integers(-10800, 10800, n)).astype(np.int64)
    pattern = (np.arange(n)[:, None] + chans[None, :] / 100.0).astype(np.float32)

    with nc4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("Channel", n_channels)
        ds.createDimension("Location", None)
        c = ds.createVariable("Channel", "i4", ("Channel",), fill_value=INT_FILL)
        c[:] = chans
        loc = ds.createVariable("Location", "i4", ("Location",), fill_value=INT_FILL)
        loc[:] = np.arange(n)
        ds.sensorCommonName = "ATMS"
        ds._ioda_layout = "ObsGroup"

        meta = _metadata(ds, lat, lon, times)
        _ivar(meta, "sensorChannelNumber", ("Location", "Channel"), np.tile(chans, (n, 1)))
        _fvar(meta, "sensorZenithAngle", ("Location",), rng.uniform(0, 60, n), units="degree")
        _ivar(meta, "sensorScanPosition", ("Location",), rng.integers(1, 97, n).astype(np.int32))

        dm = ds.createGroup("DerivedMetaData")
        _fvar(dm, "CLWRetFromObs", ("Location",), rng.uniform(0, 1, n))
        _fvar(dm, "Innovation", ("Location", "Channel"), pattern)
        _fvar(ds.createGroup("DerivedObsError"), "brightnessTemperature", ("Location", "Channel"), pattern)

        _fvar(ds.createGroup("ObsValue"), "brightnessTemperature", ("Location", "Channel"),
              200.0 + pattern, units="K")
        for grp in SIM_FLOAT_GROUPS + ATMS_PREDICTOR_GROUPS:
            _fvar(ds.createGroup(grp), "brightnessTemperature", ("Location", "Channel"), pattern)
        for grp in SIM_INT_GROUPS:
            _ivar(ds.createGroup(grp), "brightnessTemperature", ("Location", "Channel"),
                  np.zeros((n, n_channels), dtype=np.int32))

    return dict(lat=lat, lon=lon, times=times, n=n, channels=chans, pattern=pattern, cycle=cycle)
