"""
obs_monitor.plotting.dispatcher
================================

Ties the plotting sub-package together.  For each ob-type entry in the job
config the dispatcher:

1. Loads the plot config for the ob_type by:
   a. Reading ``monitor_types.yaml`` (pointed to by ``PLOT_CONFIG_YAML``) to
      find the monitor-type file for this ob_type.
   b. Loading that file and extracting the ob_type's config block.
2. Discovers and sorts the staged NetCDF files in the runtime directory.
3. Reads dimension labels (``statisticDomain``) once, shared across all reads.
4. For each figure spec in the config:
   a. Reads the appropriate group via the ``group_path`` key in the spec,
      using :func:`~obs_monitor.plotting.reader.read_group`.
   b. Applies the correct transform pipeline
      (:func:`~obs_monitor.plotting.transforms.prepare_time_series` or
      :func:`~obs_monitor.plotting.transforms.prepare_gridded`).
   c. Instantiates the correct figure class via
      :func:`~obs_monitor.plotting.figures.build_figure` and calls
      ``.save()``.
5. Returns a summary dict the driver can log or inspect.

Config layout (rooted at PLOT_CONFIG_YAML)
------------------------------------------
``PLOT_CONFIG_YAML`` points to ``monitor_types.yaml``:

.. code-block:: yaml

    ob_type_index:
      prepbufr_adpsfc:
        monitor_type: conventional
        path: config/monitor_types/conventional.yaml

Each monitor-type file contains an ``ob_types`` block:

.. code-block:: yaml

    ob_types:
      prepbufr_adpsfc:
        variable: stationPressure
        unit: Pa
        nc_groups:
          coords: griddedBins
        figures:
          - type: time_series
            group_path: byDomains/ombg/stationPressure
            stat: assimilated_mean
            title: "prepbufr_adpsfc Time Series — Assimilated Mean O-F"
            y_label: "stationPressure (Pa)"
            domains: [Global, NH, SH, CONUS]
          - type: map_gridded
            group_path: griddedBins/ombg/stationPressure
            stat: assimilated_mean
            title: "prepbufr_adpsfc O-F — Assimilated Mean Cycle Avg"
            colorbar_label: "stationPressure (Pa)"
            projection: plcarr
            domain: global
            cmap: coolwarm

Typical call from ``driver.py``
--------------------------------
::

    from obs_monitor.plotting.dispatcher import dispatch_plots

    results = dispatch_plots(
        ob_type=cfg.ob_type,
        runtime_dir=window_dir,
        output_dir=window_dir / "plots",
    )
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
import xarray as xr

from .reader import read_group, read_coords, read_dim_labels
from .transforms import prepare_time_series, prepare_gridded
from .figures import build_figure, FIGURE_REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_ob_type_config(ob_type: str) -> dict[str, Any] | None:
    """
    Load the plot config for *ob_type* by:

    1. Reading ``PLOT_CONFIG_YAML`` as the ``monitor_types.yaml`` index.
    2. Looking up the ob_type entry to find its monitor-type file path.
    3. Loading that file and returning the ob_type's config block.

    Parameters
    ----------
    ob_type:
        Observation type string, e.g. ``"prepbufr_adpsfc"``.

    Returns
    -------
    dict | None
        The per-ob-type config dict, or ``None`` if anything goes wrong
        (missing env var, missing ob_type, missing file).  Errors are logged
        so the caller can skip gracefully.
    """
    plot_config_yaml = os.getenv("PLOT_CONFIG_YAML")
    if not plot_config_yaml:
        logger.error("PLOT_CONFIG_YAML environment variable is not set.")
        return None

    index_path = Path(plot_config_yaml)
    if not index_path.exists():
        logger.error("PLOT_CONFIG_YAML '%s' does not exist.", index_path)
        return None

    with open(index_path, "r") as f:
        index = yaml.safe_load(f)

    if not isinstance(index, dict) or "ob_type_index" not in index:
        logger.error(
            "PLOT_CONFIG_YAML '%s' must define an 'ob_type_index' mapping.",
            index_path,
        )
        return None

    entry = index["ob_type_index"].get(ob_type)
    if entry is None:
        logger.warning(
            "ob_type '%s' not found in PLOT_CONFIG_YAML '%s'; "
            "no plots will be generated for this type.",
            ob_type, index_path,
        )
        return None

    # Resolve the monitor-type file path relative to the index file's directory.
    # Paths in monitor_types.yaml are relative to config/ (the index file's
    # parent), e.g. "monitor_types/conventional.yaml".
    mt_file = index_path.parent / entry["path"]
    if not mt_file.exists():
        logger.error(
            "Monitor-type config file '%s' (for ob_type '%s') does not exist.",
            mt_file, ob_type,
        )
        return None

    with open(mt_file, "r") as f:
        mt_doc = yaml.safe_load(f)

    if not isinstance(mt_doc, dict) or "ob_types" not in mt_doc:
        logger.error(
            "Monitor-type file '%s' must define an 'ob_types' mapping.",
            mt_file,
        )
        return None

    ob_config = mt_doc["ob_types"].get(ob_type)
    if ob_config is None:
        logger.error(
            "ob_type '%s' not found under 'ob_types' in '%s'.",
            ob_type, mt_file,
        )
        return None

    return ob_config


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def _validate_config(plot_config: dict, ob_type: str) -> bool:
    """
    Check that the per-ob-type config dict has the minimum required keys.
    Logs descriptive errors and returns False on any problem.
    """
    required_top = {"variable", "nc_groups", "figures"}
    missing = required_top - set(plot_config)
    if missing:
        logger.error(
            "[%s] Plot config is missing required key(s): %s", ob_type, missing
        )
        return False

    if "coords" not in plot_config["nc_groups"]:
        logger.error(
            "[%s] nc_groups is missing required key 'coords'.", ob_type
        )
        return False

    if not isinstance(plot_config["figures"], list) or not plot_config["figures"]:
        logger.error("[%s] 'figures' must be a non-empty list.", ob_type)
        return False

    for i, spec in enumerate(plot_config["figures"]):
        if "type" not in spec:
            logger.error("[%s] Figure spec #%d is missing 'type' key.", ob_type, i)
            return False
        if spec["type"] not in FIGURE_REGISTRY:
            logger.error(
                "[%s] Figure spec #%d has unknown type '%s'. "
                "Registered types: %s",
                ob_type, i, spec["type"], sorted(FIGURE_REGISTRY),
            )
            return False
        if "stat" not in spec:
            logger.error(
                "[%s] Figure spec #%d (type='%s') is missing 'stat' key.",
                ob_type, i, spec["type"],
            )
            return False
        if "group_path" not in spec:
            logger.error(
                "[%s] Figure spec #%d (type='%s') is missing 'group_path' key.",
                ob_type, i, spec["type"],
            )
            return False

    return True


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _discover_nc_files(runtime_dir: Path, ob_type: str) -> list[Path]:
    """
    Return a time-sorted list of NetCDF files for *ob_type* in *runtime_dir*.

    Files are matched by the ``{ob_type}_*.nc`` glob and sorted
    lexicographically on their names, which is equivalent to chronological
    order given the ``YYYYMMDDHH`` timestamp embedded in each filename.
    """
    pattern = f"{ob_type}_*.nc"
    files = sorted(runtime_dir.glob(pattern))
    logger.info(
        "[%s] Discovered %d NetCDF file(s) in %s",
        ob_type, len(files), runtime_dir,
    )
    return files


# ---------------------------------------------------------------------------
# Dataset cache
# ---------------------------------------------------------------------------

class _DatasetCache:
    """
    Simple in-memory cache keyed by ``(group_path, tuple(variables))``.

    Within a single :func:`dispatch_plots` call, multiple figure specs may
    request the same group and variables.  The cache ensures each group is
    opened and stacked only once.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, tuple[str, ...]], xr.Dataset] = {}

    def get_or_read(
        self,
        nc_files: list[Path],
        group_path: str,
        variables: list[str],
        dim_labels: dict[str, list[str]] | None = None,
    ) -> xr.Dataset:
        key = (group_path, tuple(sorted(variables)))
        if key not in self._store:
            logger.debug("Cache miss — reading group '%s'", group_path)
            self._store[key] = read_group(
                nc_files, group_path, variables, dim_labels=dim_labels
            )
        else:
            logger.debug("Cache hit — reusing group '%s'", group_path)
        return self._store[key]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def dispatch_plots(
    ob_type: str,
    runtime_dir: Path,
    output_dir: Path,
    plot_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Main entry point.  Load config, read, transform, and render all figures
    specified for one observation type.

    Parameters
    ----------
    ob_type:
        Observation type string, e.g. ``"prepbufr_adpsfc"``.  Used for file
        discovery (glob pattern) and forwarded to figure constructors for
        titles and filenames.
    runtime_dir:
        Per-window runtime directory containing the staged ``*.nc`` files.
    output_dir:
        Root directory for PNG output.  Created if absent.
    plot_config:
        Optional pre-loaded per-ob-type config dict.  If ``None`` (default),
        the config is loaded from ``PLOT_CONFIG_YAML`` via the
        ``monitor_types.yaml`` index.  Passing a dict directly is useful for
        testing without touching the filesystem.

    Returns
    -------
    dict
        Summary with keys:

        * ``ob_type`` (str)
        * ``status`` (str): ``"ok"`` | ``"skipped"`` | ``"partial"`` | ``"failed"``
        * ``figures_requested`` (int)
        * ``figures_written`` (int)
        * ``paths`` (list[str]): absolute paths of PNGs written
        * ``errors`` (list[str]): error messages for any failed specs
    """
    summary: dict[str, Any] = {
        "ob_type": ob_type,
        "status": "ok",
        "figures_requested": 0,
        "figures_written": 0,
        "paths": [],
        "errors": [],
    }

    # ------------------------------------------------------------------
    # 0. Load config if not supplied directly
    # ------------------------------------------------------------------
    if plot_config is None:
        plot_config = _load_ob_type_config(ob_type)
        if plot_config is None:
            summary["status"] = "skipped"
            summary["errors"].append(
                f"Could not load plot config for '{ob_type}' — see logs for details."
            )
            return summary

    # ------------------------------------------------------------------
    # 1. Validate config
    # ------------------------------------------------------------------
    if not _validate_config(plot_config, ob_type):
        summary["status"] = "skipped"
        summary["errors"].append("Invalid plot config — see logs for details.")
        return summary

    variable  = plot_config["variable"]
    nc_groups = plot_config["nc_groups"]
    fig_specs = plot_config["figures"]

    # ------------------------------------------------------------------
    # 2. Discover staged NetCDF files
    # ------------------------------------------------------------------
    nc_files = _discover_nc_files(Path(runtime_dir), ob_type)
    if not nc_files:
        logger.warning("[%s] No NetCDF files found in %s; skipping.", ob_type, runtime_dir)
        summary["status"] = "skipped"
        summary["errors"].append(
            f"No NetCDF files matching '{ob_type}_*.nc' in {runtime_dir}"
        )
        return summary

    # ------------------------------------------------------------------
    # 3. Read dimension labels once — shared across all time_series specs
    # ------------------------------------------------------------------
    domain_labels = read_dim_labels(nc_files, var_name="statisticDomain")
    dim_labels_for_ts = {"statisticDomain": domain_labels} if domain_labels else None

    # ------------------------------------------------------------------
    # 4. Read lat/lon coords once — shared across all map_gridded specs
    # ------------------------------------------------------------------
    lat = lon = None  # loaded lazily on first map_gridded spec

    # ------------------------------------------------------------------
    # 5. Dataset cache — one open-and-stack per unique (group_path, variables)
    # ------------------------------------------------------------------
    cache = _DatasetCache()

    # ------------------------------------------------------------------
    # 6. Iterate figure specs
    # ------------------------------------------------------------------
    summary["figures_requested"] = len(fig_specs)
    output_dir = Path(output_dir)

    for spec_idx, spec in enumerate(fig_specs):
        fig_type   = spec["type"]
        stat       = spec["stat"]
        group_path = spec["group_path"]

        logger.info(
            "[%s] Processing figure spec #%d: type='%s', stat='%s', group_path='%s'",
            ob_type, spec_idx, fig_type, stat, group_path,
        )

        # ---- Read ----
        try:
            if fig_type == "time_series":
                ds_raw = cache.get_or_read(
                    nc_files, group_path, [stat],
                    dim_labels=dim_labels_for_ts,
                )
            else:
                # map_gridded — no domain labels needed
                ds_raw = cache.get_or_read(nc_files, group_path, [stat])

        except Exception as exc:
            msg = f"Spec #{spec_idx} ({fig_type}): read failed — {exc}"
            logger.error("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

        if not ds_raw.data_vars:
            msg = f"Spec #{spec_idx} ({fig_type}): empty Dataset returned; skipping."
            logger.warning("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

        if stat not in ds_raw.data_vars:
            msg = (
                f"Spec #{spec_idx} ({fig_type}): stat '{stat}' not found in "
                f"Dataset after read (available: {list(ds_raw.data_vars)}). "
                "Check the 'stat' key in the figure spec."
            )
            logger.error("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

        # ---- Transform ----
        try:
            if fig_type == "time_series":
                ds_plot = prepare_time_series(ds_raw, variables=[stat])

            else:  # map_gridded
                # Load lat/lon on first gridded spec, then reuse.
                # Coords group path comes from nc_groups["coords"].
                if lat is None:
                    lat, lon = read_coords(
                        nc_files,
                        coords_group_path=nc_groups["coords"],
                    )
                ds_plot = prepare_gridded(ds_raw, lat, lon, variables=[stat])

        except Exception as exc:
            msg = f"Spec #{spec_idx} ({fig_type}): transform failed — {exc}"
            logger.error("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

        # ---- Render & save ----
        try:
            fig_obj = build_figure(
                figure_type=fig_type,
                ds=ds_plot,
                spec=spec,
                ob_type=ob_type,
                variable=variable,
                stat=stat,
                output_dir=output_dir,
            )
            written = fig_obj.save()
            summary["figures_written"] += len(written)
            summary["paths"].extend(str(p) for p in written)

        except Exception as exc:
            msg = f"Spec #{spec_idx} ({fig_type}): render/save failed — {exc}"
            logger.error("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

    # ------------------------------------------------------------------
    # 7. Final status
    # ------------------------------------------------------------------
    n_req = summary["figures_requested"]
    n_ok  = summary["figures_written"]

    if n_ok == 0 and n_req > 0:
        summary["status"] = "failed"
    elif summary["errors"]:
        summary["status"] = "partial"
    else:
        summary["status"] = "ok"

    logger.info(
        "[%s] dispatch_plots complete: %d/%d figure(s) written, status='%s'",
        ob_type, n_ok, n_req, summary["status"],
    )
    return summary
