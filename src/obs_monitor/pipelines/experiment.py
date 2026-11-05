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

Each input gets its own cache folder, ``summaries/<name>-<input id>/``, e.g.
``summaries/diags-46fd7765333d/``. ``<name>`` is the folder the diag files
are in (or the experiment folder of a ``com`` comroot), so people can tell
the caches apart. ``<input id>`` is a short hash of the configured source:
the glob template (from ``--input`` + ``--pattern``), or for a ``com`` source
its comroot, run and templates, so two inputs never share a folder even if
their names match. It doesn't depend on which obs spaces or components are
run. ``input.json`` in the folder gives the full source. So summaries from
two experiments can never be mixed, even in the same ``--output`` folder or
when two runs start at once, and nothing has to be locked or refused. A
run YAML's own ``summary_template`` gets the same ``<name>-<input id>/``
folder inserted. Cache folders from before this layout are simply not read.

One ``--output`` per experiment is still the clearest layout: figures and
``obsmon_status.json`` sit at the top of ``--output`` and are overwritten by
the next run there.

Nothing under ``--input`` is ever deleted. Scratch files are only removed if
this run extracted them from a tarball (``source: {type: com}`` in a run YAML).

Exit status: 0 if any figure was written, 1 if nothing could be produced
(e.g. no files matched), 2 for a bad argument or configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from obs_monitor.config import ConfigError, RunConfig, load_obs_spaces
from obs_monitor.config.obs_spaces import DEFAULT_OBS_SPACE_DIR
from obs_monitor.config.run_config import read_run_yaml
from obs_monitor.io.catalog import DEFAULT_MEMBER_TEMPLATE, DEFAULT_TARBALL_TEMPLATE, CatalogError, GlobLocator
from obs_monitor.io.timewindow import CycleError, cycle_range

from .run import RunResult, run_window

logger = logging.getLogger("obs_monitor.experiment")

DEFAULT_PATTERN = "diag_{obs_space}_{cycle:%Y%m%d%H}.nc"
INPUT_INFO = "input.json"
SUMMARY_NAME = "{obs_space}/{variable}/summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc"


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


def _expand(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return os.path.normpath(os.path.expandvars(os.path.expanduser(value)))


def describe_source(source: Any) -> dict | None:
    """
    The configured source in a canonical form: what the files are read from,
    independent of which obs spaces or components a run selects. None if
    ``source`` is malformed (RunConfig validation reports that).
    """
    if not isinstance(source, Mapping):
        return None
    if source.get("type") == "glob":
        return {"type": "glob", "template": _expand(source.get("template"))}
    if source.get("type") == "com":
        return {"type": "com", "comroot": _expand(source.get("comroot")), "run": source.get("run", "gdas"),
                "tarball_template": source.get("tarball_template", DEFAULT_TARBALL_TEMPLATE),
                "member_template": source.get("member_template", DEFAULT_MEMBER_TEMPLATE)}
    return None


def input_id(desc: Mapping) -> str:
    """Short, stable id for a source description (same source -> same id)."""
    return hashlib.sha256(json.dumps(desc, sort_keys=True).encode()).hexdigest()[:12]


def input_label(desc: Mapping) -> str:
    """
    A readable name for the input: the folder the diag files are in (glob), or
    the experiment folder (com comroot). Only for people; uniqueness comes
    from :func:`input_id`.
    """
    if desc.get("type") == "glob":
        template = str(desc.get("template") or "")
        head = template.split("{", 1)[0]
        folder = head if head.endswith("/") else os.path.dirname(head)
    else:
        folder = str(desc.get("comroot") or "")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(folder).name).strip("._-")[:40]
    return name or "input"


def cache_folder_name(desc: Mapping) -> str:
    """``<label>-<input id>``, e.g. ``diags-46fd7765333d``: readable, and never shared by two inputs."""
    return f"{input_label(desc)}-{input_id(desc)}"


def keyed_cache(cfg: dict) -> tuple[dict, Path | None, dict | None]:
    """
    ``cfg`` with its summary cache moved into a folder for this input:
    ``<cache root>/<name>-<input id>/...``. Returns (cfg, input.json path, source description);
    the last two are None when cfg is too malformed to key (validation then reports why).
    """
    desc = describe_source(cfg.get("source"))
    template = cfg.get("summary_template")
    if desc is None or not isinstance(template, (str, type(None))):
        return cfg, None, None
    key = cache_folder_name(desc)
    if template is None:
        output = cfg.get("output_dir")
        if not isinstance(output, str):
            return cfg, None, None
        root = Path(_expand(output)) / "summaries" / key
        keyed = f"{root}/{SUMMARY_NAME}"
    else:
        template = os.path.expandvars(os.path.expanduser(template))
        if "{" not in template:
            return cfg, None, None
        cut = template[:template.index("{")].rfind("/") + 1          # last folder before any field
        root = Path(template[:cut] + key)
        keyed = template[:cut] + key + "/" + template[cut:]
    return {**cfg, "summary_template": keyed}, root / INPUT_INFO, desc


def write_input_info(path: Path, desc: Mapping) -> None:
    """Say which input a cache folder belongs to (informational; atomic, identical for the same input)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(desc, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def build_run_config(args: argparse.Namespace) -> tuple[RunConfig, Path | None, dict | None] | None:
    """
    (RunConfig, input.json path, source description) from the command line or
    ``--config``, with the summary cache keyed by input. None if no configured
    obs space has files in the window.
    """
    if args.config:
        extra = [a for a in ("input", "start", "end", "output", "obs_space", "obs_space_config")
                 if getattr(args, a)]
        if extra or args.pattern != DEFAULT_PATTERN or args.interval != 6:
            raise ConfigError("--config cannot be combined with other options; put them in the YAML.")
        path = _abs(args.config)
        cfg = read_run_yaml(path)
        info = (None, None)
        if isinstance(cfg, dict):
            cfg, *info = keyed_cache(cfg)
        return (RunConfig.from_dict(cfg, source_name=path), *info)

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
    cfg, info_path, desc = keyed_cache(cfg)
    return RunConfig.from_dict(cfg, source_name="command line"), info_path, desc


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
        built = build_run_config(args)
    except (ConfigError, CatalogError) as exc:
        logger.error("%s", exc)
        return 2
    if built is None:
        return 1
    rc, info_path, desc = built
    if info_path is not None:
        try:
            write_input_info(info_path, desc)
        except OSError as exc:
            logger.error("Cannot write to the summary cache folder %s: %s", info_path.parent, exc)
            return 2
        logger.info("Summary cache for this input: %s", info_path.parent)

    result = run_window(rc)
    _report(result)
    if result.figures_written == 0:
        logger.error("No figures were produced.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
