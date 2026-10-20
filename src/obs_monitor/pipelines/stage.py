"""
obs_monitor.pipelines.stage
===========================

The copy step (``ush/copy_ioda_stats.sh``, run from cron): for every cycle in
the global-workflow output that hasn't been staged yet, extract **only the
monitored** ``diag_<obs_space>_YYYYMMDDHH.nc`` files from::

    SOURCE/<run>.YYYYMMDD/HH/analysis/<component>/<run>.tHHz.<component>_analysis.ioda_hofx.tar.gz

into::

    TARGET/<run>.YYYYMMDD/HH/analysis/<component>/

then write ``obsmon_staged.json`` there. The Rocoto driver task waits on that
marker, so it never starts on a half-copied cycle.

Which obs spaces are "monitored" comes from the obs-space YAML (those whose
``component`` matches). A component with none configured still gets markers
(with no files), so the driver task isn't left waiting on it. Tarballs younger than ``--min-age`` minutes are left
for the next run (they may still be being written). A cycle whose tarball is
missing or unreadable is left unstaged and retried next time; obs spaces not
in the tarball are listed as missing in the marker.

    python -m obs_monitor.pipelines.stage --src SOURCE --target TARGET [--run gdas] [--component atmos]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

from obs_monitor.config import ConfigError, load_obs_spaces
from obs_monitor.config.obs_spaces import DEFAULT_OBS_SPACE_DIR
from obs_monitor.io.catalog import ComTarballLocator
from obs_monitor.io.timewindow import format_cycle

logger = logging.getLogger("obs_monitor.stage")

MARKER = "obsmon_staged.json"
TARBALL_TEMPLATE = "{comroot}/{run}.{cycle:%Y%m%d}/{cycle:%H}/analysis/{component}/" \
                   "{run}.t{cycle:%H}z.{component}_analysis.ioda_hofx.tar.gz"
EXTRACT_TEMPLATE = "{work_dir}/{run}.{cycle:%Y%m%d}/{cycle:%H}/analysis/{component}"


def source_cycles(source: Path, run: str) -> list[datetime]:
    """Cycles present in SOURCE as ``<run>.YYYYMMDD/HH`` directories."""
    rx = re.compile(rf"^{re.escape(run)}\.(\d{{8}})$")
    out = []
    for day in source.glob(f"{run}.*"):
        m = rx.match(day.name)
        if not (m and day.is_dir()):
            continue
        for hh in day.iterdir():
            if hh.is_dir() and re.fullmatch(r"\d{2}", hh.name):
                out.append(datetime.strptime(m.group(1) + hh.name, "%Y%m%d%H"))
    return sorted(out)


def stage(source: Path, target: Path, run: str, component: str, obs_spaces: list[str],
          min_age_minutes: float = 10.0, now: float | None = None) -> dict[str, str]:
    """
    Stage every not-yet-staged cycle. Returns ``{cycle: outcome}`` with outcome
    ``staged`` / ``already staged`` / ``too new`` / ``no tarball`` / ``unreadable``.
    """
    loc = ComTarballLocator(comroot=source, work_dir=target, component=component, run=run,
                            tarball_template=TARBALL_TEMPLATE, extract_dir_template=EXTRACT_TEMPLATE)
    now = time.time() if now is None else now
    outcomes = {}
    for cycle in source_cycles(source, run):
        key = format_cycle(cycle)
        dest = loc.extract_dir(cycle)
        if (dest / MARKER).is_file():
            outcomes[key] = "already staged"
            continue
        tarball = loc.tarball(cycle)
        if not tarball.is_file() or tarball.stat().st_size == 0:
            outcomes[key] = "no tarball"
            continue
        if now - tarball.stat().st_mtime < min_age_minutes * 60:
            outcomes[key] = "too new"
            continue
        # No obs spaces for this component: mark the cycle without reading the tarball,
        # so the driver task (which waits on every component's marker) isn't blocked.
        found = loc.locate(cycle, obs_spaces) if obs_spaces else {}
        if obs_spaces and not found and not _readable(tarball):
            outcomes[key] = "unreadable"            # retried next run
            continue
        dest.mkdir(parents=True, exist_ok=True)
        marker = {"cycle": key, "tarball": str(tarball),
                  "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "files": {o: p.name for o, p in sorted(found.items())},
                  "missing": sorted(set(obs_spaces) - set(found))}
        tmp = dest / (MARKER + ".part")
        tmp.write_text(json.dumps(marker, indent=2))
        tmp.replace(dest / MARKER)
        outcomes[key] = "staged"
        logger.info("%s: staged %d/%d obs spaces%s", key, len(found), len(obs_spaces),
                    f" (missing {', '.join(marker['missing'])})" if marker["missing"] else "")
    return outcomes


def _readable(tarball: Path) -> bool:
    try:
        with tarfile.open(tarball, "r:*") as tar:
            next(iter(tar), None)
        return True
    except (tarfile.TarError, OSError, EOFError):
        return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1], formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("-s", "--src", required=True, type=Path, help="global-workflow COMROOT (has <run>.YYYYMMDD/)")
    ap.add_argument("-t", "--target", required=True, type=Path, help="DATAROOT for obs-monitor")
    ap.add_argument("-r", "--run", default="gdas")
    ap.add_argument("-c", "--component", default="atmos")
    ap.add_argument("--min-age", type=float, default=10.0, help="minutes a tarball must be unchanged (default 10)")
    ap.add_argument("--obs-space-config", type=Path, help="extra obs-space YAML (absolute path)")
    args = ap.parse_args(argv)

    for label, p in (("--src", args.src), ("--target", args.target)):
        if not p.is_absolute() or not p.is_dir():
            logger.error("%s must be an existing absolute directory: %s", label, p)
            return 2
    try:
        paths = [DEFAULT_OBS_SPACE_DIR] + ([args.obs_space_config] if args.obs_space_config else [])
        names = [n for n, o in load_obs_spaces(paths).items() if o.component == args.component]
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 2
    if not names:
        logger.warning("No obs spaces configured for component '%s'; marking cycles staged with no files.",
                       args.component)

    outcomes = stage(args.src, args.target, args.run, args.component, names, args.min_age)
    counts: dict[str, int] = {}
    for v in outcomes.values():
        counts[v] = counts.get(v, 0) + 1
    logger.info("%s %s: %s", args.run, args.component, ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or
                "no cycles in source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
