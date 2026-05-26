"""
obs_monitor.plotting.transforms
================================

Reductions applied to Datasets returned by :mod:`obs_monitor.plotting.reader`
before they are handed to figure constructors.

Shapes after stacking N cycles
-------------------------------
``byDomains`` group  →  ``(analysisCycle=N, Domain=7)``
``griddedBins`` group →  ``(analysisCycle=N, binsZDim=1, binsYDim=72, binsXDim=144)``

This module provides two primary transforms:

``cycle_mean``
    Reduce across ``analysisCycle`` with :func:`numpy.nanmean`, producing
    a time-averaged field.  Used by map/gridded figures.

``squeeze_gridded``
    Drop the degenerate ``binsZDim=1`` vertical axis so downstream code
    works with clean ``(binsYDim, binsXDim)`` arrays.

``attach_coords``
    Attach lat/lon 2-D arrays (from :func:`~obs_monitor.plotting.reader.read_coords`)
    as Dataset coordinates so figure code can access them by name.

All functions are pure — they return new Datasets and never mutate inputs.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public transforms
# ---------------------------------------------------------------------------


def cycle_mean(ds: xr.Dataset, variables: Sequence[str] | None = None) -> xr.Dataset:
    """
    Average across the ``analysisCycle`` dimension using :func:`numpy.nanmean`.

    Missing values (NaN) are ignored, matching the sentinel-scrubbing done in
    the reader.  If every cycle is NaN for a given grid cell, the result is
    NaN for that cell (not zero).

    Parameters
    ----------
    ds:
        Dataset with an ``analysisCycle`` dimension, as returned by
        :func:`~obs_monitor.plotting.reader.read_group`.
    variables:
        Subset of variables to reduce.  ``None`` (default) reduces all
        data variables in *ds*.

    Returns
    -------
    xr.Dataset
        New Dataset without the ``analysisCycle`` dimension.  Each variable
        is the nanmean across cycles.  Original variable attributes are
        preserved.  A ``n_cycles`` scalar coordinate records how many cycles
        contributed.

    Raises
    ------
    ValueError
        If ``analysisCycle`` is not a dimension in *ds*.

    Examples
    --------
    >>> ds_mean = cycle_mean(ds_by_domains)
    >>> ds_mean["assimilated_mean"].dims
    ('dim_0',)                  # byDomains: analysisCycle removed, leaving Domain

    >>> ds_mean = cycle_mean(ds_gridded)
    >>> ds_mean["assimilated_mean"].dims
    ('dim_0', 'dim_1', 'dim_2') # griddedBins before squeeze_gridded(): binsZDim × binsYDim × binsXDim
    """
    if "analysisCycle" not in ds.dims:
        raise ValueError(
            "'analysisCycle' is not a dimension in the supplied Dataset. "
            "Was this Dataset produced by read_group()?"
        )

    target_vars = list(variables) if variables is not None else list(ds.data_vars)
    missing = [v for v in target_vars if v not in ds.data_vars]
    if missing:
        raise ValueError(f"Variables not found in Dataset: {missing}")

    n_cycles = ds.sizes["analysisCycle"]
    reduced: dict[str, xr.DataArray] = {}

    for vname in target_vars:
        da = ds[vname]
        axis = da.dims.index("analysisCycle")
        mean_vals = np.nanmean(da.values, axis=axis)
        new_dims = tuple(d for d in da.dims if d != "analysisCycle")
        reduced[vname] = xr.DataArray(mean_vals, dims=new_dims, attrs=da.attrs)

    # Preserve coordinates that don't depend on analysisCycle
    new_coords = {
        k: v for k, v in ds.coords.items() if "analysisCycle" not in v.dims
    }
    new_coords["n_cycles"] = xr.DataArray(n_cycles, attrs={"long_name": "number of cycles averaged"})

    result = xr.Dataset(reduced, coords=new_coords)

    logger.info(
        "cycle_mean: averaged %d cycle(s) for variable(s) %s",
        n_cycles,
        target_vars,
    )
    return result


def squeeze_gridded(ds: xr.Dataset, zdim: str = "dim_0") -> xr.Dataset:
    """
    Drop the degenerate vertical dimension (``binsZDim=1``) from gridded variables.

    After stacking across cycles, gridded variables have shape::

        (analysisCycle, binsZDim=1, binsYDim=72, binsXDim=144)

    which — after :func:`cycle_mean` — becomes::

        (binsZDim=1, binsYDim=72, binsXDim=144)

    This function squeezes out the size-1 vertical axis so that figure code
    receives clean ``(binsYDim, binsXDim)`` arrays matching the lat/lon grids.

    Parameters
    ----------
    ds:
        Dataset, typically the output of :func:`cycle_mean` on a gridded group.
    zdim:
        Name of the degenerate vertical dimension to remove.
        Defaults to ``"dim_1"`` (the name assigned by the reader when the
        in-file dimension is ``binsZDim``).

    Returns
    -------
    xr.Dataset
        New Dataset with *zdim* squeezed out of every variable that has it.
        Variables that don't have *zdim* are passed through unchanged.

    Examples
    --------
    >>> ds_squeezed = squeeze_gridded(cycle_mean(ds_gridded))
    >>> ds_squeezed["assimilated_mean"].dims
    ('dim_1', 'dim_2')          # binsZDim (dim_0) squeezed out; remaining: binsYDim × binsXDim
    """
    out: dict[str, xr.DataArray] = {}
    for vname, da in ds.data_vars.items():
        if zdim in da.dims:
            idx = da.dims.index(zdim)
            if da.shape[idx] != 1:
                logger.warning(
                    "squeeze_gridded: '%s' has dim '%s' of size %d (expected 1); skipping squeeze.",
                    vname,
                    zdim,
                    da.shape[idx],
                )
                out[vname] = da
            else:
                out[vname] = da.squeeze(zdim, drop=True)
        else:
            out[vname] = da

    result = xr.Dataset(out, coords=ds.coords, attrs=ds.attrs)

    squeezed_vars = [v for v in out if zdim not in out[v].dims and zdim in ds[v].dims]
    logger.info("squeeze_gridded: removed dim '%s' from %s", zdim, squeezed_vars)
    return result


def attach_coords(
    ds: xr.Dataset,
    lat: np.ndarray,
    lon: np.ndarray,
    lat_dim: str = "dim_1",
    lon_dim: str = "dim_2",
) -> xr.Dataset:
    """
    Attach 2-D latitude and longitude arrays as Dataset coordinates.

    The lat/lon arrays from :func:`~obs_monitor.plotting.reader.read_coords`
    have shape ``(72, 144)`` — already a meshgrid.  After :func:`cycle_mean`
    and :func:`squeeze_gridded` the gridded data variables have dims
    ``(dim_2, dim_3)`` (binsYDim × binsXDim), so we assign lat/lon over
    those same dims.

    Parameters
    ----------
    ds:
        Dataset from :func:`squeeze_gridded` (or :func:`cycle_mean` if you
        skipped the squeeze).
    lat:
        2-D latitude array of shape ``(binsYDim, binsXDim)``.
    lon:
        2-D longitude array of shape ``(binsYDim, binsXDim)``.
    lat_dim, lon_dim:
        Names of the Dataset dimensions that correspond to the lat/lon axes.
        Defaults match the reader's generic naming after cycle_mean +
        squeeze_gridded (``dim_2``, ``dim_3``).

    Returns
    -------
    xr.Dataset
        New Dataset with ``latitude`` and ``longitude`` added as non-index
        coordinates of shape ``(lat_dim, lon_dim)``.

    Examples
    --------
    >>> lat, lon = read_coords(nc_files)
    >>> ds_final = attach_coords(squeeze_gridded(cycle_mean(ds_gridded)), lat, lon)
    >>> ds_final.coords["latitude"].shape
    (72, 144)
    """
    new_coords = dict(ds.coords)
    new_coords["latitude"] = xr.DataArray(
        lat, dims=(lat_dim, lon_dim), attrs={"units": "degrees_north"}
    )
    new_coords["longitude"] = xr.DataArray(
        lon, dims=(lat_dim, lon_dim), attrs={"units": "degrees_east"}
    )
    result = ds.assign_coords(new_coords)
    logger.info(
        "attach_coords: lat%s lon%s attached on dims ('%s', '%s')",
        lat.shape, lon.shape, lat_dim, lon_dim,
    )
    return result


# ---------------------------------------------------------------------------
# Convenience: full gridded pipeline in one call
# ---------------------------------------------------------------------------


def prepare_gridded(
    ds: xr.Dataset,
    lat: np.ndarray,
    lon: np.ndarray,
    variables: Sequence[str] | None = None,
    zdim: str = "dim_0",
    lat_dim: str = "dim_1",
    lon_dim: str = "dim_2",
) -> xr.Dataset:
    """
    Full transform pipeline for a gridded group: mean → squeeze → attach coords.

    This is the single call that ``dispatcher.py`` makes for ``map_gridded``
    figure specs.

    Parameters
    ----------
    ds:
        Raw Dataset from :func:`~obs_monitor.plotting.reader.read_group`
        for a ``griddedBins/…`` group path.
    lat, lon:
        2-D coordinate arrays from
        :func:`~obs_monitor.plotting.reader.read_coords`, shape ``(72, 144)``.
    variables:
        Variables to include.  ``None`` processes all.
    zdim:
        Degenerate vertical dim name (``"dim_1"`` by default — the
        in-file ``binsZDim``).
    lat_dim, lon_dim:
        Spatial dim names after squeezing (``"dim_2"``, ``"dim_3"``).

    Returns
    -------
    xr.Dataset
        Cycle-averaged, squeezed Dataset with ``latitude`` and ``longitude``
        coordinates attached, ready to pass to figure constructors.

    Examples
    --------
    >>> ds_raw   = read_group(nc_files, "griddedBins/ombg/stationPressure", variables)
    >>> lat, lon = read_coords(nc_files)
    >>> ds_plot  = prepare_gridded(ds_raw, lat, lon)
    >>> ds_plot["assimilated_mean"].shape
    (72, 144)
    """
    ds = cycle_mean(ds, variables=variables)
    ds = squeeze_gridded(ds, zdim=zdim)
    ds = attach_coords(ds, lat, lon, lat_dim=lat_dim, lon_dim=lon_dim)
    return ds


def prepare_time_series(
    ds: xr.Dataset,
    variables: Sequence[str] | None = None,
) -> xr.Dataset:
    """
    Prepare a ``byDomains`` Dataset for time-series plotting.

    No averaging is applied — we want to preserve every cycle as a point
    on the time axis.  This function just validates the Dataset and
    optionally subsets variables.

    Shape in: ``(analysisCycle=N, dim_0=7)`` (Domain axis)
    Shape out: same — untouched.

    Parameters
    ----------
    ds:
        Raw Dataset from :func:`~obs_monitor.plotting.reader.read_group`
        for a ``byDomains/…`` group path.
    variables:
        Variables to keep.  ``None`` keeps all.

    Returns
    -------
    xr.Dataset
        Validated (and optionally subsetted) Dataset ready for time-series
        figure constructors.

    Examples
    --------
    >>> ds_ts = prepare_time_series(ds_raw, variables=["assimilated_mean"])
    >>> ds_ts["assimilated_mean"].dims
    ('analysisCycle', 'dim_0')
    """
    if "analysisCycle" not in ds.dims:
        raise ValueError(
            "'analysisCycle' is not a dimension in the supplied Dataset. "
            "Was this Dataset produced by read_group()?"
        )

    if variables is not None:
        missing = [v for v in variables if v not in ds.data_vars]
        if missing:
            raise ValueError(f"Variables not found in Dataset: {missing}")
        ds = ds[list(variables)]

    logger.info(
        "prepare_time_series: %d cycle(s), variables=%s",
        ds.sizes["analysisCycle"],
        list(ds.data_vars),
    )
    return ds
