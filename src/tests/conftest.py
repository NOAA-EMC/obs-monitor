"""
tests/plotting/conftest.py
==========================

Shared pytest fixtures for the obs_monitor.plotting test suite.

The central fixture is ``write_nc_file``, a factory that writes minimal but
structurally correct NetCDF files matching the exact group hierarchy confirmed
from the real obs-monitor output:

Root dimensions:  analysisCycle=1, Domain=7, binsZDim=1, binsYDim=72, binsXDim=144
Root variables:   validTime(1,), statisticDomain(7,), verticalBin(1,)

Groups:
  byDomains/
    {stat_group}/         e.g. ombg/stationPressure
      assimilated_mean    (1, 7)  float32
      assimilated_count   (1, 7)  int32
      assimilated_RMS     (1, 7)  float32
      monitored_mean      (1, 7)  float32  — filled with sentinel
      rejected_mean       (1, 7)  float32
      ...
  griddedBins/
    latitude              (72, 144) float32   ← 2-D meshgrid
    longitude             (72, 144) float32
    {stat_group}/
      assimilated_mean    (1, 1, 72, 144) float32
      assimilated_count   (1, 1, 72, 144) int32
      assimilated_RMS     (1, 1, 72, 144) float32
      ...

All fixtures use ``tmp_path`` so files are created in pytest's managed temp
directory and cleaned up automatically after each test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import netCDF4 as nc4
import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Constants mirroring the real file schema
# ---------------------------------------------------------------------------

DOMAINS = ["SH", "NH", "CONUS", "Europe", "Africa", "Asia", "Global"]
N_DOMAINS = len(DOMAINS)          # 7
BINS_Z = 1
BINS_Y = 72
BINS_X = 144
SENTINEL = -3.36879526214505e+38  # the fill value used in real files

# Stat variables present in each byDomains group — mirrors real file
DOMAIN_VARS = [
    "assimilated_mean",
    "assimilated_count",
    "assimilated_RMS",
    "monitored_mean",
    "monitored_count",
    "monitored_RMS",
    "rejected_mean",
    "rejected_count",
    "rejected_RMS",
]

# Same variables in griddedBins groups
GRIDDED_VARS = DOMAIN_VARS  # identical names, different shape


# ---------------------------------------------------------------------------
# Low-level NetCDF writer
# ---------------------------------------------------------------------------

def _write_nc_file(
    path: Path,
    cycle_dt: datetime,
    ob_type: str = "prepbufr_adpsfc",
    stat_group: str = "ombg/stationPressure",
    domain_data: dict[str, np.ndarray] | None = None,
    gridded_data: dict[str, np.ndarray] | None = None,
    include_sentinel: bool = True,
) -> Path:
    """
    Write a single synthetic NetCDF file that matches the real obs-monitor
    group schema.

    Parameters
    ----------
    path:
        Full output path including filename.
    cycle_dt:
        UTC datetime for this cycle; used to populate ``validTime``.
    ob_type:
        Observation type string (unused in file content but kept for clarity).
    stat_group:
        Slash-separated sub-group path under both ``byDomains`` and
        ``griddedBins``, e.g. ``"ombg/stationPressure"``.
    domain_data:
        Optional dict mapping variable name → array of shape ``(1, 7)`` to
        use as the ``byDomains`` variable values.  Defaults to synthetic data.
    gridded_data:
        Optional dict mapping variable name → array of shape
        ``(1, 1, 72, 144)`` for the ``griddedBins`` variables.
        Defaults to synthetic data.
    include_sentinel:
        If True, ``monitored_*`` variables are filled with the real sentinel
        value so tests can verify sentinel scrubbing.

    Returns
    -------
    Path
        The path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with nc4.Dataset(path, "w", format="NETCDF4") as ds:

        # ---- Root dimensions ----
        ds.createDimension("analysisCycle", 1)
        ds.createDimension("Domain", N_DOMAINS)
        ds.createDimension("binsZDim", BINS_Z)
        ds.createDimension("binsYDim", BINS_Y)
        ds.createDimension("binsXDim", BINS_X)

        # ---- Root string variables ----
        vt = ds.createVariable("validTime", str, ("analysisCycle",))
        vt[0] = cycle_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        sd = ds.createVariable("statisticDomain", str, ("Domain",))
        for i, name in enumerate(DOMAINS):
            sd[i] = name

        vb = ds.createVariable("verticalBin", str, ("analysisCycle",))
        vb[0] = "all"

        # ---- byDomains group hierarchy ----
        grp_by = ds.createGroup("byDomains")
        parts = stat_group.split("/")

        # Navigate / create nested groups
        current = grp_by
        for part in parts:
            current = current.createGroup(part)
        stat_leaf = current  # e.g. byDomains/ombg/stationPressure

        for vname in DOMAIN_VARS:
            if "count" in vname:
                dtype = "i4"
                default = np.zeros((1, N_DOMAINS), dtype=np.int32)
                default[0, :] = [10035, 68033, 24199, 20753, 3353, 12462, 78068]
            else:
                dtype = "f4"
                if include_sentinel and "monitored" in vname:
                    default = np.full((1, N_DOMAINS), SENTINEL, dtype=np.float32)
                else:
                    rng = np.random.default_rng(seed=abs(hash(vname)) % (2**31))
                    default = rng.uniform(-200, 200, (1, N_DOMAINS)).astype(np.float32)

            v = stat_leaf.createVariable(
                vname, dtype, ("analysisCycle", "Domain")
            )
            v[:] = (domain_data or {}).get(vname, default)

        # ---- griddedBins group hierarchy ----
        grp_grid = ds.createGroup("griddedBins")

        # 2-D lat/lon meshgrid matching real file
        lat_1d = np.linspace(-88.75, 88.75, BINS_Y, dtype=np.float32)
        lon_1d = np.linspace(-178.75, 178.75, BINS_X, dtype=np.float32)
        lon2d, lat2d = np.meshgrid(lon_1d, lat_1d)  # both (72, 144)

        vl = grp_grid.createVariable("latitude", "f4", ("binsYDim", "binsXDim"))
        vl[:] = lat2d
        vo = grp_grid.createVariable("longitude", "f4", ("binsYDim", "binsXDim"))
        vo[:] = lon2d

        # Navigate / create nested groups under griddedBins
        current = grp_grid
        for part in parts:
            current = current.createGroup(part)
        gridded_leaf = current

        for vname in GRIDDED_VARS:
            if "count" in vname:
                dtype = "i4"
                default = np.zeros((1, BINS_Z, BINS_Y, BINS_X), dtype=np.int32)
            else:
                dtype = "f4"
                if include_sentinel and "monitored" in vname:
                    default = np.full(
                        (1, BINS_Z, BINS_Y, BINS_X), SENTINEL, dtype=np.float32
                    )
                else:
                    rng = np.random.default_rng(seed=abs(hash(vname + "_grid")) % (2**31))
                    default = rng.uniform(-500, 500, (1, BINS_Z, BINS_Y, BINS_X)).astype(np.float32)

            v = gridded_leaf.createVariable(
                vname, dtype,
                ("analysisCycle", "binsZDim", "binsYDim", "binsXDim"),
            )
            v[:] = (gridded_data or {}).get(vname, default)

    return path


