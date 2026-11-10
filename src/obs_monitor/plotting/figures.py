"""
obs_monitor.plotting.figures
=============================

Object-oriented figure classes that wrap EMCPy's plotting primitives for the
two plot types used by obs-monitor:

``TimeSeriesFigure``
    Multi-line plot of a statistic over analysis cycles, one line per
    requested domain.  Backed by ``emcpy.plots.plots.LinePlot`` and
    ``emcpy.plots.create_plots.CreatePlot / CreateFigure``.

``MapGriddedFigure``
    Global (or regional) map of a cycle-averaged gridded field.  Backed by
    ``emcpy.plots.map_plots.MapGridded`` and the same Create* wrappers.

Both classes share a common interface::

    fig = TimeSeriesFigure(ds, spec, ob_type, variable, stat)
    fig.save()          # writes a PNG; returns the Path

Neither class mutates the Dataset it receives.  All domain filtering,
title formatting, and output path construction happen here;
:mod:`~obs_monitor.plotting.summary_figures` passes fully-prepared Datasets
and receives back output Paths.

EMCPy is a hard runtime requirement.  If it cannot be imported, a clear
``ImportError`` is raised at module load time rather than at first use.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend; safe for batch/HPC use
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

# Hard EMCPy requirement — fail loudly at import time if missing.
try:
    from emcpy.plots.plots import LinePlot, HorizontalLine
    from emcpy.plots.create_plots import CreatePlot, CreateFigure
    from emcpy.plots.map_plots import MapGridded, MapScatter
except ImportError as _emcpy_err:
    raise ImportError(
        "EMCPy is required for obs_monitor.plotting.figures but could not be "
        "imported.  Install it with: pip install emcpy\n"
        f"Original error: {_emcpy_err}"
    ) from _emcpy_err

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour cycle for multi-domain time-series lines
# ---------------------------------------------------------------------------
# Chosen to be distinguishable on both screen and printed plots and to work
# for the most common forms of colour-vision deficiency.
_DOMAIN_COLORS: dict[str, str] = {
    "Global": "#000000",  # black   — always draw first / most prominent
    "NH": "#0072B2",  # blue
    "SH": "#E69F00",  # orange
    "CONUS": "#009E73",  # teal
    "Europe": "#CC79A7",  # mauve
    "Asia": "#D55E00",  # vermilion
    "Africa": "#56B4E9",  # sky blue
}
_FALLBACK_COLORS = plt.rcParams["axes.prop_cycle"].by_key()["color"]


def _domain_color(domain: str, idx: int) -> str:
    """Return a consistent colour for *domain*, falling back to the
    matplotlib prop-cycle when the domain name is not in the preset map."""
    return _DOMAIN_COLORS.get(domain, _FALLBACK_COLORS[idx % len(_FALLBACK_COLORS)])


# Filename helpers live in naming.py (the website contract); re-exported here
# so existing imports keep working.
from obs_monitor.plotting.naming import build_map_filename, build_timeseries_filename  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class FigureBase(ABC):
    """
    Common interface for all obs-monitor figure types.

    Subclasses implement :meth:`_render`, which returns a list of
    ``(matplotlib.figure.Figure, Path)`` pairs.  :meth:`save` calls
    ``_render`` and writes each figure to disk, returning the list of
    paths actually written.
    """

    def __init__(
        self,
        ds: xr.Dataset,
        spec: dict,
        ob_type: str,
        variable: str,
        stat: str,
        output_dir: Path,
    ) -> None:
        self.ds = ds
        self.spec = spec
        self.ob_type = ob_type
        self.variable = variable
        self.stat = stat
        self.output_dir = Path(output_dir)
        self.failed: list[tuple[Path, str]] = []   # (path, error) for figures that could not be saved

    @abstractmethod
    def _render(self) -> list[tuple["plt.Figure", Path]]:
        """
        Build and return a list of (matplotlib Figure, output Path) pairs.
        No I/O is performed here — that is left to :meth:`save`.
        """

    def save(self) -> list[Path]:
        """
        Render all figures for this spec entry and write them to
        ``output_dir`` as PNGs.

        Returns
        -------
        list[Path]
            Paths of files that were successfully written.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        pairs = self._render()
        for mpl_fig, out_path in pairs:
            try:
                mpl_fig.savefig(out_path, dpi=150, bbox_inches="tight")
                logger.info("Saved figure: %s", out_path)
                written.append(out_path)
            except Exception as exc:
                logger.error("Failed to save figure '%s': %s", out_path, exc)
                self.failed.append((out_path, f"{type(exc).__name__}: {exc}"))
            finally:
                plt.close(mpl_fig)

        return written


