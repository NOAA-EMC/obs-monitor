"""
obs_monitor.pipelines.run
=========================

The shared engine: one :class:`~obs_monitor.config.RunConfig` in, figures and
a status report out. Workflow (``workflow.py``) and experiment runs
differ only in how they build the RunConfig.

For each obs space and simulated variable::

    for each expected cycle:
        cached summary?  -> use it
        diag file found? -> read_ioda -> reduce_cycle -> cache it
        neither          -> gap
    stack_cycles -> plot_obs_space

Failure policy (docs/driver-redesign-plan.md): missing or unreadable data
never stops the run. A cycle that can't be read is a gap; an obs space that
fails is marked ``failed`` with the reason and the others continue. Only
configuration errors raise, and they are raised when the RunConfig is built,
before any work.
"""

from __future__ import annotations

import json
import logging
import shutil
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from obs_monitor.config import FigureSpec, ObsSpaceConfig, RunConfig, load_default_figures
from obs_monitor.io import list_simulated_variables, read_ioda
from obs_monitor.io.catalog import Inventory, build_inventory
from obs_monitor.io.timewindow import format_cycle
from obs_monitor.plotting.summary_figures import plot_obs_space
from obs_monitor.stats import load_regions, read_summary, reduce_cycle, stack_cycles, write_summary

logger = logging.getLogger(__name__)

STATUS_FILE = "obsmon_status.json"


@dataclass
class ObsSpaceStatus:
    """
    Outcome for one obs space. ``status``:

    * ``ok``: data for every cycle, no figure failed (figures may be *skipped*,
      e.g. per-channel figures not implemented yet; see ``figures_skipped``)
    * ``partial``: some cycles missing/unreadable, or some figures failed
    * ``no_data``: nothing for any cycle in the window
    * ``failed``: an error stopped this obs space, or every figure failed
    """

    obs_space: str
    status: str = "ok"
    variables: list[str] = field(default_factory=list)
    cycles_with_data: int = 0
    cycles_expected: int = 0
    missing_cycles: list[str] = field(default_factory=list)
    unreadable_cycles: dict[str, str] = field(default_factory=dict)     # cycle -> error
    figures_written: int = 0
    figures_failed: list[str] = field(default_factory=list)
    figures_skipped: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class RunResult:
    cycles: list[str]
    output_dir: str
    obs_spaces: list[ObsSpaceStatus]

    @property
    def figures_written(self) -> int:
        return sum(s.figures_written for s in self.obs_spaces)

    def summary_line(self) -> str:
        counts: dict[str, int] = {}
        for s in self.obs_spaces:
            counts[s.status] = counts.get(s.status, 0) + 1
        parts = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        return f"window {self.cycles[0]}-{self.cycles[-1]}: {parts}; {self.figures_written} figures"

    def to_dict(self) -> dict:
        return {"cycles": self.cycles, "output_dir": self.output_dir,
                "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "summary": self.summary_line(),
                "obs_spaces": [asdict(s) for s in self.obs_spaces]}


def _summaries_for_variable(rc: RunConfig, obs: ObsSpaceConfig, variable: str, inv: Inventory,
                            domains, grid, status: ObsSpaceStatus) -> dict[datetime, object]:
    """Cached or freshly computed summary per cycle; unreadable cycles recorded and left out."""
    out = {}
    for cycle in rc.cycles:
        cache = rc.summary_path(obs, variable, cycle)
        s = read_summary(cache)
        if s is None:
            path = inv.path(obs.name, cycle)
            if path is None:
                continue
            try:
                ds = read_ioda(path, variable, obs_space=obs.name, channels=obs.channels, group_map=obs.group_map)
                s = reduce_cycle(ds, cycle, domains, grid)
            except Exception as exc:  # noqa: BLE001 - a bad file is a gap, not a crash
                logger.warning("%s %s %s: could not read/reduce %s: %s", obs.name, variable,
                               format_cycle(cycle), path, exc)
                status.unreadable_cycles[format_cycle(cycle)] = f"{type(exc).__name__}: {exc}"
                continue
            try:
                write_summary(s, cache)
            except OSError as exc:
                logger.warning("Could not cache summary %s: %s", cache, exc)
        out[cycle] = s
    return out


def _run_obs_space(rc: RunConfig, obs: ObsSpaceConfig, inv: Inventory, domains, grid,
                   default_figures: Sequence[FigureSpec]) -> ObsSpaceStatus:
    status = ObsSpaceStatus(obs.name, cycles_expected=len(rc.cycles))
    variables = list(obs.variables or [])
    if not variables:
        first = next((inv.path(obs.name, c) for c in reversed(rc.cycles) if inv.path(obs.name, c)), None)
        if first is None:
            status.status = "no_data"
            status.missing_cycles = [format_cycle(c) for c in rc.cycles]
            return status
        variables = list_simulated_variables(first)
    status.variables = variables

    have: set[datetime] = set()
    for variable in variables:
        summaries = _summaries_for_variable(rc, obs, variable, inv, domains, grid, status)
        have |= set(summaries)
        result = plot_obs_space(stack_cycles(summaries, rc.cycles), obs.label,
                                obs.figures or default_figures, rc.output_dir)
        status.figures_written += len(result.written)
        status.figures_failed += [f"{variable}: {d}: {e}" for d, e in result.failed]
        status.figures_skipped += [f"{variable}: {d}: {e}" for d, e in result.skipped]

    status.cycles_with_data = len(have)
    status.missing_cycles = [format_cycle(c) for c in rc.cycles if c not in have]
    if not have:
        status.status = "no_data"
    elif status.figures_written == 0 and status.figures_failed:
        status.status = "failed"
        status.error = "no figures could be written"
    elif status.missing_cycles or status.figures_failed:
        status.status = "partial"
    return status


def run_window(rc: RunConfig, *, default_figures: Sequence[FigureSpec] | None = None,
               write_status: bool = True) -> RunResult:
    """
    Make every figure for every obs space in ``rc`` and (by default) write
    ``obsmon_status.json`` to ``rc.output_dir``. Never raises for data problems.
    """
    domains, grid = load_regions()
    default_figures = default_figures or load_default_figures()
    rc.output_dir.mkdir(parents=True, exist_ok=True)
    inv = build_inventory(rc.locators, list(rc.cycles), rc.obs_space_names)

    statuses = []
    for obs in rc.obs_spaces:
        try:
            st = _run_obs_space(rc, obs, inv, domains, grid, default_figures)
        except Exception as exc:  # noqa: BLE001 - isolate obs spaces from each other
            logger.error("%s failed:\n%s", obs.name, traceback.format_exc())
            st = ObsSpaceStatus(obs.name, status="failed", cycles_expected=len(rc.cycles),
                                error=f"{type(exc).__name__}: {exc}")
        logger.info("%s: %s (%d/%d cycles, %d figures)", obs.name, st.status, st.cycles_with_data,
                    st.cycles_expected, st.figures_written)
        statuses.append(st)

    result = RunResult([format_cycle(c) for c in rc.cycles], str(rc.output_dir), statuses)
    logger.info(result.summary_line())
    if write_status:
        path = rc.output_dir / STATUS_FILE
        path.write_text(json.dumps(result.to_dict(), indent=2))
        logger.info("Status written to %s", path)
    extracted = rc.work_dir / "diags"           # what ComTarballLocator writes; never the user's work_dir itself
    if not rc.keep_work and extracted.exists():
        shutil.rmtree(extracted, ignore_errors=True)
    return result
