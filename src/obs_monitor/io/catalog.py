"""
obs_monitor.io.catalog
======================

Find the IODA diag file for each (obs space, cycle). Nothing here opens a
diag file; that is :mod:`obs_monitor.io.ioda`'s job.

A locator answers one question: for this cycle, where are the diag files
for these obs spaces?  Two are provided:

:class:`ComTarballLocator`
    global-workflow COM layout, where each component's diag files for a cycle
    are bundled in one tarball::

        {comroot}/{run}.YYYYMMDD/HH/analysis/{component}/
            {run}.tHHz.{component}_analysis.ioda_hofx.tar.gz
                diag_{obs_space}_YYYYMMDDHH.nc

    Only the requested members are extracted, in one pass over the tarball,
    into ``{work_dir}/{YYYYMMDDHH}/``.

:class:`GlobLocator`
    Plain files on disk described by a path template, e.g. an experiment
    directory: ``"/path/to/expt/{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"``.

:func:`build_inventory` runs a locator over every cycle and records what was
found, what is missing and why.
"""

from __future__ import annotations

import logging
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from obs_monitor.io.timewindow import format_cycle

logger = logging.getLogger(__name__)

DEFAULT_TARBALL_TEMPLATE = (
    "{comroot}/{run}.{cycle:%Y%m%d}/{cycle:%H}/analysis/{component}/"
    "{run}.t{cycle:%H}z.{component}_analysis.ioda_hofx.tar.gz"
)
DEFAULT_MEMBER_TEMPLATE = "diag_{obs_space}_{cycle:%Y%m%d%H}.nc"

_OBS_SPACE_TOKEN = "\x00OBS_SPACE\x00"


class CatalogError(RuntimeError):
    """A locator is misconfigured (not: a file is missing; that is recorded, not raised)."""


# ---------------------------------------------------------------------------
# Locator interface
# ---------------------------------------------------------------------------

class Locator(Protocol):
    def locate(self, cycle: datetime, obs_spaces: Sequence[str] | None = None) -> dict[str, Path]:
        """Return ``{obs_space: path}`` for the requested obs spaces found at
        ``cycle`` (all available ones if ``obs_spaces`` is None). Missing obs
        spaces are simply absent from the result."""


def _check_template(template: str, required: Iterable[str]) -> None:
    for name in required:
        if "{" + name not in template:
            raise CatalogError(f"Template '{template}' must contain '{{{name}...}}'.")


def _template_regex(template: str, cycle: datetime, **fixed) -> re.Pattern:
    """Regex matching a formatted template, capturing ``obs_space``."""
    probe = template.format(cycle=cycle, obs_space=_OBS_SPACE_TOKEN, **fixed)
    head, _, tail = probe.partition(_OBS_SPACE_TOKEN)
    if _OBS_SPACE_TOKEN in tail:
        # obs_space appears more than once (e.g. in a directory and the file name)
        rest = re.escape(tail).replace(re.escape(_OBS_SPACE_TOKEN), r"(?P=obs_space)")
    else:
        rest = re.escape(tail)
    return re.compile("^" + re.escape(head) + r"(?P<obs_space>[A-Za-z0-9_.\-]+?)" + rest + "$")


# ---------------------------------------------------------------------------
# GlobLocator: files already on disk
# ---------------------------------------------------------------------------

class GlobLocator:
    """
    Files on disk described by a path template with ``{obs_space}`` and
    ``{cycle:<strftime>}`` fields.

    >>> loc = GlobLocator("/scratch/expt/diags/diag_{obs_space}_{cycle:%Y%m%d%H}.nc")
    >>> loc.locate(datetime(2026, 10, 1, 0), ["prepbufr_adpsfc"])
    {'prepbufr_adpsfc': PosixPath('/scratch/expt/diags/diag_prepbufr_adpsfc_2026100100.nc')}
    """

    def __init__(self, template: str) -> None:
        _check_template(template, ["obs_space", "cycle"])
        if not Path(template.split("{", 1)[0] or "x").is_absolute():
            raise CatalogError(f"GlobLocator template must be an absolute path: '{template}'.")
        self.template = template

    def __repr__(self) -> str:
        return f"GlobLocator({self.template!r})"

    def locate(self, cycle: datetime, obs_spaces: Sequence[str] | None = None) -> dict[str, Path]:
        if obs_spaces is not None:
            found = {}
            for name in obs_spaces:
                p = Path(self.template.format(cycle=cycle, obs_space=name))
                if p.is_file():
                    found[name] = p
            return found

        rx = _template_regex(self.template, cycle)
        pattern = self.template.format(cycle=cycle, obs_space="*")
        root = Path("/")
        found = {}
        for p in sorted(root.glob(pattern.lstrip("/"))):
            m = rx.match(str(p))
            if m and p.is_file():
                found[m.group("obs_space")] = p
        return found


# ---------------------------------------------------------------------------
# ComTarballLocator: global-workflow COM tarballs
# ---------------------------------------------------------------------------