# ---------------------------------------------------------------------------
# Time-series figure
# ---------------------------------------------------------------------------

class TimeSeriesFigure(FigureBase):
    """
    Multi-domain time-series line plot of a single statistic over cycles.

    One PNG is produced per domain so that file names are unambiguous in
    COM and individual domain plots can be linked independently on web pages.

    The ``analysisCycle`` coordinate (``datetime64``) from the Dataset is
    used as the x-axis.  The ``statisticDomain`` coordinate (if present) is
    used for domain label lookup; otherwise integer indices are used.

    Parameters
    ----------
    ds:
        Dataset from :func:`~obs_monitor.plotting.summary_figures.time_series_dataset`.
        Expected shape of each variable: ``(analysisCycle, dim_0)``.
    spec:
        Figure spec dict from the job config.  Recognised keys:

        * ``title`` (str) — may contain ``{ob_type}``, ``{variable}``,
          ``{stat}``, ``{domain}`` placeholders.
        * ``y_label`` (str) — y-axis label.
        * ``domains`` (list[str] | None) — domain names to plot.
          ``None`` or absent → all domains.
    ob_type, variable, stat:
        Used for title formatting and filename construction.
    output_dir:
        Directory where PNGs are written.
    """

    def _resolve_domains(self) -> list[tuple[int, str]]:
        """
        Return ``[(dim_0_index, domain_label), ...]`` for the domains to plot.
        """
        requested: list[str] | None = self.spec.get("domains")

        if "statisticDomain" in self.ds.coords:
            all_labels: list[str] = list(
                self.ds.coords["statisticDomain"].values.astype(str)
            )
            if requested is None:
                return list(enumerate(all_labels))

            result: list[tuple[int, str]] = []
            for name in requested:
                if name in all_labels:
                    result.append((all_labels.index(name), name))
                else:
                    logger.warning(
                        "Requested domain '%s' not found in file "
                        "(available: %s); skipping.",
                        name,
                        all_labels,
                    )
            return result

        # No coordinate labels — fall back to indices
        n_domains = self.ds[self.stat].shape[1] if self.ds[self.stat].ndim >= 2 else 1
        if requested is not None:
            logger.warning(
                "domains filter %s specified but 'statisticDomain' coordinate "
                "is absent; plotting all %d domain(s) by index.",
                requested,
                n_domains,
            )
        return [(i, f"domain_{i}") for i in range(n_domains)]

    def _render(self) -> list[tuple["plt.Figure", Path]]:
        if self.stat not in self.ds.data_vars:
            logger.error(
                "Statistic '%s' not found in Dataset (available: %s); "
                "skipping TimeSeriesFigure.",
                self.stat,
                list(self.ds.data_vars),
            )
            return []

        da = self.ds[self.stat]  # shape (analysisCycle, dim_0)
        cycles = self.ds.coords["analysisCycle"].values  # datetime64 array

        # Convert datetime64 → timezone-aware UTC datetimes for matplotlib
        from datetime import timezone as _tz
        x_times = [
            datetime.fromtimestamp(int(t) / 1e9, tz=_tz.utc).replace(tzinfo=None)
            for t in cycles.astype("int64")
        ]

        domains = self._resolve_domains()
        title_template = self.spec.get(
            "title", "{ob_type} {stat} — {domain}"
        )
        y_label = self.spec.get("y_label", self.stat)

        results: list[tuple["plt.Figure", Path]] = []

        for dom_idx, dom_label in domains:
            # Extract the (analysisCycle,) slice for this domain
            if da.ndim == 2:
                y_vals = da.values[:, dom_idx].astype(float)
            else:
                y_vals = da.values.astype(float)

            title = title_template.format(
                ob_type=self.ob_type,
                variable=self.variable,
                stat=self.stat,
                domain=dom_label,
            )

            # ---- EMCPy LinePlot ----
            lp = LinePlot(x_times, y_vals)
            lp.label = dom_label
            lp.color = _domain_color(dom_label, dom_idx)
            lp.linewidth = 1.5
            lp.marker = "o"      # without a marker, a cycle between two gaps would not show
            lp.markersize = 4

            # Zero reference line — uses EMCPy HorizontalLine so it renders
            # as a proper plot layer rather than a post-hoc matplotlib patch.
            zero_line = HorizontalLine(0)
            zero_line.color = "black"
            zero_line.linewidth = 0.8
            zero_line.linestyle = "--"

            plot1 = CreatePlot()
            plot1.plot_layers = [lp, zero_line]
            plot1.add_title(label=title, loc="center", fontsize=12)
            plot1.add_xlabel(xlabel="Analysis Cycle (UTC)", fontsize=10)
            plot1.add_ylabel(ylabel=y_label, fontsize=10)
            plot1.add_legend(loc="best", fontsize=9)
            # Grid via EMCPy's add_grid — routes to ax.gridlines() on map axes
            # and ax.grid() on regular axes (see CreateFigure._plot_grid).
            plot1.add_grid(linestyle=":", linewidth=0.6, color="gray", alpha=0.7)

            fig_obj = CreateFigure(figsize=(10, 4))
            fig_obj.plot_list = [plot1]
            fig_obj.create_figure()

            # Rotate x-tick labels for readability; EMCPy exposes the
            # underlying axes via fig_obj.fig.
            mpl_fig: plt.Figure = fig_obj.fig
            for ax in mpl_fig.axes:
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y%m%d\n%Hz"))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
                # Draw grid lines behind data
                ax.set_axisbelow(True)

            out_name = build_timeseries_filename(
                self.ob_type, self.variable, self.stat, dom_label,
                label=self.spec.get("label"),
            )
            out_path = self.output_dir / out_name
            results.append((mpl_fig, out_path))

        return results


