"""
obs_monitor.stats.cache
=======================

Per-cycle summaries on disk, so a rolling window only summarizes the newest
cycle and re-reads the rest (a summary is KBs to a few MB; the diag file it
came from is much larger).

Layout::

    <root>/<obs_space>/<variable>/summary_<obs_space>_<variable>_YYYYMMDDHH.nc
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import xarray as xr


def summary_path(root: str | Path, obs_space: str, variable: str, cycle: datetime) -> Path:
    return Path(root) / obs_space / variable / f"summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc"


def write_summary(ds: xr.Dataset, path: str | Path) -> Path:
    """Write atomically (temp file + rename) so a killed job never leaves a half-written summary."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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
