"""
obs_monitor.pipelines.operational
=================================

The Rocoto ``obs_monitor_driver`` task (``jobs/rocoto/run_driver.sh``)::

    python -m obs_monitor.pipelines.operational

Reads the job's environment, builds one :class:`~obs_monitor.config.RunConfig`
per component and runs :func:`~obs_monitor.pipelines.run.run_window`. This is
the only module that reads environment variables.

Environment (set by the Rocoto template)
----------------------------------------
``PDY`` + ``CYC`` (or ``CDATE``)  end of the window
``CYCLES``, ``INTERVAL_HOURS``    window length
``RUN``                           e.g. gdas
``COMPONENT``                     one or a comma-separated list (atmos, chem, snow, ...)
``DATAROOT``                      staged diag files (``ush/copy_ioda_stats.sh``) and the summary cache
``COMROOT``                       figures + status, pushed to the web server
``RUNTIME_DIR``                   scratch
``KEEP_DATA``                     keep scratch files (true/false)
``OBSMON_OBS_SPACE_CONFIG``       optional extra obs-space YAML

Layout
------
* diag files (input):  ``$DATAROOT/$RUN.YYYYMMDD/HH/analysis/<component>/diag_<obs_space>_YYYYMMDDHH.nc``
* summaries (cache):   ``$DATAROOT/$RUN.YYYYMMDD/HH/products/<component>/anlmon/``
  ``summary_<obs_space>_<variable>_YYYYMMDDHH.nc``
  (where the old stat files lived; not pushed to the web server)
* figures + status:    ``$COMROOT/$RUN.$PDY/$CYC/<component>/`` (same folder as the old driver's plots)

Exit status: 0 if any figure was written; 1 if nothing at all could be
produced (the only data condition Rocoto should flag); 2 for a configuration
or environment error. Partial results are reported in ``obsmon_status.json``
and the log, not by failing the job.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Mapping

from obs_monitor.config import ConfigError, RunConfig, load_obs_spaces
from obs_monitor.config.obs_spaces import DEFAULT_OBS_SPACE_DIR
from obs_monitor.io.timewindow import CycleError, parse_cycle

from .run import run_window

logger = logging.getLogger("obs_monitor.operational")

DIAG_TEMPLATE = "{dataroot}/{run}.{{cycle:%Y%m%d}}/{{cycle:%H}}/analysis/{{component}}/" \
                "diag_{{obs_space}}_{{cycle:%Y%m%d%H}}.nc"
SUMMARY_TEMPLATE = "{dataroot}/{run}.{{cycle:%Y%m%d}}/{{cycle:%H}}/products/{{component}}/anlmon/" \
                   "summary_{{obs_space}}_{{variable}}_{{cycle:%Y%m%d%H}}.nc"


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Environment variable {name} is not set.")
    return value


def _flag(value: str | None) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t")


def build_run_configs(env: Mapping[str, str]) -> dict[str, RunConfig]:
    """One RunConfig per component in ``COMPONENT`` that has obs spaces configured."""
    cdate = env.get("CDATE", "").strip() or (env.get("PDY", "").strip() + env.get("CYC", "").strip())
    if not cdate:
        raise ConfigError("Set CDATE, or both PDY and CYC.")
    try:
        end = parse_cycle(cdate)
    except CycleError as exc:
        raise ConfigError(f"CDATE/PDY+CYC: {exc}") from exc
    try:
        n_cycles = int(_require(env, "CYCLES"))
        interval = int(env.get("INTERVAL_HOURS", "6"))
    except ValueError as exc:
        raise ConfigError(f"CYCLES and INTERVAL_HOURS must be integers: {exc}") from exc

    run = _require(env, "RUN")
    dataroot = _require(env, "DATAROOT")
    comroot = _require(env, "COMROOT")
    runtime = _require(env, "RUNTIME_DIR")
    components = [c.strip() for c in _require(env, "COMPONENT").split(",") if c.strip()]
    extra = env.get("OBSMON_OBS_SPACE_CONFIG", "").strip()

    paths = [DEFAULT_OBS_SPACE_DIR] + ([extra] if extra else [])
    known = load_obs_spaces(paths)

    configs = {}
    for comp in components:
        names = [n for n, o in known.items() if o.component == comp]
        if not names:
            logger.warning("No obs spaces configured for component '%s'; nothing to do for it.", comp)
            continue
        cfg = {
            "cycles": {"end": end.strftime("%Y%m%d%H"), "n_cycles": n_cycles, "interval_hours": interval},
            "source": {"type": "glob", "template": DIAG_TEMPLATE.format(dataroot=dataroot, run=run)},
            "obs_spaces": names,
            "output_dir": f"{comroot}/{run}.{end:%Y%m%d}/{end:%H}/{comp}",
            "work_dir": f"{runtime}/{end:%Y%m%d%H}/{comp}",
            "keep_work": _flag(env.get("KEEP_DATA")),
            "summary_template": SUMMARY_TEMPLATE.format(dataroot=dataroot, run=run),
        }
        if extra:
            cfg["obs_space_config"] = extra
        configs[comp] = RunConfig.from_dict(cfg, source_name=f"operational ({comp})")
    return configs


def main(env: Mapping[str, str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = os.environ if env is None else env
    try:
        configs = build_run_configs(env)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 2
    if not configs:
        logger.warning("No component in COMPONENT has obs spaces configured; nothing to do.")
        return 0

    written = 0
    for comp, rc in configs.items():
        logger.info("=== %s: %d obs spaces, cycles %s-%s -> %s", comp, len(rc.obs_spaces),
                    f"{rc.cycles[0]:%Y%m%d%H}", f"{rc.cycles[-1]:%Y%m%d%H}", rc.output_dir)
        result = run_window(rc)
        written += result.figures_written
        for st in result.obs_spaces:
            if st.status != "ok":
                detail = st.error or (f"missing {', '.join(st.missing_cycles)}" if st.missing_cycles else "")
                logger.warning("  %s: %s %s", st.obs_space, st.status.upper(), detail)

    if written == 0:
        logger.error("No figures were produced for any component.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