# ---------------------------------------------------------------------------
# Gridded map figure
# ---------------------------------------------------------------------------

class MapGriddedFigure(FigureBase):
    """
    Global (or regional) gridded map of a cycle-averaged field.

    One PNG is produced per figure spec entry (one map per statistic).

    Parameters
    ----------
    ds:
        Dataset from :func:`~obs_monitor.plotting.summary_figures.gridded_dataset`.
        Each variable should have shape ``(binsYDim, binsXDim)`` with
        ``latitude`` and ``longitude`` attached as coordinates.
    spec:
        Figure spec dict from the job config.  Recognised keys:

        * ``title`` (str) — may contain ``{ob_type}``, ``{variable}``,
          ``{stat}`` placeholders.
        * ``colorbar_label`` (str) — label for the colorbar.
        * ``projection`` (str) — EMCPy projection name, e.g. ``"plcarr"``.
          Defaults to ``"plcarr"``.
        * ``domain`` (str) — EMCPy domain name, e.g. ``"global"``.
          Defaults to ``"global"``.
        * ``cmap`` (str | None) — matplotlib colormap name.
          Defaults to ``"coolwarm"``.
        * ``vmin`` (float | None) — lower bound for the colorbar.
          When omitted the full data range is used.
        * ``vmax`` (float | None) — upper bound for the colorbar.
          When omitted the full data range is used.
    ob_type, variable, stat:
        Used for title formatting and filename construction.
    output_dir:
        Directory where PNGs are written.
    """

    def _render(self) -> list[tuple["plt.Figure", Path]]:
        if self.stat not in self.ds.data_vars:
            logger.error(
                "Statistic '%s' not found in Dataset (available: %s); "
                "skipping MapGriddedFigure.",
                self.stat,
                list(self.ds.data_vars),
            )
            return []

        if "latitude" not in self.ds.coords or "longitude" not in self.ds.coords:
            logger.error(
                "Dataset is missing 'latitude' or 'longitude' coordinates. "
                "Expected gridded_dataset() output.  Skipping MapGriddedFigure."
            )
            return []

        lat = self.ds.coords["latitude"].values   # (72, 144)
        lon = self.ds.coords["longitude"].values  # (72, 144)
        data = self.ds[self.stat].values.astype(float)  # (72, 144)

        projection = self.spec.get("projection", "plcarr")
        domain = self.spec.get("domain", "global")
        cmap = self.spec.get("cmap") or "coolwarm"
        cb_label = self.spec.get("colorbar_label", f"{self.variable} ({self.stat})")
        vmin = self.spec.get("vmin")   # None → EMCPy uses full data range
        vmax = self.spec.get("vmax")
        title_template = self.spec.get(
            "title", "{ob_type} {variable} {stat} — Cycle Mean"
        )
        title = title_template.format(
            ob_type=self.ob_type,
            variable=self.variable,
            stat=self.stat,
        )

        # ---- EMCPy MapGridded ----
        # vmin/vmax are first-class attributes on MapGridded; _apply_norm_from_layer
        # in CreateFigure reads them and builds a Normalize before calling pcolormesh.
        gridded = MapGridded(lat, lon, data)
        gridded.cmap = cmap
        gridded.vmin = vmin
        gridded.vmax = vmax

        plot1 = CreatePlot()
        plot1.plot_layers = [gridded]
        plot1.projection = projection
        plot1.domain = domain
        plot1.add_map_features(["coastline", "borders"])
        plot1.add_xlabel(xlabel="Longitude", fontsize=10)
        plot1.add_ylabel(ylabel="Latitude", fontsize=10)
        plot1.add_title(label=title, loc="center", fontsize=12)
        plot1.add_grid()
        plot1.add_colorbar(label=cb_label, fontsize=10, extend="both")

        fig_obj = CreateFigure(figsize=(12, 6))
        fig_obj.plot_list = [plot1]
        fig_obj.create_figure()

        mpl_fig: plt.Figure = fig_obj.fig

        out_name = build_map_filename(
            self.ob_type, self.variable, self.stat,
            label=self.spec.get("label"),
        )
        out_path = self.output_dir / out_name

        return [(mpl_fig, out_path)]


