"""
obs_monitor.io.ioda
===================
 
Read one JEDI IODA diagnostic file (``diag_<obs_space>_<YYYYMMDDHH>.nc``)
for one simulated variable into a canonical :class:`xarray.Dataset`.
 
This module is the only place in obs-monitor that knows IODA group names.
Everything downstream (reductions, figures) works with the canonical field
names below, so a change in how a JEDI application names its groups is a
change to :data:`DEFAULT_GROUP_MAP` or a per-obs-space override, never to
downstream code.
 
Output contract
---------------
For a conventional obs space::
 
    Dimensions:  (Location: N)
    Coordinates:
        latitude   (Location) float64   degrees north
        longitude  (Location) float64   degrees east, normalised to [-180, 180)
        dateTime   (Location) datetime64[ns]  NaT where missing
    Data variables (each present only if its IODA group exists in the file):
        obs        (Location) float64   ObsValue
        ombg       (Location) float64   observation minus background
        oman       (Location) float64   observation minus analysis
        hofx_bg    (Location) float64   H(x) background   (hofx0)
        hofx_an    (Location) float64   H(x) analysis     (hofx1)
        qc_bg      (Location) int32     EffectiveQC0, QC_MISSING where filled
        qc_an      (Location) int32     EffectiveQC1, QC_MISSING where filled
        err_bg     (Location) float64   EffectiveError0
        err_an     (Location) float64   EffectiveError1
        bias_bg    (Location) float64   ObsBias0
        bias_an    (Location) float64   ObsBias1
    Attributes:
        obs_space, variable, units, source_path, ioda_layout
 
For a radiance obs space every data variable gains a trailing ``channel``
dimension, and ``channel`` is a coordinate holding the sensor channel numbers
(from the root ``Channel`` variable).
 
Missing values: float fill values (and anything below ``-1e36``) become NaN;
integer QC fill values become :data:`QC_MISSING`; ``dateTime`` fill becomes
NaT.
 
Typical usage
-------------
>>> from obs_monitor.io.ioda import list_simulated_variables, read_ioda
>>> list_simulated_variables(path)
['airTemperatureAt2M', 'stationPressure']
>>> ds = read_ioda(path, "stationPressure", obs_space="prepbufr_adpsfc")
>>> ds = read_ioda(rad_path, "brightnessTemperature", channels=[1, 5, 7])
"""
 
from __future__ import annotations
 
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
 
import netCDF4 as nc4
import numpy as np
import xarray as xr
 
logger = logging.getLogger(__name__)
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
 
#: Canonical field name -> IODA group name.  Order is the order fields appear
#: in the returned Dataset.  Override per obs space with ``group_map=``.
DEFAULT_GROUP_MAP: dict[str, str] = {
    "obs": "ObsValue",
    "ombg": "ombg",
    "oman": "oman",
    "hofx_bg": "hofx0",
    "hofx_an": "hofx1",
    "qc_bg": "EffectiveQC0",
    "qc_an": "EffectiveQC1",
    "err_bg": "EffectiveError0",
    "err_an": "EffectiveError1",
    "bias_bg": "ObsBias0",
    "bias_an": "ObsBias1",
}
 
#: Fields that must be present for the file to be usable.
REQUIRED_FIELDS: tuple[str, ...] = ("obs",)
 
#: Fields read as integer QC flags rather than floats.
QC_FIELDS: frozenset[str] = frozenset({"qc_bg", "qc_an"})
 
#: IODA group whose variables define the "simulated variables" of a file.
SIMULATED_VARIABLES_GROUP = "ombg"
 
#: Value written into QC fields where the file holds the integer fill value.
QC_MISSING = -1
 
METADATA_GROUP = "MetaData"
LAT_VAR = "latitude"
LON_VAR = "longitude"
TIME_VAR = "dateTime"
CHANNEL_VAR = "Channel"
 
# Real files use -3.368795e+38 as the float fill; netCDF4 masks it when the
# _FillValue attribute is set, and this threshold catches it when it isn't.
_FLOAT_FILL_THRESHOLD = -1e36
 
_TIME_UNITS_RE = re.compile(r"^\s*seconds\s+since\s+(.+?)\s*$")
 
 
# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
 
class IodaFormatError(ValueError):
    """The file is not a usable IODA diag file (unreadable, or a required
    group/variable is missing)."""
 
 
class VariableNotSimulatedError(ValueError):
    """The requested variable is not a simulated variable in this file."""
 
    def __init__(self, variable: str, available: Sequence[str], path: Path) -> None:
        self.variable = variable
        self.available = list(available)
        super().__init__(
            f"'{variable}' is not simulated in '{path.name}'. "
            f"Simulated variables: {self.available}"
        )
 
 
class ChannelNotFoundError(ValueError):
    """One or more requested channel numbers are not in the file."""
 
 
# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
 
