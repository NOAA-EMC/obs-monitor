"""
obs_monitor.pipelines.experiment
================================

Entry point for experiment runs: point it at a folder of IODA diag files and
a time range, get the same figures and status file as the workflow run::

    obs-monitor-exp --input /scratch/$USER/myexpt/diags \\
                    --start 2026100100 --end 2026100518 \\
                    --output /scratch/$USER/myexpt/obsmon

    # or, with everything in a run YAML (see obs_monitor.config.run_config)
    obs-monitor-exp --config my_run.yaml

(``python -m obs_monitor.pipelines.experiment`` works the same.)

``--input``/``--pattern`` is a ``source: {type: glob}`` run: plain diag files
already on disk. A run YAML can also use ``source: {type: com}`` to read
straight from global-workflow tarballs, extracting only the diag files it
needs (see :mod:`obs_monitor.config.run_config`).

Finding the files
-----------------
``--pattern`` is the file name under ``--input``, with ``{obs_space}`` and
``{cycle:<strftime>}`` fields. The default matches the GDAS diag files::

    diag_{obs_space}_{cycle:%Y%m%d%H}.nc

Sub-folders work too, e.g. ``--pattern "{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"``.

Which obs spaces
----------------
Without ``--obs-space``, every configured obs space with at least one file in
the window is run. To pick some, list them, separated by spaces or commas::

    --obs-space prepbufr_adpsfc prepbufr_adpupa
    --obs-space prepbufr_adpsfc,prepbufr_adpupa

(In a run YAML: ``obs_spaces: [prepbufr_adpsfc, prepbufr_adpupa]``.)
Files for obs spaces with no configuration are listed in the log and
skipped; add them with ``--obs-space-config my_obs_spaces.yaml`` (same format
as ``config/yaml/obs_spaces/*.yaml``).

Output
------
``--output`` gets the figures, ``obsmon_status.json`` and ``summaries/`` (the
per-cycle cache, so re-running or extending the window only reads new
cycles).

A summary cache belongs to one input. ``obsmon_run.json`` in the cache folder
(``<output>/summaries/`` by default) records which input made it, for
command-line and ``--config`` runs alike. A run is refused (exit 2) if that
record names a different input, or if it can't be read, so cached summaries
from another experiment are never mixed in. Use a new ``--output`` per
experiment.

Nothing under ``--input`` is ever deleted. Scratch files are only removed if
this run extracted them from a tarball (``source: {type: com}`` in a run YAML).

Exit status: 0 if any figure was written, 1 if nothing could be produced
(e.g. no files matched), 2 for a bad argument or configuration.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from obs_monitor.config import ConfigError, RunConfig, load_obs_spaces, load_run_config
from obs_monitor.config.obs_spaces import DEFAULT_OBS_SPACE_DIR
from obs_monitor.io.catalog import CatalogError, ComTarballLocator, GlobLocator
from obs_monitor.io.timewindow import CycleError, cycle_range

from .run import RunResult, run_window

logger = logging.getLogger("obs_monitor.experiment")

DEFAULT_PATTERN = "diag_{obs_space}_{cycle:%Y%m%d%H}.nc"
RUN_RECORD = "obsmon_run.json"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="obs-monitor-exp",
        description="Make obs-monitor figures for an experiment's IODA diag files.",
        epilog="Example: obs-monitor-exp --input /path/diags --start 2026100100 --end 2026100518 "
               "--output /path/obsmon")
    p.add_argument("--config", metavar="YAML", help="Run YAML with everything below (other options not allowed).")
    p.add_argument("--input", metavar="DIR", help="Folder with the diag files.")
    p.add_argument("--pattern", default=DEFAULT_PATTERN,
                   help="File name under --input, with {obs_space} and {cycle:...} "
                        f"(default: {DEFAULT_PATTERN.replace('%', '%%')}).")
    p.add_argument("--start", metavar="YYYYMMDDHH", help="First cycle.")
    p.add_argument("--end", metavar="YYYYMMDDHH", help="Last cycle.")
    p.add_argument("--interval", type=int, default=6, metavar="HOURS", help="Hours between cycles (default: 6).")
    p.add_argument("--output", metavar="DIR", help="Where figures, status and summaries go.")
    p.add_argument("--obs-space", nargs="+", metavar="NAME",
                   help="Obs spaces to run, separated by spaces or commas "
                        "(default: every configured obs space with files in the window).")
    p.add_argument("--obs-space-config", nargs="+", metavar="YAML",
                   help="Extra obs-space YAML file(s) or folder(s), for obs spaces not in the shipped config.")
    return p


def _abs(path: str) -> str:
    """CLI paths may be relative to where the command is run; RunConfig wants absolute."""
    return str(Path(path).expanduser().resolve())


def discover_obs_spaces(template: str, cycles) -> list[str]:
    """Obs-space names with at least one file matching ``template`` in ``cycles``, sorted."""
    loc = GlobLocator(template)
    found: set[str] = set()
    for cycle in cycles:
        found.update(loc.locate(cycle))
    return sorted(found)


def source_identity(rc: RunConfig) -> str:
    """What the run reads from, as one string: the same input always gives the same string."""
    parts = set()
    for loc in rc.locators.values():
        if isinstance(loc, GlobLocator):
            parts.add(f"glob:{loc.template}")
        elif isinstance(loc, ComTarballLocator):
            parts.add(f"com:{loc.comroot}|{loc.run}|{loc.component}|{loc.tarball_template}|{loc.member_template}")
        else:
            parts.add(repr(loc))
    return " + ".join(sorted(parts))


def cache_root(rc: RunConfig) -> Path:
    """The fixed folder the summary cache lives under (the part of the template before any field)."""
    head = (rc.summary_template or str(rc.output_dir / "summaries") + "/").split("{", 1)[0]
    return Path(head) if head.endswith("/") else Path(head).parent


def check_run_record(rc: RunConfig) -> Path:
    """
    Refuse to mix cached summaries from two inputs: compare this run's input
    with the one recorded in the cache folder, then record it. Raises
    ConfigError if the record names another input or can't be validated.
    """
    identity = source_identity(rc)
    record = cache_root(rc) / RUN_RECORD
    if record.exists():
        try:
            previous = json.loads(record.read_text())["input"]
            if not isinstance(previous, str) or not previous:
                raise ValueError("invalid input identity")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError(f"Cannot validate {record} ({exc}); use a new --output folder.") from exc
        if previous != identity:
            raise ConfigError(f"The summary cache in {record.parent} was made from a different input "
                              f"({previous}). Use a new --output folder for this experiment.")
        return record
    record.parent.mkdir(parents=True, exist_ok=True)
    tmp = record.with_name(record.name + ".tmp")
    tmp.write_text(json.dumps({"input": identity}, indent=2) + "\n")
    os.replace(tmp, record)                         # atomic: never left half-written
    return record


def build_run_config(args: argparse.Namespace) -> RunConfig | None:
    """RunConfig from the command line, or None if no configured obs space has files in the window."""
    if args.config:
        extra = [a for a in ("input", "start", "end", "output", "obs_space", "obs_space_config")
                 if getattr(args, a)]
        if extra or args.pattern != DEFAULT_PATTERN or args.interval != 6:
            raise ConfigError("--config cannot be combined with other options; put them in the YAML.")
        return load_run_config(_abs(args.config))

    missing = [f"--{a}" for a in ("input", "start", "end", "output") if not getattr(args, a)]
    if missing:
        raise ConfigError(f"Missing {', '.join(missing)} (or use --config).")
    if Path(args.pattern).is_absolute() or "{obs_space}" not in args.pattern or "{cycle" not in args.pattern:
        raise ConfigError("--pattern must be a file name relative to --input containing {obs_space} "
                          "and {cycle:...}.")
    input_dir = Path(_abs(args.input))
    if not input_dir.is_dir():
        raise ConfigError(f"--input {input_dir} is not a folder.")
    try:
        cycles = cycle_range(args.start, args.end, args.interval)
    except CycleError as exc:
        raise ConfigError(f"--start/--end/--interval: {exc}") from exc

    template = str(input_dir / args.pattern)
    try:
        GlobLocator(template)                       # checks the fields format, before any discovery
    except CatalogError as exc:
        raise ConfigError(f"Invalid --pattern: {exc}") from exc
    extra_configs = [_abs(p) for p in args.obs_space_config or []]
    known = load_obs_spaces([DEFAULT_OBS_SPACE_DIR] + extra_configs)

    if args.obs_space:
        names = [n.strip() for arg in args.obs_space for n in arg.split(",") if n.strip()]
    else:
        found = discover_obs_spaces(template, cycles)
        unconfigured = [n for n in found if n not in known]
        if unconfigured:
            logger.warning("Found files for obs spaces with no configuration, skipped: %s. "
                           "Add them with --obs-space-config.", ", ".join(unconfigured))
        names = [n for n in found if n in known]
        if not names:
            logger.error("No files for any configured obs space matched %s between %s and %s.",
                         template, args.start, args.end)
            return None
        logger.info("Obs spaces with files in the window: %s", ", ".join(names))

    output = Path(_abs(args.output))
    cfg = {
        "cycles": {"start": args.start, "end": args.end, "interval_hours": args.interval},
        "source": {"type": "glob", "template": template},
        "obs_spaces": names,
        "output_dir": str(output),
        "work_dir": str(output / "work"),
    }
    if extra_configs:
        cfg["obs_space_config"] = extra_configs
    return RunConfig.from_dict(cfg, source_name="command line")


def _report(result: RunResult) -> None:
    for st in result.obs_spaces:
        detail = st.error or (f"missing {', '.join(st.missing_cycles)}" if st.missing_cycles else "")
        logger.info("  %-28s %-8s %d/%d cycles  %d figures  %s", st.obs_space, st.status,
                    st.cycles_with_data, st.cycles_expected, st.figures_written, detail)
    logger.info("Figures and %s are in %s", "obsmon_status.json", result.output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    try:
        rc = build_run_config(args)
        if rc is not None:
            check_run_record(rc)                    # command line and --config alike
    except (ConfigError, CatalogError) as exc:
        logger.error("%s", exc)
        return 2
    if rc is None:
        return 1

    result = run_window(rc)
    _report(result)
    if result.figures_written == 0:
        logger.error("No figures were produced.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