# ---------------------------------------------------------------------------
# QC-class figures: count series, coverage map, scatter map
# ---------------------------------------------------------------------------

#: One colour per QC class, colour-vision-deficiency safe (same palette as the domains).
QC_COLORS: dict[str, str] = {
    "all": "#000000",          # black
    "assimilated": "#0072B2",  # blue
    "monitored": "#E69F00",    # orange
    "rejected": "#D55E00",     # vermilion
}


def _cycle_times(ds: xr.Dataset) -> list[datetime]:
    return [datetime.fromtimestamp(int(t) / 1e9, tz=timezone.utc).replace(tzinfo=None)
            for t in ds.coords["analysisCycle"].values.astype("int64")]


def _map_figure(layers: list, spec: dict, title: str, colorbar_label: str | None = None) -> "plt.Figure":
    """One global (or regional) map with ``layers``, coastlines, grid and optional colorbar."""
    plot1 = CreatePlot()
    plot1.plot_layers = layers
    plot1.projection = spec.get("projection", "plcarr")
    plot1.domain = spec.get("map_domain", spec.get("domain", "global"))
    plot1.add_map_features(["coastline", "borders"])
    plot1.add_xlabel(xlabel="Longitude", fontsize=10)
    plot1.add_ylabel(ylabel="Latitude", fontsize=10)
    plot1.add_title(label=title, loc="center", fontsize=12)
    plot1.add_grid()
    if colorbar_label is not None:
        plot1.add_colorbar(label=colorbar_label, fontsize=10, extend="both")
    else:
        plot1.add_legend(loc="lower left", fontsize=9, markerscale=3)
    fig_obj = CreateFigure(figsize=(12, 6))
    fig_obj.plot_list = [plot1]
    fig_obj.create_figure()
    return fig_obj.fig


def _apply_layer_colors(fig: "plt.Figure", colors: dict[str, str], legend_order: list[str] | None = None) -> None:
    """
    Colour solid-colour MapScatter layers by label, then redraw the legend.

    EMCPy's map scatter renderer drops ``color`` for layers without data
    values, so every layer gets the next default colour. Until that's fixed
    upstream, set the colours on the drawn points so QC classes keep the same
    colour in every figure.
    """
    for ax in fig.axes:
        recolored = False
        for coll in ax.collections:
            color = colors.get(coll.get_label())
            if color is not None:
                coll.set_facecolor(color)
                coll.set_edgecolor(color)
                recolored = True
        if recolored and ax.get_legend() is not None:
            handles = {c.get_label(): c for c in ax.collections if c.get_label() in colors}
            order = [lab for lab in (legend_order or handles) if lab in handles]
            ax.legend([handles[lab] for lab in order], order, loc="lower left", fontsize=9, markerscale=3)