def _open(path: Path) -> nc4.Dataset:
    if not path.exists():
        raise IodaFormatError(f"File does not exist: {path}")
    try:
        return nc4.Dataset(path, "r")
    except Exception as exc:  # noqa: BLE001
        raise IodaFormatError(f"'{path.name}' could not be opened by netCDF4: {exc}") from exc
 
 
def _channel_index(root: nc4.Dataset, channels: Sequence[int] | None, path: Path):
    """
    Return ``(index, channel_numbers)`` for the Channel dimension, or
    ``(None, None)`` if the file has no Channel dimension.
 
    ``index`` is a slice (all channels) or a sorted integer array.
    """
    if CHANNEL_VAR not in root.dimensions:
        if channels is not None:
            raise ChannelNotFoundError(f"'{path.name}' has no Channel dimension; channels={list(channels)} given.")
        return None, None
 
    if CHANNEL_VAR in root.variables:
        all_numbers = np.asarray(root.variables[CHANNEL_VAR][:]).astype(int)
    else:
        all_numbers = np.arange(1, root.dimensions[CHANNEL_VAR].size + 1)
 
    if channels is None:
        return slice(None), all_numbers
 
    requested = [int(c) for c in channels]
    missing = sorted(set(requested) - set(all_numbers.tolist()))
    if missing:
        raise ChannelNotFoundError(
            f"Channel(s) {missing} not in '{path.name}'. Available: {all_numbers.tolist()}"
        )
    idx = np.sort(np.array([int(np.where(all_numbers == c)[0][0]) for c in set(requested)]))
    return idx, all_numbers[idx]
 
 
def _read_array(var: nc4.Variable, chan_idx, is_qc: bool) -> np.ndarray:
    """Read a (Location[, Channel]) variable, applying channel selection and fill handling."""
    if var.ndim == 2 and chan_idx is not None:
        raw = var[:, chan_idx]
    else:
        raw = var[:]
 
    if is_qc:
        if isinstance(raw, np.ma.MaskedArray):
            return raw.filled(QC_MISSING).astype(np.int32)
        return np.asarray(raw, dtype=np.int32)
 
    if isinstance(raw, np.ma.MaskedArray):
        data = raw.astype(np.float64).filled(np.nan)
    else:
        data = np.asarray(raw, dtype=np.float64)
    data[data < _FLOAT_FILL_THRESHOLD] = np.nan
    return data
 
 
def _decode_time(var: nc4.Variable) -> np.ndarray:
    """Decode an IODA ``dateTime`` (integer seconds since an epoch) to datetime64[ns]."""
    raw = var[:]
    units = getattr(var, "units", "seconds since 1970-01-01T00:00:00Z")
    match = _TIME_UNITS_RE.match(units)
    if not match:
        raise IodaFormatError(f"Unsupported {TIME_VAR} units '{units}'; expected 'seconds since <ISO time>'.")
    epoch_str = match.group(1).replace("Z", "+00:00")
    epoch = datetime.fromisoformat(epoch_str)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
 
    if isinstance(raw, np.ma.MaskedArray):
        mask = np.ma.getmaskarray(raw)
        secs = raw.filled(0).astype(np.int64)
    else:
        secs = np.asarray(raw, dtype=np.int64)
        mask = np.zeros(secs.shape, dtype=bool)
    fill = getattr(var, "_FillValue", None)
    if fill is not None:
        mask |= secs == np.int64(fill)
 
    out = np.datetime64(epoch, "s") + secs.astype("timedelta64[s]")
    out = out.astype("datetime64[ns]")
    out[mask] = np.datetime64("NaT")
    return out
 
 
def _normalise_longitude(lon: np.ndarray) -> np.ndarray:
    """Map longitudes to [-180, 180); NaN stays NaN."""
    return ((lon + 180.0) % 360.0) - 180.0
 
 
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
 
def list_simulated_variables(path: str | Path) -> list[str]:
    """
    Return the simulated variables in an IODA diag file.
 
    These are the variables in the ``ombg`` group: the ones the DA actually
    simulated. ``ObsValue`` often carries more (e.g. adpsfc has wind and
    humidity in ``ObsValue`` but only ``stationPressure`` and
    ``airTemperatureAt2M`` are simulated).
 
    Raises
    ------
    IodaFormatError
        If the file can't be opened or has no ``ombg`` group.
    """
    path = Path(path)
    with _open(path) as root:
        if SIMULATED_VARIABLES_GROUP not in root.groups:
            raise IodaFormatError(
                f"'{path.name}' has no '{SIMULATED_VARIABLES_GROUP}' group; cannot list simulated variables."
            )
        return sorted(root.groups[SIMULATED_VARIABLES_GROUP].variables)
 
 
