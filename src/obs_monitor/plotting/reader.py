"""
obs_monitor.plotting.reader
===========================

Opens staged obs-monitor NetCDF files, navigates to a specified group
path, reads requested variables, and stacks the results across files into
a single xarray Dataset whose first dimension is ``analysisCycle``.

Typical usage
-------------
>>> from obs_monitor.plotting.reader import read_group
>>>
>>> ds = read_group(
...     nc_files=sorted(window_dir.glob("prepbufr_adpsfc_*.nc")),
...     group_path="byDomains/ombg/stationPressure",
...     variables=["assimilated_mean", "assimilated_count", "assimilated_RMS"],
... )
>>> ds
<xarray.Dataset>
Dimensions:  (analysisCycle: 4, ...)
Coordinates:
  * analysisCycle  (analysisCycle) datetime64[ns] 2025-01-01T00:00:00 ...
Data variables:
    assimilated_mean  (analysisCycle, ...) float64 ...
    ...

Notes
-----
* ``analysisCycle`` timestamps are parsed from filenames using the same
  10-digit ``YYYYMMDDHH`` pattern that the rest of obs-monitor uses.
* Files where the target group is absent are skipped with a WARNING rather
  than raising an exception, keeping the pipeline fault-tolerant.
* Variables that are missing in a particular file are filled with NaN
  arrays of matching shape/dtype so the stack stays rectangular.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import netCDF4 as nc4
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TIMESTAMP_RE = re.compile(r"\d{10,14}")


def _parse_cycle_from_path(path: Path) -> datetime | None:
    """
    Extract a UTC ``datetime`` from the first 10-digit (or longer) run of
    digits found in the file's stem.

    The obs-monitor filename convention embeds the cycle as ``YYYYMMDDHH``
    (optionally followed by ``MMSS``), e.g.::

        prepbufr_adpsfc_2025010106.nc
        prepbufr_adpsfc_2025010106_something.nc

    Parameters
    ----------
    path:
        Path to a NetCDF file.

    Returns
    -------
    datetime | None
        Timezone-aware UTC datetime on success, or ``None`` if no suitable
        digit sequence is found.
    """
    match = _TIMESTAMP_RE.search(path.stem)
    if match is None:
        logger.debug("No timestamp found in filename '%s'", path.name)
        return None

    digits = match.group(0)[:10]  # take first 10 digits = YYYYMMDDHH
    try:
        return datetime.strptime(digits, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.debug("Could not parse timestamp '%s' from '%s'", digits, path.name)
        return None


def _navigate_to_group(root: nc4.Dataset, group_path: str) -> nc4.Group | nc4.Dataset | None:
    """
    Descend into a NetCDF group hierarchy given a slash-separated path.

    For example, ``"byDomains/ombg/stationPressure"`` walks::

        root -> root["byDomains"] -> ...["ombg"] -> ...["stationPressure"]

    Parameters
    ----------
    root:
        An open ``netCDF4.Dataset``.
    group_path:
        Slash-separated group path.  An empty string or ``"/"`` returns
        ``root`` itself.

    Returns
    -------
    netCDF4.Group | netCDF4.Dataset | None
        The target group object, or ``None`` if any segment is missing.
    """
    if not group_path or group_path == "/":
        return root

    current: nc4.Group | nc4.Dataset = root
    for segment in group_path.strip("/").split("/"):
        if segment not in current.groups:
            return None
        current = current.groups[segment]
    return current


def _read_variable(
    group: nc4.Group | nc4.Dataset,
    var_name: str,
    fill_shape: tuple[int, ...] | None,
    fill_dtype: np.dtype = np.float64,
) -> tuple[np.ndarray, dict]:
    """
    Read a single variable from a NetCDF group.

    If the variable is absent, returns a NaN-filled array of ``fill_shape``
    so that stacking across cycles remains possible.

    Parameters
    ----------
    group:
        An open netCDF4 group or dataset.
    var_name:
        Name of the variable to read.
    fill_shape:
        Shape used for the NaN placeholder when the variable is missing.
        ``None`` means we cannot construct a placeholder (returns scalar NaN).
    fill_dtype:
        Dtype for the placeholder array.

    Returns
    -------
    (data, attrs):
        * ``data`` — a plain NumPy array (masked values converted to NaN).
        * ``attrs`` — dict of variable attributes (empty if placeholder).
    """
    if var_name not in group.variables:
        shape = fill_shape if fill_shape is not None else ()
        logger.debug("Variable '%s' not found; substituting NaN placeholder.", var_name)
        return np.full(shape, np.nan, dtype=fill_dtype), {}

    raw = group.variables[var_name][:]
    attrs = {k: getattr(group.variables[var_name], k)
             for k in group.variables[var_name].ncattrs()}

    # Convert masked arrays to plain float arrays with NaN fill
    if isinstance(raw, np.ma.MaskedArray):
        data = raw.filled(np.nan).astype(float)
    else:
        data = np.asarray(raw, dtype=float)

    # Replace the large-negative sentinel value used by obs-monitor
    # (≈ -3.369e+38, i.e. roughly half of float32 min) with NaN.
    # netCDF4-python does not always expose this as a proper mask when
    # the _FillValue attribute is absent or non-standard.
    _SENTINEL_THRESHOLD = -1e36
    data[data < _SENTINEL_THRESHOLD] = np.nan

    return data, attrs


def _infer_fill_shape(
    group: nc4.Group | nc4.Dataset,
    variables: Sequence[str],
) -> tuple[int, ...] | None:
    """
    Return the shape of the first readable variable in *group* to use as
    a NaN-placeholder shape for absent variables.
    """
    for vname in variables:
        if vname in group.variables:
            return tuple(group.variables[vname].shape)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_group(
    nc_files: Sequence[str | Path],
    group_path: str,
    variables: Sequence[str],
    dim_labels: dict[str, list[str]] | None = None,
) -> xr.Dataset:
    """
    Read one NetCDF group from each file and stack results along a new
    ``analysisCycle`` dimension.

    Parameters
    ----------
    nc_files:
        Ordered list of paths to staged NetCDF files.  The order determines
        the order of ``analysisCycle`` coordinates; callers should sort by
        cycle time before passing.
    group_path:
        Slash-separated path to the target group, e.g.
        ``"byDomains/ombg/stationPressure"`` or ``"griddedBins"``.
    variables:
        Names of variables to read within that group.
    dim_labels:
        Optional mapping of ``{coordinate_name: [label, ...]}`` to attach as
        named coordinates on the returned Dataset.  The most common use case
        is passing domain label strings so that downstream code can select by
        name rather than integer index::

            dim_labels={"statisticDomain": ["SH", "NH", "CONUS", ..., "Global"]}

        The label list must have the same length as the corresponding dimension
        (``dim_0`` for ``byDomains`` data, which has ``Domain=7``).  Labels
        are attached to the generic dim name in insertion order — i.e. the
        first entry maps to ``dim_0``, the second to ``dim_1``, and so on.
        Use :func:`read_dim_labels` to obtain these lists from the files.

    Returns
    -------
    xr.Dataset
        Dataset with dimensions ``(analysisCycle, ...)`` and one data
        variable per entry in *variables*.  The ``analysisCycle`` coordinate
        holds ``numpy.datetime64`` values parsed from filenames.

        If *dim_labels* is provided, the Dataset will also carry named
        non-index coordinates (e.g. ``statisticDomain``) that make domain
        selection in figures transparent::

            ds.sel(dim_0=ds.coords["statisticDomain"] == "Global")

        Files whose group is absent are omitted from the stack (with a
        WARNING logged).  If *no* files yield data, an empty Dataset is
        returned.

    Raises
    ------
    ValueError
        If nc_files is empty or variables is empty.

    Examples
    --------
    >>> domains = read_dim_labels(nc_files, "statisticDomain")
    >>> ds = read_group(
    ...     nc_files=sorted(window_dir.glob("prepbufr_adpsfc_*.nc")),
    ...     group_path="byDomains/ombg/stationPressure",
    ...     variables=["assimilated_mean", "assimilated_RMS"],
    ...     dim_labels={"statisticDomain": domains},
    ... )
    >>> ds.coords["statisticDomain"].values
    array(['SH', 'NH', 'CONUS', 'Europe', 'Africa', 'Asia', 'Global'], dtype=object)
    """
    if not nc_files:
        raise ValueError("nc_files must not be empty.")
    if not variables:
        raise ValueError("variables must not be empty.")

    nc_files = [Path(p) for p in nc_files]
    variables = list(variables)

    cycle_times: list[np.datetime64] = []
    per_cycle: list[dict[str, np.ndarray]] = []
    collected_attrs: dict[str, dict] = {v: {} for v in variables}
    fill_shape: tuple[int, ...] | None = None  # determined from first successful read

    for path in nc_files:
        if not path.exists():
            logger.warning("File does not exist, skipping: %s", path)
            continue

        cycle_dt = _parse_cycle_from_path(path)
        if cycle_dt is None:
            logger.warning(
                "Cannot determine cycle timestamp from filename '%s'; skipping.",
                path.name,
            )
            continue

        try:
            with nc4.Dataset(path, "r") as root:
                group = _navigate_to_group(root, group_path)

                if group is None:
                    logger.warning(
                        "Group '%s' not found in '%s'; skipping this cycle.",
                        group_path,
                        path.name,
                    )
                    continue

                # Determine placeholder shape from this file (first successful hit)
                if fill_shape is None:
                    fill_shape = _infer_fill_shape(group, variables)

                arrays: dict[str, np.ndarray] = {}
                for var in variables:
                    data, attrs = _read_variable(group, var, fill_shape)
                    arrays[var] = data
                    # Keep the first non-empty attrs we see for each variable
                    if attrs and not collected_attrs[var]:
                        collected_attrs[var] = attrs

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error reading '%s' (group '%s'): %s — skipping this cycle.",
                path.name,
                group_path,
                exc,
            )
            continue

        cycle_times.append(np.datetime64(cycle_dt.replace(tzinfo=None), "ns"))
        per_cycle.append(arrays)

    # ------------------------------------------------------------------
    # Nothing was successfully read
    # ------------------------------------------------------------------
    if not per_cycle:
        logger.warning(
            "No data could be read for group '%s' from %d file(s). "
            "Returning empty Dataset.",
            group_path,
            len(nc_files),
        )
        return xr.Dataset()

    # ------------------------------------------------------------------
    # Reconcile shapes: use fill_shape for any placeholder that needed it
    # ------------------------------------------------------------------
    # At this point fill_shape may still be None if every variable was
    # missing in every file (pathological case); guard against it.
    for cycle_arrays in per_cycle:
        for var in variables:
            arr = cycle_arrays[var]
            if arr.ndim == 0 and fill_shape:
                # Scalar placeholder — expand to the correct shape
                cycle_arrays[var] = np.full(fill_shape, np.nan, dtype=float)

    # ------------------------------------------------------------------
    # Squeeze the in-file analysisCycle=1 leading dimension before stacking
    # ------------------------------------------------------------------
    # Each file stores variables with an in-file analysisCycle dim of size 1
    # (e.g. shape (1, 7) for byDomains, (1, 1, 72, 144) for griddedBins).
    # We squeeze that axis out here so that np.stack produces the clean shape
    # (N_cycles, 7) or (N_cycles, 1, 72, 144) rather than adding a redundant
    # extra leading dimension.
    for cycle_arrays in per_cycle:
        for var in variables:
            arr = cycle_arrays[var]
            if arr.ndim >= 1 and arr.shape[0] == 1:
                cycle_arrays[var] = arr.squeeze(axis=0)

    # ------------------------------------------------------------------
    # Stack along analysisCycle
    # ------------------------------------------------------------------
    cycle_coord = xr.Variable("analysisCycle", np.array(cycle_times, dtype="datetime64[ns]"))

    data_vars: dict[str, xr.Variable] = {}
    for var in variables:
        stacked = np.stack([c[var] for c in per_cycle], axis=0)  # (N_cycles, ...)
        dims = ("analysisCycle",) + tuple(f"dim_{i}" for i in range(stacked.ndim - 1))
        data_vars[var] = xr.Variable(dims, stacked, attrs=collected_attrs[var])

    coords: dict[str, xr.Variable] = {"analysisCycle": cycle_coord}

    # Attach any caller-supplied dimension labels (e.g. statisticDomain).
    # Labels are mapped onto the generic dim names (dim_0, dim_1, …) in the
    # order they are provided, which matches insertion order of dim_labels.
    if dim_labels:
        for label_idx, (coord_name, labels) in enumerate(dim_labels.items()):
            dim_name = f"dim_{label_idx}"
            coords[coord_name] = xr.Variable(dim_name, np.array(labels, dtype=object))

    ds = xr.Dataset(data_vars, coords=coords)

    logger.info(
        "read_group('%s'): loaded %d cycle(s), variables=%s%s",
        group_path,
        len(cycle_times),
        variables,
        f", dim_labels={list(dim_labels)}" if dim_labels else "",
    )
    return ds


def read_coords(
    nc_files: Sequence[str | Path],
    coords_group_path: str = "griddedBins",
    lat_var: str = "latitude",
    lon_var: str = "longitude",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Read latitude and longitude coordinate arrays from the first readable
    file.  Coordinate grids are expected to be identical across all cycles,
    so only one file needs to be consulted.

    Parameters
    ----------
    nc_files:
        Ordered list of paths to staged NetCDF files (same list passed to
        :func:`read_group`).
    coords_group_path:
        Group path that contains the lat/lon variables.
        Default is ``"griddedBins"``.
    lat_var:
        Name of the latitude variable within that group.
    lon_var:
        Name of the longitude variable within that group.

    Returns
    -------
    (lat, lon):
        Two NumPy arrays of shape ``(nlat,)`` and ``(nlon,)`` (or 2-D grids
        if the file stores them that way).

    Raises
    ------
    RuntimeError
        If no file yields valid coordinate data.

    Examples
    --------
    >>> lat, lon = read_coords(
    ...     nc_files=sorted(window_dir.glob("prepbufr_adpsfc_*.nc")),
    ...     coords_group_path="griddedBins",
    ... )
    """
    nc_files = [Path(p) for p in nc_files]

    for path in nc_files:
        if not path.exists():
            continue
        try:
            with nc4.Dataset(path, "r") as root:
                group = _navigate_to_group(root, coords_group_path)
                if group is None:
                    logger.debug(
                        "Coord group '%s' not found in '%s'; trying next file.",
                        coords_group_path,
                        path.name,
                    )
                    continue

                if lat_var not in group.variables or lon_var not in group.variables:
                    logger.debug(
                        "Lat/lon variables not found in group '%s' of '%s'; trying next.",
                        coords_group_path,
                        path.name,
                    )
                    continue

                lat = np.asarray(group.variables[lat_var][:], dtype=float)
                lon = np.asarray(group.variables[lon_var][:], dtype=float)

                # Unmask if necessary
                if isinstance(lat, np.ma.MaskedArray):
                    lat = lat.filled(np.nan)
                if isinstance(lon, np.ma.MaskedArray):
                    lon = lon.filled(np.nan)

                logger.info(
                    "read_coords: loaded lat%s lon%s from '%s' (group '%s')",
                    lat.shape,
                    lon.shape,
                    path.name,
                    coords_group_path,
                )
                return lat, lon

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error reading coords from '%s': %s — trying next file.",
                path.name,
                exc,
            )
            continue

    raise RuntimeError(
        f"Could not read coordinate arrays ('{lat_var}', '{lon_var}') "
        f"from group '{coords_group_path}' in any of the {len(nc_files)} provided file(s)."
    )