# ---------------------------------------------------------------------------
# Filename helper — matches obs-monitor naming convention
# ---------------------------------------------------------------------------

def nc_filename(ob_type: str, cycle_dt: datetime) -> str:
    """Return a filename following the obs-monitor convention."""
    ts = cycle_dt.strftime("%Y%m%d%H")
    return f"{ob_type}_{ts}_output_atmos.nc"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ob_type() -> str:
    """Default observation type used across tests."""
    return "prepbufr_adpsfc"


@pytest.fixture
def stat_group() -> str:
    """Default stat group path used across tests."""
    return "ombg/stationPressure"


@pytest.fixture
def cycle_times() -> list[datetime]:
    """Four consecutive 6-hourly UTC cycle datetimes for a multi-cycle window."""
    return [
        datetime(2025, 11, 13, 0, tzinfo=timezone.utc),
        datetime(2025, 11, 13, 6, tzinfo=timezone.utc),
        datetime(2025, 11, 13, 12, tzinfo=timezone.utc),
        datetime(2025, 11, 13, 18, tzinfo=timezone.utc),
    ]


@pytest.fixture
def write_nc_file():
    """
    Factory fixture. Returns the ``_write_nc_file`` function so individual
    tests can write files with custom parameters while still benefiting from
    pytest's ``tmp_path`` cleanup.

    Usage::

        def test_something(write_nc_file, tmp_path, ob_type, cycle_times):
            path = write_nc_file(
                tmp_path / nc_filename(ob_type, cycle_times[0]),
                cycle_times[0],
            )
    """
    return _write_nc_file


@pytest.fixture
def single_nc_file(tmp_path, ob_type, cycle_times, write_nc_file):
    """
    A single synthetic NetCDF file for the first cycle in ``cycle_times``.
    Useful for tests that only need one file.
    """
    path = tmp_path / nc_filename(ob_type, cycle_times[0])
    return write_nc_file(path, cycle_times[0])


@pytest.fixture
def multi_nc_files(tmp_path, ob_type, cycle_times, write_nc_file):
    """
    Four synthetic NetCDF files — one per entry in ``cycle_times``.
    Sorted by filename (equivalent to chronological order).
    Useful for testing stacking across cycles.
    """
    paths = []
    for dt in cycle_times:
        path = tmp_path / nc_filename(ob_type, dt)
        write_nc_file(path, dt)
        paths.append(path)
    return sorted(paths)


@pytest.fixture
def multi_nc_files_with_gap(tmp_path, ob_type, cycle_times, write_nc_file):
    """
    Three synthetic NetCDF files with the second cycle (index 1) missing.
    Useful for testing graceful handling of missing cycles.
    """
    paths = []
    for i, dt in enumerate(cycle_times):
        if i == 1:
            continue  # intentional gap
        path = tmp_path / nc_filename(ob_type, dt)
        write_nc_file(path, dt)
        paths.append(path)
    return sorted(paths)