class CountSeriesFigure(FigureBase):
    """
    Number of observations per cycle, one line per QC class, one PNG per domain.

    ``ds`` (from :func:`~obs_monitor.plotting.summary_figures.count_series_dataset`)
    has one variable per QC class on ``(analysisCycle, dim_0)`` with a
    ``statisticDomain`` coordinate. Spec keys: ``qcs``, ``domains``, ``field``,
    ``title``, ``y_label``, ``log_scale``.
    """

    def _render(self) -> list[tuple["plt.Figure", Path]]:
        x_times = _cycle_times(self.ds)
        all_domains = list(self.ds.coords["statisticDomain"].values.astype(str))
        results = []
        for domain in self.spec.get("domains") or all_domains:
            if domain not in all_domains:
                logger.warning("Domain '%s' not in summaries (%s); skipped.", domain, all_domains)
                continue
            idx = all_domains.index(domain)
            layers = []
            for qc in self.spec["qcs"]:
                lp = LinePlot(x_times, self.ds[qc].values[:, idx].astype(float))
                lp.label = qc
                lp.color = QC_COLORS.get(qc, "gray")
                lp.linewidth = 1.5
                lp.marker = "o"
                lp.markersize = 4
                layers.append(lp)
            title = self.spec.get("title", "{ob_type} {domain} — observation count").format(
                ob_type=self.ob_type, variable=self.variable, stat=self.stat, domain=domain)

            plot1 = CreatePlot()
            plot1.plot_layers = layers
            plot1.add_title(label=title, loc="center", fontsize=12)
            plot1.add_xlabel(xlabel="Analysis Cycle (UTC)", fontsize=10)
            plot1.add_ylabel(ylabel=self.spec.get("y_label", "count"), fontsize=10)
            plot1.add_legend(loc="best", fontsize=9)
            plot1.add_grid(linestyle=":", linewidth=0.6, color="gray", alpha=0.7)
            fig_obj = CreateFigure(figsize=(10, 4))
            fig_obj.plot_list = [plot1]
            fig_obj.create_figure()
            mpl_fig = fig_obj.fig
            for ax in mpl_fig.axes:
                if self.spec.get("log_scale"):
                    ax.set_yscale("log")
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y%m%d\n%Hz"))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
            name = build_timeseries_filename(self.ob_type, self.variable, "count", domain,
                                             label=self.spec.get("field"))
            results.append((mpl_fig, self.output_dir / name))
        return results


class CoverageMapFigure(FigureBase):
    """
    Where the observations of the newest cycle are, coloured by QC class
    (by default only the assimilated ones). The first class in ``qcs`` is
    drawn on top and listed first in the legend.

    ``ds`` (from :func:`~obs_monitor.plotting.summary_figures.latest_points_dataset`)
    has ``latitude``/``longitude`` on ``Location`` and one boolean variable per
    QC class; attrs ``cycle``. Spec keys: ``qcs``, ``title``, ``marker_size``,
    ``projection``, ``map_domain``.
    """

    def _render(self) -> list[tuple["plt.Figure", Path]]:
        lat, lon = self.ds["latitude"].values, self.ds["longitude"].values
        layers, counts = [], []
        # Drawn last-listed first, so the first class listed ends up on top: with
        # [assimilated, rejected], rejected obs at the same station don't hide the assimilated ones.
        for qc in reversed(self.spec["qcs"]):
            mask = self.ds[qc].values.astype(bool)
            counts.append(f"{qc} {int(mask.sum()):,}")
            if not mask.any():
                continue
            layer = MapScatter(lat[mask], lon[mask])
            layer.color = QC_COLORS.get(qc, "gray")
            layer.markersize = self.spec.get("marker_size", 3)
            layer.label = f"{qc} ({int(mask.sum()):,})"
            layers.append(layer)
        if not layers:
            logger.warning("%s %s: no observations in any of %s; coverage map skipped.",
                           self.ob_type, self.variable, list(self.spec["qcs"]))
            return []
        title = self.spec.get("title", "{ob_type} {variable} coverage {cycle}").format(
            ob_type=self.ob_type, variable=self.variable, stat=self.stat, cycle=self.ds.attrs.get("cycle", ""))
        fig = _map_figure(layers, self.spec, title)
        _apply_layer_colors(fig, {layer.label: layer.color for layer in layers}, legend_order=[
            layer.label for layer in reversed(layers)])
        return [(fig, self.output_dir / build_map_filename(self.ob_type, self.variable, "coverage"))]