def read_dim_labels(
    nc_files: "Sequence[str | Path]",
    var_name: str = "statisticDomain",
) -> list:
    """
    Read a root-level string variable from the first readable file and
    return its values as a plain Python list.

    These root-level string arrays (``statisticDomain``, ``verticalBin``,
    ``validTime``) are identical across every cycle file — they describe the
    *structure* of the data, not the data itself — so reading from a single
    file is sufficient and correct.

    The returned list is used to attach human-readable labels as a coordinate
    on the ``byDomains`` Dataset, enabling downstream code (figure constructors,
    the dispatcher) to select domains by name rather than by integer index.

    Parameters
    ----------
    nc_files:
        Ordered list of paths to staged NetCDF files (same list passed to
        :func:`read_group`).
    var_name:
        Name of the root-level string variable to read.
        Defaults to ``"statisticDomain"``, which yields::

            ['SH', 'NH', 'CONUS', 'Europe', 'Africa', 'Asia', 'Global']

    Returns
    -------
    list[str]
        Decoded string values in file order.  Returns an empty list (with a
        WARNING) if the variable is absent from every file — callers should
        treat an empty return as "labels unavailable" rather than an error,
        since the data arrays are still readable without them.

    Examples
    --------
    >>> domains = read_dim_labels(nc_files, var_name="statisticDomain")
    ['SH', 'NH', 'CONUS', 'Europe', 'Africa', 'Asia', 'Global']
    """
    nc_files = [Path(p) for p in nc_files]

    for path in nc_files:
        if not path.exists():
            continue
        try:
            with nc4.Dataset(path, "r") as root:
                if var_name not in root.variables:
                    logger.debug(
                        "'%s' not found as a root variable in '%s'; trying next file.",
                        var_name,
                        path.name,
                    )
                    continue

                raw = root.variables[var_name][:]

                # netCDF4 returns string variables as numpy object arrays of
                # bytes or str depending on NC type (NC_STRING vs CHAR).
                # Normalise to plain Python str in all cases.
                labels = []
                for item in np.asarray(raw).flat:
                    if isinstance(item, bytes):
                        labels.append(item.decode("utf-8").strip())
                    else:
                        labels.append(str(item).strip())

                logger.info(
                    "read_dim_labels('%s'): %s from '%s'",
                    var_name,
                    labels,
                    path.name,
                )
                return labels

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error reading dim labels from '%s': %s — trying next file.",
                path.name,
                exc,
            )
            continue

    logger.warning(
        "read_dim_labels: '%s' not found in any of the %d provided file(s). "
        "Domain filtering by name will be unavailable.",
        var_name,
        len(nc_files),
    )
    return []


