"""
obs_monitor.plotting
====================

Figures for obs-monitor, drawn with EMCPy.

Entry point: :func:`plot_obs_space`, which turns the stacked summaries for one
obs space (:func:`obs_monitor.stats.stack_cycles`) into PNGs::

    from obs_monitor.plotting import plot_obs_space

    result = plot_obs_space(stacked, "prepbufr_adpsfc", specs, output_dir)
    result.written, result.failed, result.skipped

Module layout
-------------
``summary_figures``
    Summaries -> figure Datasets -> PNGs.
    Key callables: :func:`~summary_figures.plot_obs_space`,
    :func:`~summary_figures.time_series_dataset`,
    :func:`~summary_figures.gridded_dataset`.

``figures``
    EMCPy-backed figure classes behind a common ``FigureBase`` interface.
    Key callable: :func:`~figures.build_figure`.
    Registry: :data:`~figures.FIGURE_REGISTRY`.

``naming``
    Figure file names (the website contract, pinned by tests).

Dependencies
------------
* ``numpy``, ``pandas``, ``xarray``
* ``matplotlib`` — figure backend (non-interactive ``Agg``)
* ``emcpy`` — NOAA/EMC plotting wrappers (hard requirement)
"""

from obs_monitor.plotting.figures import (
    FigureBase,
    TimeSeriesFigure,
    MapGriddedFigure,
    build_figure,
    FIGURE_REGISTRY,
)
from obs_monitor.plotting.naming import build_map_filename, build_timeseries_filename
from obs_monitor.plotting.summary_figures import PlotResult, plot_obs_space

__all__ = [
    # figures
    "FigureBase",
    "TimeSeriesFigure",
    "MapGriddedFigure",
    "build_figure",
    "FIGURE_REGISTRY",
    # naming
    "build_map_filename",
    "build_timeseries_filename",
    # summary figures
    "PlotResult",
    "plot_obs_space",
]