class ScatterMapFigure(FigureBase):
    """
    One value per observation of the newest cycle (e.g. O-F of assimilated obs), on a map.

    ``ds`` (from :func:`~obs_monitor.plotting.summary_figures.latest_points_dataset`)
    has ``latitude``/``longitude`` on ``Location`` and the variable ``stat``
    (``<qc>_<field>``), NaN where the observation isn't in the QC class.
    Colour limits: ``vmin``/``vmax`` if given; otherwise, for O-F and O-A,
    symmetric about zero at the 98th percentile of |value| so a few outliers
    don't wash out the map (the colorbar arrows mark values beyond).
    """

    def _render(self) -> list[tuple["plt.Figure", Path]]:
        values = self.ds[self.stat].values.astype(float)
        keep = np.isfinite(values)
        if not keep.any():
            logger.warning("%s %s: no %s values; scatter map skipped.", self.ob_type, self.variable, self.stat)
            return []
        field_name = self.spec.get("field", "")
        layer = MapScatter(self.ds["latitude"].values[keep], self.ds["longitude"].values[keep], values[keep])
        layer.markersize = self.spec.get("marker_size", 4)
        diverging = field_name in ("ombg", "oman")
        layer.cmap = self.spec.get("cmap") or ("coolwarm" if diverging else "viridis")
        vmin, vmax = self.spec.get("vmin"), self.spec.get("vmax")
        if vmin is None and vmax is None and diverging:
            lim = float(np.nanpercentile(np.abs(values[keep]), 98)) or float(np.nanmax(np.abs(values[keep])))
            vmin, vmax = -lim, lim
        layer.vmin, layer.vmax = vmin, vmax
        title = self.spec.get("title", "{ob_type} {variable} {stat} {cycle} ({n:,} obs)").format(
            ob_type=self.ob_type, variable=self.variable, stat=self.stat,
            cycle=self.ds.attrs.get("cycle", ""), n=int(keep.sum()))
        fig = _map_figure([layer], self.spec, title, colorbar_label=self.spec.get("colorbar_label", self.variable))
        qc, _, fld = self.stat.partition("_")
        name = build_map_filename(self.ob_type, self.variable, f"{qc}_scatter", label=fld)
        return [(fig, self.output_dir / name)]


# ---------------------------------------------------------------------------
# Registry — maps config ``type`` strings to classes
# ---------------------------------------------------------------------------

#: Maps the ``type`` field in a figure spec to the corresponding class.
#: Extend this dict to register new figure types without changing summary_figures.py.
FIGURE_REGISTRY: dict[str, type[FigureBase]] = {
    "time_series": TimeSeriesFigure,
    "map_gridded": MapGriddedFigure,
    "count_series": CountSeriesFigure,
    "coverage_map": CoverageMapFigure,
    "scatter_map": ScatterMapFigure,
}


def build_figure(
    figure_type: str,
    ds: xr.Dataset,
    spec: dict,
    ob_type: str,
    variable: str,
    stat: str,
    output_dir: Path,
) -> FigureBase:
    """
    Factory function — look up *figure_type* in :data:`FIGURE_REGISTRY` and
    return an instantiated figure object.

    Parameters
    ----------
    figure_type:
        String key from the job config, e.g. ``"time_series"`` or
        ``"map_gridded"``.
    ds:
        Prepared Dataset (from ``summary_figures.time_series_dataset`` or
        ``summary_figures.gridded_dataset``).
    spec:
        Full figure spec dict from the job config.
    ob_type, variable, stat:
        Metadata forwarded to the figure class.
    output_dir:
        Directory where PNGs will be written.

    Returns
    -------
    FigureBase
        An instance ready for ``.save()``.

    Raises
    ------
    ValueError
        If *figure_type* is not in the registry.
    """
    if figure_type not in FIGURE_REGISTRY:
        raise ValueError(
            f"Unknown figure type '{figure_type}'. "
            f"Registered types: {sorted(FIGURE_REGISTRY)}"
        )
    cls = FIGURE_REGISTRY[figure_type]
    return cls(ds, spec, ob_type, variable, stat, output_dir)