# ---------------------------------------------------------------------------
# Typed validation exceptions
# ---------------------------------------------------------------------------
# These are defined here so that driver.py can catch them specifically and
# route each failure mode to an appropriate log message. All three are
# subclasses of ValueError so callers that don't need the distinction can
# catch the base class.

class CorruptFileError(ValueError):
    """
    Raised when a NetCDF file exists on disk but cannot be opened by
    netCDF4 (e.g. truncated, not a valid NetCDF file, I/O error).
    """


class MissingGroupError(ValueError):
    """
    Raised when a NetCDF file opens successfully but a required group path
    is absent from its hierarchy.

    Attributes
    ----------
    group_path : str
        The slash-separated group path that was expected but not found.
    """
    def __init__(self, group_path: str, filename: str) -> None:
        self.group_path = group_path
        super().__init__(
            f"Group '{group_path}' not found in '{filename}'."
        )


class MissingVariableError(ValueError):
    """
    Raised when a required group exists but a specific variable is absent
    from it.

    Attributes
    ----------
    group_path : str
        The group in which the variable was expected.
    variable : str
        The variable name that was expected but not found.
    """
    def __init__(self, variable: str, group_path: str, filename: str) -> None:
        self.group_path = group_path
        self.variable = variable
        super().__init__(
            f"Variable '{variable}' not found in group '{group_path}' "
            f"of '{filename}'."
        )


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def validate_nc_file(
    path: "Path",
    coords_group: str,
    figure_specs: list[dict],
) -> None:
    """
    Validate that a staged NetCDF file satisfies all structural requirements
    for the given figure specs before it is handed to the plotting pipeline.

    Checks performed (in order):
    1. File opens without error                              → CorruptFileError
    2. The coords group (e.g. ``griddedBins``) exists        → MissingGroupError
    3. Each unique ``group_path`` in figure_specs exists     → MissingGroupError
    4. Each ``stat`` variable exists within its group_path   → MissingVariableError

    Steps 3 and 4 deduplicate across figure specs so each unique
    ``(group_path, stat)`` pair is checked exactly once, regardless of how
    many specs share it.

    Parameters
    ----------
    path:
        Path to the staged ``.nc`` file.
    coords_group:
        Top-level group containing lat/lon coordinates, taken from
        ``nc_groups.coords`` in the plot config (e.g. ``"griddedBins"``).
    figure_specs:
        List of figure spec dicts from the plot config.  Each must have
        ``group_path`` and ``stat`` keys (already validated by the
        dispatcher's ``_validate_config`` before this is called).

    Raises
    ------
    CorruptFileError
        If the file cannot be opened by netCDF4.
    MissingGroupError
        If any required group is absent from the file hierarchy.
    MissingVariableError
        If any required stat variable is absent from its group.

    Notes
    -----
    This function intentionally performs *only* structural checks — it does
    not read any data values. It is designed to be fast (one open per file,
    no array reads) and to be called in the driver before the plotting
    pipeline so that bad files can be quarantined and replaced with stubs
    rather than silently producing incomplete figures.
    """
    path = Path(path)
    fname = path.name

    # 1. File must be openable
    try:
        root = nc4.Dataset(path, "r")
    except Exception as exc:
        raise CorruptFileError(
            f"'{fname}' could not be opened by netCDF4: {exc}"
        ) from exc

    with root:
        # 2. Coords group must exist
        if _navigate_to_group(root, coords_group) is None:
            raise MissingGroupError(coords_group, fname)

        # 3 & 4. Check each unique (group_path, stat) pair once
        seen: set[tuple[str, str]] = set()
        for spec in figure_specs:
            group_path = spec["group_path"]
            stat = spec["stat"]
            key = (group_path, stat)
            if key in seen:
                continue
            seen.add(key)

            group = _navigate_to_group(root, group_path)
            if group is None:
                raise MissingGroupError(group_path, fname)

            if stat not in group.variables:
                raise MissingVariableError(stat, group_path, fname)
