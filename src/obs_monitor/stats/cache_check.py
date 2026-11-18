"""
obs_monitor.stats.cache_check
=============================

Decide whether a cached summary can be reused: only when it would come out
the same if computed again. Every summary written to the cache carries a
cache key, stored as these attributes:

``obsmon_summary_version``
    :data:`~obs_monitor.stats.summary.SUMMARY_VERSION`: which version of the
    statistics code made it. Bumped whenever the summary contents or
    definitions change (new fields, QC class rules, binning, ...).
``obsmon_config_hash``
    A short hash of the configuration that affects the numbers for this obs
    space and variable: its ``channels`` and ``group_map``, and the domains
    and grid from ``regions.yaml``. Figure settings and ``web_name`` are not
    included: they don't change the numbers.
``obsmon_source_name``, ``obsmon_source_size``, ``obsmon_source_mtime``
    The diag file it was computed from (file name, bytes, modification time
    in whole seconds). The folder is left out on purpose, so the same file
    extracted to a different scratch folder still matches.

:func:`check` compares a cached summary with what this run expects and
returns why it can't be reused, or ``None`` if it can. The source is only
compared when this run has the diag file. Once the diag file has been
cleaned up, the summary is all there is, and it is used as long as the
version and config match.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import xarray as xr

from obs_monitor.stats.regions import Domain, Grid
from obs_monitor.stats.summary import SUMMARY_VERSION

if TYPE_CHECKING:
    from obs_monitor.config import ObsSpaceConfig

VERSION_ATTR = "obsmon_summary_version"
CONFIG_ATTR = "obsmon_config_hash"
SOURCE_ATTRS = ("obsmon_source_name", "obsmon_source_size", "obsmon_source_mtime")
ATTRS = (VERSION_ATTR, CONFIG_ATTR) + SOURCE_ATTRS


@dataclass(frozen=True)
class SourceFingerprint:
    """A diag file, as far as reuse is concerned: same name, size and modification time."""
    name: str
    size: int
    mtime: int

    @classmethod
    def of(cls, path: str | Path) -> "SourceFingerprint":
        st = Path(path).stat()
        return cls(Path(path).name, int(st.st_size), int(st.st_mtime))


@dataclass(frozen=True)
class CacheKey:
    """How a summary was made: statistics version, config hash and (if known) the diag file."""
    version: int
    config_hash: str
    source: SourceFingerprint | None = None

    def attrs(self) -> dict:
        out = {VERSION_ATTR: self.version, CONFIG_ATTR: self.config_hash}
        if self.source is not None:
            out.update(zip(SOURCE_ATTRS, (self.source.name, self.source.size, self.source.mtime)))
        return out


def config_hash(obs: "ObsSpaceConfig", variable: str, domains: Sequence[Domain], grid: Grid) -> str:
    """Short hash of everything in config that changes the numbers for (obs space, variable)."""
    desc = {
        "obs_space": obs.name,
        "variable": variable,
        "channels": list(obs.channels) if obs.channels else None,
        "group_map": dict(sorted((obs.group_map or {}).items())),
        "domains": [[d.name, float(d.lat_min), float(d.lat_max), float(d.lon_min), float(d.lon_max)]
                    for d in domains],
        "grid": [[round(float(x), 6) for x in grid.lat_edges], [round(float(x), 6) for x in grid.lon_edges]],
    }
    return hashlib.sha256(json.dumps(desc, sort_keys=True).encode()).hexdigest()[:16]


def expected(obs: "ObsSpaceConfig", variable: str, domains: Sequence[Domain], grid: Grid,
             diag_path: str | Path | None) -> CacheKey:
    """What a summary made by this run, from ``diag_path`` (if it has one), would carry."""
    source = SourceFingerprint.of(diag_path) if diag_path is not None else None
    return CacheKey(SUMMARY_VERSION, config_hash(obs, variable, domains, grid), source)


def check(ds: xr.Dataset, want: CacheKey) -> str | None:
    """``None`` if ``ds`` can be reused, otherwise the reason it can't (for logs and the status file)."""
    attrs = ds.attrs
    if VERSION_ATTR not in attrs or CONFIG_ATTR not in attrs:
        return "made by an older obs-monitor (no cache key)"
    try:
        version = int(attrs[VERSION_ATTR])
    except (TypeError, ValueError):
        return f"unreadable summary version {attrs[VERSION_ATTR]!r}"
    if version != want.version:
        return f"summary version {version}, current {want.version}"
    if str(attrs[CONFIG_ATTR]) != want.config_hash:
        return "obs-space or region config changed"
    if want.source is not None:
        try:
            have = SourceFingerprint(str(attrs[SOURCE_ATTRS[0]]), int(attrs[SOURCE_ATTRS[1]]),
                                     int(attrs[SOURCE_ATTRS[2]]))
        except (KeyError, TypeError, ValueError):
            return "no diag file recorded"
        if have != want.source:
            return "diag file changed"
    return None
