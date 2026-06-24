"""
obs_monitor.plotting
====================

Internal plotting subpackage for obs-monitor.  Replaces the EVA subprocess
call with a lightweight, EMCPy-backed pipeline that is fully owned by
NOAA/EMC.

Public API
----------
The intended entry point for the driver is :func:`dispatch_plots`.  Everything
else is importable for testing or direct scripting, but normal operational use
only needs the single top-level call::

    from obs_monitor.plotting import dispatch_plots

    result = dispatch_plots(
        ob_type=cfg.ob_type,
        runtime_dir=window_dir,
        plot_config=ob_plot_config,
        output_dir=window_dir / "plots",
    )

Module layout
-------------
``reader``
    Opens staged NetCDF files and stacks them along ``analysisCycle``.
    Key callables: :func:`~reader.read_group`, :func:`~reader.read_coords`,
    :func:`~reader.read_dim_labels`.

``transforms``
    Pure reductions on xarray Datasets.
    Key callables: :func:`~transforms.prepare_time_series`,
    :func:`~transforms.prepare_gridded`, and the lower-level
    :func:`~transforms.cycle_mean`, :func:`~transforms.squeeze_gridded`,
    :func:`~transforms.attach_coords`.

``figures``
    EMCPy-backed figure classes behind a common ``FigureBase`` interface.
    Key callables: :func:`~figures.build_figure`.
    Registry: :data:`~figures.FIGURE_REGISTRY`.

``dispatcher``
    Orchestrates the read → transform → render pipeline for one ob-type.
    Key callable: :func:`~dispatcher.dispatch_plots`.

Dependencies
------------
* ``netCDF4`` — NetCDF I/O
* ``numpy`` — array operations
* ``xarray`` — labelled Dataset/DataArray layer
* ``matplotlib`` — figure backend (non-interactive ``Agg``)
* ``emcpy`` — NOAA/EMC plotting wrappers (hard requirement)
"""

# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------
from .reader import (
    read_group,
    read_coords,
    read_dim_labels,
)

# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------
from .transforms import (
    cycle_mean,
    squeeze_gridded,
    attach_coords,
    prepare_time_series,
    prepare_gridded,
)

# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
from .figures import (
    FigureBase,
    TimeSeriesFigure,
    MapGriddedFigure,
    build_figure,
    FIGURE_REGISTRY,
)

# ---------------------------------------------------------------------------
# Dispatcher — primary driver entry point
# ---------------------------------------------------------------------------
from .dispatcher import dispatch_plots

# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------
__all__ = [
    # reader
    "read_group",
    "read_coords",
    "read_dim_labels",
    # transforms
    "cycle_mean",
    "squeeze_gridded",
    "attach_coords",
    "prepare_time_series",
    "prepare_gridded",
    # figures
    "FigureBase",
    "TimeSeriesFigure",
    "MapGriddedFigure",
    "build_figure",
    "FIGURE_REGISTRY",
    # dispatcher
    "dispatch_plots",
]