def read_ioda(
    path: str | Path,
    variable: str,
    *,
    obs_space: str | None = None,
    channels: Sequence[int] | None = None,
    fields: Sequence[str] | None = None,
    group_map: Mapping[str, str] | None = None,
) -> xr.Dataset:
    """
    Read one simulated variable from one IODA diag file.
 
    Parameters
    ----------
    path:
        Path to the diag file.
    variable:
        Simulated variable name, e.g. ``"stationPressure"`` or
        ``"brightnessTemperature"``.
    obs_space:
        Name recorded in ``ds.attrs["obs_space"]``. Defaults to the filename
        stem with a leading ``diag_`` and trailing ``_YYYYMMDDHH`` removed.
    channels:
        Radiance only: sensor channel numbers to read (others are never
        loaded). ``None`` reads all channels.
    fields:
        Canonical fields to read (keys of the group map). ``None`` reads
        every field whose group exists. Required fields are always read.
    group_map:
        Overrides merged on top of :data:`DEFAULT_GROUP_MAP`, e.g.
        ``{"qc_bg": "EffectiveQC"}`` for an application with one QC group.
 
    Raises
    ------
    IodaFormatError
        Unreadable file, or missing ``MetaData`` lat/lon/dateTime or a
        required field.
    VariableNotSimulatedError
        ``variable`` is not in the file's ``ombg`` group (when that group
        exists).
    ChannelNotFoundError
        A requested channel number is not in the file.
    """
    path = Path(path)
    gmap = {**DEFAULT_GROUP_MAP, **(group_map or {})}
    unknown = set(fields or ()) - set(gmap)
    if unknown:
        raise ValueError(f"Unknown field(s) {sorted(unknown)}. Known: {list(gmap)}")
    wanted = list(gmap) if fields is None else [f for f in gmap if f in set(fields) | set(REQUIRED_FIELDS)]
 
    if obs_space is None:
        obs_space = re.sub(r"_\d{10}$", "", re.sub(r"^diag_", "", path.stem))
 
    with _open(path) as root:
        # --- variable must be simulated (when we can tell) ---
        sim_group = gmap.get("ombg", SIMULATED_VARIABLES_GROUP)
        if sim_group in root.groups:
            simulated = sorted(root.groups[sim_group].variables)
            if variable not in simulated:
                raise VariableNotSimulatedError(variable, simulated, path)
 
        # --- MetaData coordinates ---
        if METADATA_GROUP not in root.groups:
            raise IodaFormatError(f"'{path.name}' has no '{METADATA_GROUP}' group.")
        meta = root.groups[METADATA_GROUP]
        for v in (LAT_VAR, LON_VAR, TIME_VAR):
            if v not in meta.variables:
                raise IodaFormatError(f"'{path.name}' is missing {METADATA_GROUP}/{v}.")
 
        lat = _read_array(meta.variables[LAT_VAR], None, is_qc=False)
        lon = _normalise_longitude(_read_array(meta.variables[LON_VAR], None, is_qc=False))
        times = _decode_time(meta.variables[TIME_VAR])
 
        chan_idx, chan_numbers = _channel_index(root, channels, path)
        dims: tuple[str, ...] = ("Location",) if chan_idx is None else ("Location", "channel")
 
        # --- data fields ---
        data_vars: dict[str, xr.Variable] = {}
        units = None
        for field in wanted:
            group_name = gmap[field]
            group = root.groups.get(group_name)
            if group is None or variable not in group.variables:
                if field in REQUIRED_FIELDS:
                    raise IodaFormatError(f"'{path.name}' is missing required {group_name}/{variable}.")
                logger.debug("%s: %s/%s not present; field '%s' omitted.", path.name, group_name, variable, field)
                continue
            ncvar = group.variables[variable]
            arr = _read_array(ncvar, chan_idx, is_qc=field in QC_FIELDS)
            if arr.ndim != len(dims):
                raise IodaFormatError(
                    f"'{path.name}' {group_name}/{variable} has shape {arr.shape}; expected dims {dims}."
                )
            data_vars[field] = xr.Variable(dims, arr, attrs={"ioda_group": group_name})
            if field == "obs":
                units = getattr(ncvar, "units", None)
 
        coords: dict[str, xr.Variable] = {
            "latitude": xr.Variable("Location", lat),
            "longitude": xr.Variable("Location", lon),
            "dateTime": xr.Variable("Location", times),
        }
        if chan_numbers is not None:
            coords["channel"] = xr.Variable("channel", chan_numbers.astype(np.int32))
 
        attrs = {
            "obs_space": obs_space,
            "variable": variable,
            "units": units if units is not None else "",
            "source_path": str(path),
            "ioda_layout": str(getattr(root, "_ioda_layout", "")),
        }
 
    ds = xr.Dataset(data_vars, coords=coords, attrs=attrs)
    logger.info(
        "read_ioda('%s', '%s'): %d locations%s, fields=%s",
        path.name, variable, ds.sizes["Location"],
        f" x {ds.sizes['channel']} channels" if "channel" in ds.sizes else "",
        list(ds.data_vars),
    )
    return ds
