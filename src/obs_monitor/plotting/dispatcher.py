"""
obs_monitor.plotting.dispatcher
================================

Ties the plotting sub-package together.  For each ob-type entry in the job
config the dispatcher:

1. Discovers and sorts the staged NetCDF files in the runtime directory.
2. Reads dimension labels (``statisticDomain``) once, shared across all reads.
3. For each figure spec in the config:
   a. Reads the appropriate group via :func:`~obs_monitor.plotting.reader.read_group`.
   b. Applies the correct transform pipeline
      (:func:`~obs_monitor.plotting.transforms.prepare_time_series` or
      :func:`~obs_monitor.plotting.transforms.prepare_gridded`).
   c. Instantiates the correct figure class via
      :func:`~obs_monitor.plotting.figures.build_figure` and calls
      ``.save()``.
4. Returns a summary dict the driver can log or inspect.

The dispatcher is the **only** module that knows about the job config
structure.  Reader, transforms, and figures are all config-agnostic.

Typical call from ``driver.py``
--------------------------------
Replace the ``generate_eva_config`` + ``run_eva`` block with::

    from obs_monitor.plotting.dispatcher import dispatch_plots

    results = dispatch_plots(
        ob_type=cfg.ob_type,
        runtime_dir=window_dir,
        plot_config=ob_plot_config,   # the per-ob-type dict from the new YAML
        output_dir=window_dir / "plots",
    )

Config format expected
-----------------------
.. code-block:: yaml

    prepbufr_adpsfc:
      variable: stationPressure
      unit: Pa
      nc_groups:
        time_series: byDomains/ombg/stationPressure
        gridded:     griddedBins/ombg/stationPressure
        coords:      griddedBins

      figures:
        - type: time_series
          stat: assimilated_mean
          title: "{ob_type} Time Series — Assimilated Mean O-F"
          y_label: "stationPressure (Pa)"
          domains:
            - Global
            - CONUS

        - type: map_gridded
          stat: assimilated_mean
          title: "{ob_type} O-F — Mean Cycle Avg (gridded)"
          colorbar_label: "stationPressure (Pa)"
          projection: plcarr
          domain: global
          cmap: coolwarm
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import xarray as xr

from .reader import read_group, read_coords, read_dim_labels
from .transforms import prepare_time_series, prepare_gridded
from .figures import build_figure, FIGURE_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Maps figure spec ``type`` to the nc_groups key that holds its group path.
# Extend alongside FIGURE_REGISTRY when adding new figure types that need a
# different group.
_FIGURE_TYPE_TO_GROUP_KEY: dict[str, str] = {
    "time_series": "time_series",
    "map_gridded":  "gridded",
}


def _discover_nc_files(runtime_dir: Path, ob_type: str) -> list[Path]:
    """
    Return a time-sorted list of NetCDF files for *ob_type* in *runtime_dir*.

    Files are matched by the ``{ob_type}_*.nc`` glob and sorted
    lexicographically on their names, which is equivalent to chronological
    order given the ``YYYYMMDDHH`` timestamp embedded in each filename.

    Parameters
    ----------
    runtime_dir:
        The per-window runtime directory populated by the driver.
    ob_type:
        Observation type string, e.g. ``"prepbufr_adpsfc"``.

    Returns
    -------
    list[Path]
        Sorted list of matching paths.  Empty list if none are found (the
        caller is responsible for deciding whether to skip or raise).
    """
    pattern = f"{ob_type}_*.nc"
    files = sorted(runtime_dir.glob(pattern))
    logger.info(
        "[%s] Discovered %d NetCDF file(s) in %s",
        ob_type,
        len(files),
        runtime_dir,
    )
    return files


def _validate_config(plot_config: dict, ob_type: str) -> bool:
    """
    Check that the per-ob-type config dict has the minimum required keys.
    Logs descriptive errors and returns False on any problem so the caller
    can skip gracefully rather than raise.
    """
    required_top = {"variable", "nc_groups", "figures"}
    missing = required_top - set(plot_config)
    if missing:
        logger.error(
            "[%s] Plot config is missing required key(s): %s", ob_type, missing
        )
        return False

    required_groups = {"time_series", "gridded", "coords"}
    missing_groups = required_groups - set(plot_config["nc_groups"])
    if missing_groups:
        logger.error(
            "[%s] nc_groups is missing required key(s): %s", ob_type, missing_groups
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

    return True


# ---------------------------------------------------------------------------
# Dataset cache — avoid re-reading the same group twice within one dispatch
# ---------------------------------------------------------------------------

class _DatasetCache:
    """
    Simple in-memory cache keyed by ``(group_path, tuple(variables))``.

    Within a single :func:`dispatch_plots` call, multiple figure specs may
    request the same group and variables (e.g. two time-series specs for
    the same group but different domains).  The cache ensures each group is
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
    plot_config: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """
    Main entry point.  Read, transform, and render all figures specified for
    one observation type.

    Parameters
    ----------
    ob_type:
        Observation type string, e.g. ``"prepbufr_adpsfc"``.  Used for file
        discovery (glob pattern) and forwarded to figure constructors for
        titles and filenames.
    runtime_dir:
        Per-window runtime directory containing the staged ``*.nc`` files.
    plot_config:
        The per-ob-type section of the new plotting YAML.  Must contain
        ``variable``, ``nc_groups``, and ``figures`` keys (see module
        docstring for the full schema).
    output_dir:
        Root directory for PNG output.  Created if absent.  A ``plots/``
        subdirectory is **not** added here — pass ``window_dir / "plots"``
        from the driver to match the existing COM copy logic.

    Returns
    -------
    dict
        Summary with keys:

        * ``ob_type`` (str)
        * ``status`` (str): ``"ok"`` | ``"skipped"`` | ``"partial"``
        * ``figures_requested`` (int)
        * ``figures_written`` (int)
        * ``paths`` (list[str]): absolute paths of PNGs written
        * ``errors`` (list[str]): error messages for any failed specs

    Examples
    --------
    Replacing the EVA block in ``driver.py``::

        from obs_monitor.plotting.dispatcher import dispatch_plots

        result = dispatch_plots(
            ob_type=cfg.ob_type,
            runtime_dir=window_dir,
            plot_config=ob_plot_config,
            output_dir=window_dir / "plots",
        )
        logger.info(
            "[%s] Plots: %d/%d written",
            cfg.ob_type,
            result["figures_written"],
            result["figures_requested"],
        )
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
    # 0. Validate config
    # ------------------------------------------------------------------
    if not _validate_config(plot_config, ob_type):
        summary["status"] = "skipped"
        summary["errors"].append("Invalid plot config — see logs for details.")
        return summary

    variable   = plot_config["variable"]
    nc_groups  = plot_config["nc_groups"]
    fig_specs  = plot_config["figures"]

    # ------------------------------------------------------------------
    # 1. Discover staged NetCDF files
    # ------------------------------------------------------------------
    nc_files = _discover_nc_files(Path(runtime_dir), ob_type)
    if not nc_files:
        logger.warning("[%s] No NetCDF files found in %s; skipping.", ob_type, runtime_dir)
        summary["status"] = "skipped"
        summary["errors"].append(f"No NetCDF files matching '{ob_type}_*.nc' in {runtime_dir}")
        return summary

    # ------------------------------------------------------------------
    # 2. Read dimension labels once — shared across all figure specs
    # ------------------------------------------------------------------
    domain_labels = read_dim_labels(nc_files, var_name="statisticDomain")
    dim_labels_for_ts = {"statisticDomain": domain_labels} if domain_labels else None

    # ------------------------------------------------------------------
    # 3. Read lat/lon coords once — shared across all gridded specs
    # ------------------------------------------------------------------
    lat = lon = None  # loaded lazily on first gridded spec

    # ------------------------------------------------------------------
    # 4. Dataset cache — one open-and-stack per unique (group, variables)
    # ------------------------------------------------------------------
    cache = _DatasetCache()

    # ------------------------------------------------------------------
    # 5. Iterate figure specs
    # ------------------------------------------------------------------
    summary["figures_requested"] = len(fig_specs)
    output_dir = Path(output_dir)

    for spec_idx, spec in enumerate(fig_specs):
        fig_type = spec["type"]
        stat     = spec["stat"]

        logger.info(
            "[%s] Processing figure spec #%d: type='%s', stat='%s'",
            ob_type, spec_idx, fig_type, stat,
        )

        # Determine which nc_groups key to use for this figure type
        group_key = _FIGURE_TYPE_TO_GROUP_KEY.get(fig_type)
        if group_key is None:
            # Shouldn't happen after _validate_config, but guard anyway
            msg = f"No group key mapping for figure type '{fig_type}'."
            logger.error("[%s] %s", ob_type, msg)
            summary["errors"].append(msg)
            continue

        group_path = nc_groups[group_key]

        # ---- Read ----
        try:
            if fig_type == "time_series":
                ds_raw = cache.get_or_read(
                    nc_files, group_path, [stat],
                    dim_labels=dim_labels_for_ts,
                )
            else:
                # Gridded — no domain labels needed
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

        # Guard: requested stat must actually be present in the Dataset.
        # read_group only reads variables that exist in the file; if the stat
        # name was wrong or absent in every cycle, data_vars will exist but
        # won't contain the requested key.
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
                # Load lat/lon on first gridded spec, then reuse
                if lat is None:
                    lat, lon = read_coords(nc_files, coords_group_path=nc_groups["coords"])
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
    # 6. Final status
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
