"""
obs_monitor.stats.summary
=========================

Turn one cycle of one simulated variable (the Dataset from
:func:`obs_monitor.io.read_ioda`) into a small **CycleSummary**: statistics by
domain and QC class, plus gridded means for maps. Every figure reads
summaries, never raw diag files.

CycleSummary contract
---------------------
::

    Coords:  cycle (scalar datetime64), domain, qc_class, lat, lon, [channel]
    Vars:    <field>_count  ([channel,] qc_class, domain)   int64
             <field>_mean   ([channel,] qc_class, domain)   float64
             <field>_rms    ([channel,] qc_class, domain)   float64
             <field>_std    ([channel,] qc_class, domain)   float64   (population, ddof=0)
             <field>_gridded_count  ([channel,] lat, lon)   int32     (gridded_qc class only)
             <field>_gridded_mean   ([channel,] lat, lon)   float32
    Attrs:   obs_space, variable, units, source_path, gridded_qc

``field`` is one of ``ombg``, ``oman``, ``obs`` (whichever the file has).
Statistics over zero points are NaN with count 0.

QC classes
----------
Named to match the old stat files (``assimilated_*``, ``monitored_*``,
``rejected_*``), plus ``all``. All classes only count locations where the
field is not missing.

* ``all``: every such location.
* ``assimilated``: ``EffectiveQC == 0`` (UFO ``pass``).
* ``monitored``: ``EffectiveQC == 1`` (UFO ``passive``: computed, not assimilated).
* ``rejected``: any other flag (``EffectiveQC > 1``).

TODO(PR5): confirm these against the stat files with compare_stats.py.

O-B and the observation use the background QC (``qc_bg``); O-A uses the
final-analysis QC (``qc_an``), falling back to ``qc_bg`` when the file has a
single iteration. These definitions live only here.

Several cycles are stacked with :func:`stack_cycles`, which builds the time
axis from the *expected* cycle list so missing cycles are NaN gaps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

import numpy as np
import xarray as xr

from obs_monitor.stats.regions import Domain, Grid

#: QC classes, in output order.
QC_CLASSES: tuple[str, ...] = ("all", "assimilated", "monitored", "rejected")

QC_PASS = 0
QC_PASSIVE = 1

#: Fields summarized, and the QC field each is classified by (first one present wins).
FIELD_QC: dict[str, tuple[str, ...]] = {
    "ombg": ("qc_bg",),
    "oman": ("qc_an", "qc_bg"),
    "obs": ("qc_bg",),
}

STATS: tuple[str, ...] = ("count", "mean", "rms", "std")


def _class_masks(values: np.ndarray, qc: np.ndarray | None) -> np.ndarray:
    """Boolean masks, shape (n_class, Location, channel)."""
    finite = np.isfinite(values)
    if qc is None:
        none = np.zeros_like(finite)
        return np.stack([finite, none, none, none])
    return np.stack([finite, finite & (qc == QC_PASS), finite & (qc == QC_PASSIVE), finite & (qc > QC_PASSIVE)])


def reduce_cycle(
    ds: xr.Dataset,
    cycle: datetime,
    domains: Sequence[Domain],
    grid: Grid,
    *,
    fields: Sequence[str] = tuple(FIELD_QC),
    gridded_qc: str = "assimilated",
) -> xr.Dataset:
    """
    Summarize one cycle of one variable.

    Parameters
    ----------
    ds
        Output of :func:`obs_monitor.io.read_ioda` (dims ``Location`` and
        optionally ``channel``; coords ``latitude``, ``longitude``).
    cycle
        Analysis cycle the file belongs to (from the catalog).
    domains, grid
        From :func:`obs_monitor.stats.load_regions`.
    fields
        Fields to summarize; ones the file lacks are skipped.
    gridded_qc
        QC class used for the gridded maps (one class keeps radiance
        summaries small).
    """
    if gridded_qc not in QC_CLASSES:
        raise ValueError(f"gridded_qc must be one of {QC_CLASSES}, got {gridded_qc!r}.")
    has_channel = "channel" in ds.dims
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    dom = np.stack([d.mask(lat, lon) for d in domains]).astype(np.float64)   # (domain, Location)
    flat = grid.flat_index(lat, lon)
    nlat, nlon = grid.shape
    gq = QC_CLASSES.index(gridded_qc)

    stat_dims = ("channel", "qc_class", "domain") if has_channel else ("qc_class", "domain")
    grid_dims = ("channel", "lat", "lon") if has_channel else ("lat", "lon")
    out: dict[str, tuple] = {}

    for field in fields:
        if field not in ds:
            continue
        values = ds[field].values
        qc_name = next((q for q in FIELD_QC.get(field, ("qc_bg",)) if q in ds), None)
        qc = ds[qc_name].values if qc_name else None
        if not has_channel:
            values = values[:, None]
            qc = None if qc is None else qc[:, None]

        masks = _class_masks(values, qc)                         # (class, Location, channel)
        x = np.where(np.isfinite(values), values, 0.0)
        w = masks.astype(np.float64)
        # (domain, Location) @ (class, Location, channel) -> (class, domain, channel)
        count = np.einsum("dl,clk->cdk", dom, w)
        total = np.einsum("dl,clk->cdk", dom, w * x)
        sumsq = np.einsum("dl,clk->cdk", dom, w * x * x)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = total / count
            msq = sumsq / count
        rms = np.sqrt(msq)
        std = np.sqrt(np.maximum(msq - mean * mean, 0.0))

        def arrange(a):
            a = np.moveaxis(a, -1, 0)                            # (channel, class, domain)
            return a if has_channel else a[0]

        out[f"{field}_count"] = (stat_dims, arrange(count).astype(np.int64))
        out[f"{field}_mean"] = (stat_dims, arrange(mean))
        out[f"{field}_rms"] = (stat_dims, arrange(rms))
        out[f"{field}_std"] = (stat_dims, arrange(std))

        nchan = values.shape[1]
        g_count = np.zeros((nchan, nlat * nlon), dtype=np.int64)
        g_sum = np.zeros((nchan, nlat * nlon), dtype=np.float64)
        for k in range(nchan):
            sel = masks[gq, :, k] & (flat >= 0)
            g_count[k] = np.bincount(flat[sel], minlength=nlat * nlon)
            g_sum[k] = np.bincount(flat[sel], weights=values[sel, k], minlength=nlat * nlon)
        with np.errstate(invalid="ignore", divide="ignore"):
            g_mean = (g_sum / g_count).astype(np.float32)
        g_count = g_count.reshape(nchan, nlat, nlon).astype(np.int32)
        g_mean = g_mean.reshape(nchan, nlat, nlon)
        out[f"{field}_gridded_count"] = (grid_dims, g_count if has_channel else g_count[0])
        out[f"{field}_gridded_mean"] = (grid_dims, g_mean if has_channel else g_mean[0])

    coords = {
        "domain": [d.name for d in domains],
        "qc_class": list(QC_CLASSES),
        "lat": grid.lat_centers,
        "lon": grid.lon_centers,
    }
    if has_channel:
        coords["channel"] = ds["channel"].values
    coords["cycle"] = np.datetime64(cycle, "ns")

    attrs = {k: ds.attrs[k] for k in ("obs_space", "variable", "units", "source_path") if ds.attrs.get(k) is not None}
    attrs["gridded_qc"] = gridded_qc
    return xr.Dataset(out, coords=coords, attrs=attrs)


def stack_cycles(summaries: Mapping[datetime, xr.Dataset], cycles: Sequence[datetime]) -> xr.Dataset | None:
    """
    Stack per-cycle summaries along ``cycle`` on the *expected* cycle list.

    Cycles absent from ``summaries`` become NaN (counts too), so time series
    show a gap instead of silently joining neighbours. Returns ``None`` if no
    cycle has data.
    """
    present = [(c, summaries[c]) for c in cycles if summaries.get(c) is not None]
    if not present:
        return None
    parts = [s.drop_vars("cycle", errors="ignore").expand_dims(cycle=[np.datetime64(c, "ns")]) for c, s in present]
    stacked = xr.concat(parts, dim="cycle", combine_attrs="override")
    expected = np.array([np.datetime64(c, "ns") for c in cycles])
    stacked = stacked.reindex(cycle=expected)
    stacked.attrs.pop("source_path", None)
    return stacked
