"""
obs_monitor.plotting.summary_figures
====================================

Figures from summaries (``obs_monitor.stats``).

::

    stacked = stack_cycles(summaries, cycles)            # obs_monitor.stats
    result = plot_obs_space(stacked, "prepbufr_adpsfc", specs, output_dir)
    result.written, result.failed

The rendering is the same as for the old stat files: :func:`time_series_dataset` and
:func:`gridded_dataset` reshape a stacked summary into exactly what
:class:`~obs_monitor.plotting.figures.TimeSeriesFigure` and
:class:`~obs_monitor.plotting.figures.MapGriddedFigure` already take, and the
file names come from :mod:`~obs_monitor.plotting.naming`, so the website's
PNG names don't change.

Differences from the stat-file figures
--------------------------------------
* Missing cycles are NaN in the summary, so time series show a gap (no stub files).
* The map is the count-weighted mean over the window (every assimilated ob
  counts once), instead of the unweighted mean of per-cycle cell means.
* Map colour limits default to symmetric about zero for means.
* A figure that fails is logged and recorded in ``result.failed``; the others
  are still made.
* A single-channel obs space (e.g. VIIRS AOD) is plotted like conventional data;
  multi-channel figures are skipped until Phase C.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import xarray as xr

from obs_monitor.config.figures import FigureSpec
from obs_monitor.stats.summary import FIELD_QC, QC_CLASSES, _class_masks

from obs_monitor.plotting.figures import build_figure
from obs_monitor.plotting.naming import stat_name

logger = logging.getLogger(__name__)

FIELD_LABELS = {"ombg": "O-F", "oman": "O-A", "obs": "Obs"}
STAT_LABELS = {"mean": "Mean", "rms": "RMS", "std": "Std Dev", "count": "Count"}


@dataclass
class PlotResult:
    written: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)     # (figure description, error)
    skipped: list[tuple[str, str]] = field(default_factory=list)    # (figure description, reason)


# ---------------------------------------------------------------------------
# Summary -> figure Datasets
# ---------------------------------------------------------------------------

def _select_channel(da: xr.DataArray, channel: int | None) -> xr.DataArray:
    if "channel" in da.dims:
        if channel is None:
            raise ValueError("summary has a channel dimension; pass channel=")
        return da.sel(channel=channel)
    return da


def time_series_dataset(stacked: xr.Dataset, field: str, stat: str, qc: str,
                        channel: int | None = None) -> xr.Dataset:
    """
    ``<field>_<stat>`` for one QC class, shaped for ``TimeSeriesFigure``:
    variable ``<qc>_<stat>`` with dims ``(analysisCycle, dim_0)`` and a
    ``statisticDomain`` coordinate.
    """
    var = f"{field}_{stat}"
    if var not in stacked:
        raise KeyError(f"summary has no '{var}'")
    da = _select_channel(stacked[var], channel).sel(qc_class=qc).transpose("cycle", "domain")
    return xr.Dataset(
        {stat_name(qc, stat): (("analysisCycle", "dim_0"), da.values.astype(float))},
        coords={"analysisCycle": stacked["cycle"].values,
                "statisticDomain": ("dim_0", stacked["domain"].values.astype(str))},
        attrs=dict(stacked.attrs),
    )


def gridded_dataset(stacked: xr.Dataset, field: str, stat: str, qc: str,
                    channel: int | None = None) -> xr.Dataset:
    """
    Window-total gridded field shaped for ``MapGriddedFigure``: variable
    ``<qc>_<stat>`` on ``(binsYDim, binsXDim)`` with 2-D ``latitude`` /
    ``longitude`` coordinates (bin centres).

    How the window mean is computed
    -------------------------------
    Each cycle's summary stores, per 2.5° box, a mean ``m_c`` and a count
    ``n_c``. Since mean x count = sum, the window mean is::

        mean = sum_c(m_c * n_c) / sum_c(n_c)

    i.e. the mean of every ob in the box over the whole window, each ob
    counted once. This is count-weighted: a cycle with 300 obs in a box
    counts 300 times as much as a cycle with 1. (The old stat-file maps took
    the unweighted mean of per-cycle means, which over-weights sparse cycles.)
    Example: cycles with (mean, count) = (1, 1), (3, 3), (-2, 1) give
    (1 + 9 - 2) / 5 = 1.6, not (1 + 3 - 2) / 3 = 0.67.

    Missing cycles (NaN in the stacked summary) and boxes with no obs in a
    cycle contribute nothing to either sum. Boxes with no obs in the whole
    window are NaN (blank on the map), never 0. ``stat="count"`` returns the
    total count ``sum_c(n_c)`` instead. ``n_cycles`` is the number of cycles
    with any data.
    """
    gqc = stacked.attrs.get("gridded_qc", "assimilated")
    if qc != gqc:
        raise ValueError(f"summaries hold gridded fields for qc '{gqc}' only, not '{qc}'")
    mean_var, count_var = f"{field}_gridded_mean", f"{field}_gridded_count"
    if mean_var not in stacked:
        raise KeyError(f"summary has no '{mean_var}'")
    m = _select_channel(stacked[mean_var], channel).transpose("cycle", "lat", "lon").values.astype(float)
    n = _select_channel(stacked[count_var], channel).transpose("cycle", "lat", "lon").values.astype(float)
    n = np.nan_to_num(n)                               # missing cycles are NaN
    total = np.nansum(np.where(n > 0, m * n, 0.0), axis=0)
    count = n.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        values = total / count if stat == "mean" else count
    values = np.where(count > 0, values, np.nan)

    lon2d, lat2d = np.meshgrid(stacked["lon"].values, stacked["lat"].values)
    n_cycles = int(np.any(n > 0, axis=(1, 2)).sum())
    return xr.Dataset(
        {stat_name(qc, stat): (("binsYDim", "binsXDim"), values)},
        coords={"latitude": (("binsYDim", "binsXDim"), lat2d),
                "longitude": (("binsYDim", "binsXDim"), lon2d),
                "n_cycles": n_cycles},
        attrs=dict(stacked.attrs),
    )


def count_series_dataset(stacked: xr.Dataset, field: str, qcs: Sequence[str],
                         channel: int | None = None) -> xr.Dataset:
    """
    ``<field>_count`` for several QC classes, shaped for ``CountSeriesFigure``:
    one variable per class on ``(analysisCycle, dim_0)`` with a
    ``statisticDomain`` coordinate. Missing cycles stay NaN (gaps).
    """
    var = f"{field}_count"
    if var not in stacked:
        raise KeyError(f"summary has no '{var}'")
    da = _select_channel(stacked[var], channel)
    return xr.Dataset(
        {qc: (("analysisCycle", "dim_0"), da.sel(qc_class=qc).transpose("cycle", "domain").values.astype(float))
         for qc in qcs},
        coords={"analysisCycle": stacked["cycle"].values,
                "statisticDomain": ("dim_0", stacked["domain"].values.astype(str))},
        attrs=dict(stacked.attrs),
    )


def latest_points_dataset(ds: xr.Dataset, field: str, cycle: datetime) -> xr.Dataset:
    """
    The newest cycle's observations, shaped for the latest-cycle maps:
    ``latitude``/``longitude`` on ``Location``, one boolean variable per QC
    class (same rules as the summaries, see :mod:`obs_monitor.stats.summary`),
    and ``<qc>_<field>`` with the field's value where the observation is in
    that class (NaN elsewhere). ``ds`` is :func:`obs_monitor.io.read_ioda`
    output; a single-channel file is squeezed.
    """
    if "channel" in ds.dims:
        if ds.sizes["channel"] != 1:
            raise ValueError("latest-cycle maps for multi-channel obs spaces are not implemented yet")
        ds = ds.isel(channel=0, drop=True)
    if field not in ds:
        raise KeyError(f"diag file has no '{field}'")
    values = ds[field].values.astype(float)
    qc_name = next((q for q in FIELD_QC[field] if q in ds), None)
    masks = _class_masks(values, ds[qc_name].values if qc_name else None)
    data = {}
    for i, qc in enumerate(QC_CLASSES):
        data[qc] = (("Location",), masks[i])
        data[f"{qc}_{field}"] = (("Location",), np.where(masks[i], values, np.nan))
    return xr.Dataset(data, coords={"latitude": ("Location", ds["latitude"].values),
                                    "longitude": ("Location", ds["longitude"].values)},
                      attrs={**ds.attrs, "cycle": f"{cycle:%Y%m%d%H}"})


# ---------------------------------------------------------------------------
# Specs -> PNGs
# ---------------------------------------------------------------------------

def _describe(spec: FigureSpec) -> str:
    return " ".join(p for p in (spec.type, spec.field, spec.qc or ",".join(spec.qcs), spec.stat) if p)


def _cycle_span(stacked: xr.Dataset) -> str:
    c = pd.to_datetime(stacked["cycle"].values)
    return f"{c[0]:%Y%m%d%H}-{c[-1]:%Y%m%d%H}"


def _time_series_figure_spec(spec: FigureSpec, stacked: xr.Dataset) -> tuple[dict, list[str]]:
    """Figure spec dict for TimeSeriesFigure, and the requested domains not in regions.yaml."""
    variable, units = stacked.attrs.get("variable", ""), stacked.attrs.get("units", "")
    known = [str(d) for d in stacked["domain"].values]
    domains = list(spec.domains) if spec.domains else known
    unknown = [d for d in domains if d not in known]
    if unknown:
        logger.warning("Domain(s) %s not in regions.yaml (%s); skipped.", unknown, known)
    title = (f"{{ob_type}} {{domain}} Time Series — {spec.qc.title()} {STAT_LABELS[spec.stat]} "
             f"{FIELD_LABELS[spec.field]}")
    y_label = "count" if spec.stat == "count" else f"{variable} ({units})" if units else variable
    return {"label": spec.field,
            "domains": [d for d in domains if d in known],
            "title": spec.options.get("title", title),
            "y_label": spec.options.get("y_label", y_label)}, unknown


def _map_figure_spec(spec: FigureSpec, ds: xr.Dataset, stacked: xr.Dataset) -> dict:
    variable, units = stacked.attrs.get("variable", ""), stacked.attrs.get("units", "")
    data = ds[stat_name(spec.qc, spec.stat)].values
    title = (f"{{ob_type}} {FIELD_LABELS[spec.field]} — {spec.qc.title()} {STAT_LABELS[spec.stat]}, "
             f"{int(ds['n_cycles'])} cycles {_cycle_span(stacked)}")
    out = {"label": spec.field,
           "title": spec.options.get("title", title),
           "colorbar_label": spec.options.get(
               "colorbar_label", "count" if spec.stat == "count" else f"{variable} ({units})" if units else variable),
           "cmap": spec.options.get("cmap", "coolwarm" if spec.stat == "mean" else "viridis"),
           "projection": spec.options.get("projection", "plcarr"),
           "domain": spec.options.get("map_domain", "global"),
           "vmin": spec.options.get("vmin"),
           "vmax": spec.options.get("vmax")}
    if spec.stat == "mean" and out["vmin"] is None and out["vmax"] is None and np.isfinite(data).any():
        lim = float(np.nanmax(np.abs(data)))
        out["vmin"], out["vmax"] = -lim, lim
    return out


def plot_obs_space(
    stacked: xr.Dataset | None,
    ob_type: str,
    specs: Sequence[FigureSpec],
    output_dir: str | Path,
    latest: tuple[datetime, xr.Dataset] | None = None,
) -> PlotResult:
    """
    Make every figure in ``specs`` for one obs space and variable.

    Parameters
    ----------
    stacked
        Output of :func:`obs_monitor.stats.stack_cycles` (``None`` = no data at all).
    ob_type
        Name used in file names and titles: the obs space's ``label``
        (``web_name`` if set).
    specs
        ``obs_space.figures`` or :func:`obs_monitor.config.load_default_figures`.
    output_dir
        Where the PNGs go.
    latest
        ``(cycle, read_ioda output)`` for the newest cycle in the window with a
        diag file, for the latest-cycle maps (``spec.latest``). ``None``: those
        figures are skipped.
    """
    result = PlotResult()
    if stacked is None:
        result.skipped += [(_describe(s), "no data in window") for s in specs]
        return result
    if "channel" in stacked.dims and stacked.sizes["channel"] == 1:
        # One channel (e.g. VIIRS AOD) is just one field: plot it like conventional data, same file names.
        stacked = stacked.isel(channel=0, drop=True)
    if "channel" in stacked.dims:
        # Multi-channel radiance figures (per channel, channel x cycle heatmap) come with Phase C.
        result.skipped += [(_describe(s), "per-channel figures not implemented yet") for s in specs]
        return result

    variable = stacked.attrs.get("variable", "")
    points: dict[str, xr.Dataset] = {}
    for spec in specs:
        desc = _describe(spec)
        if spec.latest and latest is None:
            result.skipped.append((desc, "no diag file in the window for the latest-cycle maps"))
            continue
        try:
            if spec.latest:
                if spec.field not in points:
                    points[spec.field] = latest_points_dataset(latest[1], spec.field, latest[0])
                ds = points[spec.field]
                stat = f"{spec.qc}_{spec.field}" if spec.type == "scatter_map" else spec.type
                fig_spec = {"field": spec.field, "qcs": list(spec.qcs), **spec.options}
                if spec.type == "scatter_map":
                    fig_spec.setdefault("title", f"{{ob_type}} {spec.qc.title()} {FIELD_LABELS[spec.field]}, "
                                                 "{cycle} ({n:,} obs)")
                    units = stacked.attrs.get("units", "")
                    fig_spec.setdefault("colorbar_label", f"{FIELD_LABELS[spec.field]} ({units})" if units
                                        else FIELD_LABELS[spec.field])
                else:
                    fig_spec.setdefault("title", f"{{ob_type}} coverage by QC ({FIELD_LABELS[spec.field]}), {{cycle}}")
            elif spec.type == "count_series":
                ds = count_series_dataset(stacked, spec.field, spec.qcs)
                stat = "count"
                fig_spec = {"field": spec.field, "qcs": list(spec.qcs), "domains": list(spec.domains or ()) or None,
                            **spec.options}
                fig_spec["title"] = spec.options.get(
                    "title", f"{{ob_type}} {{domain}} — {FIELD_LABELS[spec.field]} observation count")
            elif spec.type == "time_series":
                ds = time_series_dataset(stacked, spec.field, spec.stat, spec.qc)
                fig_spec, unknown = _time_series_figure_spec(spec, stacked)
                result.skipped += [(f"{desc} {d}", "domain not in regions.yaml") for d in unknown]
            else:
                ds = gridded_dataset(stacked, spec.field, spec.stat, spec.qc)
                fig_spec = _map_figure_spec(spec, ds, stacked)
        except KeyError as exc:
            # e.g. oman figures for a file with no oman group
            result.skipped.append((desc, str(exc)))
            continue
        except ValueError as exc:
            result.skipped.append((desc, str(exc)))
            continue
        if spec.type in ("time_series", "map_gridded"):
            stat = stat_name(spec.qc, spec.stat)
        try:
            fig = build_figure(spec.type, ds, fig_spec, ob_type, variable, stat, Path(output_dir))
            result.written += fig.save()
            result.failed += [(f"{desc} -> {path.name}", err) for path, err in fig.failed]
        except Exception as exc:  # noqa: BLE001 - one bad figure must not stop the rest
            logger.exception("Figure failed: %s %s", ob_type, desc)
            result.failed.append((desc, f"{type(exc).__name__}: {exc}"))
    return result
