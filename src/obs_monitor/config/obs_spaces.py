"""
obs_monitor.config.obs_spaces
=============================

Obs-space definitions: which diag files obs-monitor knows about and how to
read them. Adding an obs type to monitoring is an entry in a YAML file under
``config/yaml/obs_spaces/``, not Python.

.. code-block:: yaml

    obs_spaces:
      prepbufr_adpsfc:                 # = the <obs_space> in diag_<obs_space>_YYYYMMDDHH.nc
        component: atmos               # COM component whose tarball holds the file (not the obs category)
        variables: [stationPressure]   # optional; default = every simulated variable
      radiance_atms_n20:
        component: atmos
        channels: [1, 2, 3]            # optional; radiance only; default = all
        web_name: atms_n20             # optional; name used in website file names

Files are grouped by obs category (``conventional.yaml``, ``radiance.yaml``,
...); the grouping is for people, the loader reads every ``*.yaml`` in the
directory. Unknown keys are an error, so a typo (``chanels:``) fails loudly
instead of being silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from obs_monitor.io.ioda import FIELDS

#: Directory holding the obs-space YAML files shipped with obs-monitor.
DEFAULT_OBS_SPACE_DIR = Path(__file__).parent / "yaml" / "obs_spaces"


class ConfigError(ValueError):
    """A configuration file or value is invalid."""


@dataclass(frozen=True)
class ObsSpaceConfig:
    name: str
    component: str
    variables: tuple[str, ...] | None = None
    channels: tuple[int, ...] | None = None
    web_name: str | None = None
    group_map: Mapping[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Name used in output file names (the website contract)."""
        return self.web_name or self.name


_ALLOWED_KEYS = {"component", "variables", "channels", "web_name", "group_map"}


def _str_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{where} must be a non-empty list of strings.")
    return tuple(value)


def _parse_obs_space(name: str, spec: Any, source: str) -> ObsSpaceConfig:
    where = f"{source}: obs space '{name}'"
    if not isinstance(spec, dict):
        raise ConfigError(f"{where} must be a mapping.")
    unknown = set(spec) - _ALLOWED_KEYS
    if unknown:
        raise ConfigError(f"{where} has unknown key(s) {sorted(unknown)}. Allowed: {sorted(_ALLOWED_KEYS)}")
    component = spec.get("component")
    if not isinstance(component, str) or not component:
        raise ConfigError(f"{where} needs 'component' (e.g. atmos, chem, snow).")

    variables = None if spec.get("variables") is None else _str_list(spec["variables"], f"{where} 'variables'")

    channels = spec.get("channels")
    if channels is not None:
        if (not isinstance(channels, list) or not channels
                or not all(isinstance(c, int) and not isinstance(c, bool) and c > 0 for c in channels)):
            raise ConfigError(f"{where} 'channels' must be a non-empty list of positive integers.")
        if len(set(channels)) != len(channels):
            raise ConfigError(f"{where} 'channels' has duplicates.")
        channels = tuple(sorted(channels))

    web_name = spec.get("web_name")
    if web_name is not None and (not isinstance(web_name, str) or not web_name):
        raise ConfigError(f"{where} 'web_name' must be a non-empty string.")

    group_map = spec.get("group_map") or {}
    if not isinstance(group_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in group_map.items()):
        raise ConfigError(f"{where} 'group_map' must map field names to IODA group names.")
    bad = set(group_map) - set(FIELDS)
    if bad:
        raise ConfigError(f"{where} 'group_map' has unknown field(s) {sorted(bad)}. Known: {list(FIELDS)}")

    return ObsSpaceConfig(name=name, component=component, variables=variables, channels=channels,
                          web_name=web_name, group_map=dict(group_map))


def load_obs_spaces(paths: str | Path | Iterable[str | Path] = DEFAULT_OBS_SPACE_DIR) -> dict[str, ObsSpaceConfig]:
    """
    Load obs-space definitions from YAML files or directories of ``*.yaml``.

    Raises
    ------
    ConfigError
        Bad YAML, unknown keys, bad values, or the same obs space defined twice.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(p.glob("*.yaml")))
        elif p.is_file():
            files.append(p)
        else:
            raise ConfigError(f"Obs-space config path does not exist: {p}")

    out: dict[str, ObsSpaceConfig] = {}
    defined_in: dict[str, Path] = {}
    for f in files:
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{f}: invalid YAML: {exc}") from exc
        if not isinstance(doc, dict) or set(doc) != {"obs_spaces"} or not isinstance(doc["obs_spaces"], dict):
            raise ConfigError(f"{f}: must contain exactly one top-level key 'obs_spaces' holding a mapping.")
        for name, spec in doc["obs_spaces"].items():
            if name in out:
                raise ConfigError(f"Obs space '{name}' is defined in both {defined_in[name]} and {f}.")
            out[name] = _parse_obs_space(str(name), spec, f.name)
            defined_in[name] = f
    return out