class ComTarballLocator:
    """
    Diag files inside per-cycle COM tarballs. Requested members are extracted
    to ``{work_dir}/{YYYYMMDDHH}/<member name>``; an already-extracted file of
    the same size is reused, so re-running a cycle does not re-extract.

    The tarball is read as a stream (gzip can't seek), so all members needed
    for a cycle are extracted in a single pass.
    """

    def __init__(
        self,
        comroot: str | Path,
        work_dir: str | Path,
        component: str,
        run: str = "gdas",
        tarball_template: str = DEFAULT_TARBALL_TEMPLATE,
        member_template: str = DEFAULT_MEMBER_TEMPLATE,
    ) -> None:
        self.comroot = Path(comroot)
        self.work_dir = Path(work_dir)
        for label, p in (("comroot", self.comroot), ("work_dir", self.work_dir)):
            if not p.is_absolute():
                raise CatalogError(f"{label} must be an absolute path, got '{p}'.")
        _check_template(tarball_template, ["cycle"])
        _check_template(member_template, ["obs_space", "cycle"])
        if "/" in member_template:
            raise CatalogError("member_template is a file name inside the tarball and must not contain '/'.")
        self.component = component
        self.run = run
        self.tarball_template = tarball_template
        self.member_template = member_template

    def __repr__(self) -> str:
        return f"ComTarballLocator(comroot={str(self.comroot)!r}, component={self.component!r}, run={self.run!r})"

    def tarball(self, cycle: datetime) -> Path:
        return Path(self.tarball_template.format(
            comroot=self.comroot, run=self.run, component=self.component, cycle=cycle))

    def _member_name(self, cycle: datetime, obs_space: str) -> str:
        return self.member_template.format(cycle=cycle, obs_space=obs_space)

    def locate(self, cycle: datetime, obs_spaces: Sequence[str] | None = None) -> dict[str, Path]:
        tar_path = self.tarball(cycle)
        if not tar_path.is_file():
            logger.warning("No tarball for %s: %s", format_cycle(cycle), tar_path)
            return {}

        out_dir = self.work_dir / format_cycle(cycle)
        member_rx = _template_regex(self.member_template, cycle)
        wanted = None if obs_spaces is None else {self._member_name(cycle, s): s for s in obs_spaces}
        found: dict[str, Path] = {}

        try:
            with tarfile.open(tar_path, "r:*") as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    name = Path(member.name).name          # ignore any directory part in the archive
                    if member.name.startswith("/") or ".." in Path(member.name).parts:
                        logger.warning("Skipping unsafe tar member '%s' in %s", member.name, tar_path.name)
                        continue
                    if wanted is not None:
                        obs_space = wanted.get(name)
                    else:
                        m = member_rx.match(name)
                        obs_space = m.group("obs_space") if m else None
                    if obs_space is None:
                        continue
                    dest = out_dir / name
                    if not (dest.is_file() and dest.stat().st_size == member.size):
                        out_dir.mkdir(parents=True, exist_ok=True)
                        src = tar.extractfile(member)
                        tmp = dest.with_suffix(dest.suffix + ".part")
                        with src, open(tmp, "wb") as fh:
                            shutil.copyfileobj(src, fh, length=8 << 20)
                        tmp.replace(dest)
                    found[obs_space] = dest
                    if wanted is not None and len(found) == len(wanted):
                        break                                # everything requested is out; stop reading
        except (tarfile.TarError, OSError, EOFError) as exc:
            logger.error("Could not read %s: %s", tar_path, exc)
            return {}

        return found


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@dataclass
class Inventory:
    """What was found for every (obs space, cycle)."""

    cycles: list[datetime]
    obs_spaces: list[str]
    files: dict[str, dict[datetime, Path]] = field(default_factory=dict)

    def path(self, obs_space: str, cycle: datetime) -> Path | None:
        return self.files.get(obs_space, {}).get(cycle)

    def found_cycles(self, obs_space: str) -> list[datetime]:
        return sorted(self.files.get(obs_space, {}))

    def missing_cycles(self, obs_space: str) -> list[datetime]:
        have = self.files.get(obs_space, {})
        return [c for c in self.cycles if c not in have]

    def coverage(self, obs_space: str) -> float:
        return len(self.files.get(obs_space, {})) / len(self.cycles) if self.cycles else 0.0

    def summary(self) -> list[dict]:
        """One row per obs space, for logs or a status JSON."""
        return [
            {
                "obs_space": s,
                "found": len(self.files.get(s, {})),
                "expected": len(self.cycles),
                "missing": [format_cycle(c) for c in self.missing_cycles(s)],
            }
            for s in self.obs_spaces
        ]


def build_inventory(
    locators: Mapping[str, Locator] | Locator,
    cycles: Sequence[datetime],
    obs_spaces: Sequence[str],
) -> Inventory:
    """
    Locate every obs space at every cycle.

    ``locators`` is either one locator for all obs spaces, or a mapping
    ``{obs_space: locator}`` (e.g. one :class:`ComTarballLocator` per
    component). Obs spaces sharing a locator are requested together, so a COM
    tarball is read once per cycle.
    """
    if not isinstance(locators, Mapping):
        locators = {s: locators for s in obs_spaces}
    missing_loc = [s for s in obs_spaces if s not in locators]
    if missing_loc:
        raise CatalogError(f"No locator configured for obs space(s): {missing_loc}")

    groups: dict[int, tuple[Locator, list[str]]] = {}
    for s in obs_spaces:
        loc = locators[s]
        groups.setdefault(id(loc), (loc, []))[1].append(s)

    inv = Inventory(cycles=list(cycles), obs_spaces=list(obs_spaces))
    for cycle in inv.cycles:
        for loc, names in groups.values():
            for name, path in loc.locate(cycle, names).items():
                inv.files.setdefault(name, {})[cycle] = path
    for row in inv.summary():
        if row["missing"]:
            logger.warning("%s: %d/%d cycles found; missing %s",
                           row["obs_space"], row["found"], row["expected"], ", ".join(row["missing"]))
        else:
            logger.info("%s: %d/%d cycles found", row["obs_space"], row["found"], row["expected"])
    return inv
