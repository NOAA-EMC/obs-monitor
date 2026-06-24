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
title formatting, and output path construction happen here; the dispatcher
passes fully-prepared Datasets and receives back output Paths.

EMCPy is a hard runtime requirement.  If it cannot be imported, a clear
``ImportError`` is raised at module load time rather than at first use.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; safe for operational/HPC use
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Hard EMCPy requirement — fail loudly at import time if missing.
try:
    from emcpy.plots.plots import LinePlot, HorizontalLine
    from emcpy.plots.create_plots import CreatePlot, CreateFigure
    from emcpy.plots.map_plots import MapGridded
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


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _safe_stem(text: str) -> str:
    """Replace characters that are unsafe in filenames with underscores."""
    return re.sub(r"[^\w\-]", "_", text)


def build_timeseries_filename(ob_type: str, variable: str, stat: str, domain: str, label: str | None = None) -> str:
    """
    Construct the output PNG filename for a time-series plot.

    Convention: ``{ob_type}_{variable}_{stat}_{label}_{domain}_timeseries.png``
    """
    parts = [ob_type, variable, stat]
    if label:
        parts.append(label)
    parts += [domain, "timeseries"]
    return "_".join(_safe_stem(p) for p in parts) + ".png"


def build_map_filename(ob_type: str, variable: str, stat: str, label: str | None = None) -> str:
    """
    Construct the output PNG filename for a gridded map plot.

    Convention: ``{ob_type}_{variable}_{stat_{label}_map.png``
    """
    parts = [ob_type, variable, stat]
    if label:
        parts.append(label)
    parts.append("map")
    return "_".join(_safe_stem(p) for p in parts) + ".png"


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
        Dataset from :func:`~obs_monitor.plotting.transforms.prepare_time_series`.
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
        Dataset from :func:`~obs_monitor.plotting.transforms.prepare_gridded`.
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
                "Was prepare_gridded() called?  Skipping MapGriddedFigure."
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
# Registry — maps config ``type`` strings to classes
# ---------------------------------------------------------------------------

#: Maps the ``type`` field in a figure spec to the corresponding class.
#: Extend this dict to register new figure types without changing dispatcher.py.
FIGURE_REGISTRY: dict[str, type[FigureBase]] = {
    "time_series": TimeSeriesFigure,
    "map_gridded": MapGriddedFigure,
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
        Prepared Dataset (output of the appropriate ``transforms.prepare_*``
        function).
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
