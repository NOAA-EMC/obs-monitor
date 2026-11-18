"""
obs_monitor.stats.cache
=======================

Per-cycle summaries on disk, so a rolling window only summarizes the newest
cycle and re-reads the rest (a summary is KBs to a few MB; the diag file it
came from is much larger).

Layout::

    <root>/<obs_space>/<variable>/summary_<obs_space>_<variable>_YYYYMMDDHH.nc

Each file carries a cache key saying how it was made
(:mod:`obs_monitor.stats.cache_check`); the pipeline only reuses a summary
whose key matches the current run.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import xarray as xr

from obs_monitor.stats.cache_check import CacheKey


def summary_path(root: str | Path, obs_space: str, variable: str, cycle: datetime) -> Path:
    return Path(root) / obs_space / variable / f"summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc"


def write_summary(ds: xr.Dataset, path: str | Path, key: CacheKey | None = None) -> Path:
    """
    Write atomically (temp file + rename) so a killed job never leaves a
    half-written summary. ``key`` is written into the file's attributes
    (see :mod:`obs_monitor.stats.cache_check`); a summary without one is never
    reused by the pipeline.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if key is not None:
        ds = ds.copy()
        ds.attrs.update(key.attrs())
    try:
        ds.to_netcdf(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def read_summary(path: str | Path) -> xr.Dataset | None:
    """Load a cached summary, or ``None`` if it does not exist or cannot be read."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with xr.open_dataset(path) as ds:
            return ds.load()
    except (OSError, ValueError):
        return None
