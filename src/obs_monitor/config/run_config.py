"""
obs_monitor.config.run_config
=============================

:class:`RunConfig` is everything one obs-monitor run needs: which cycles,
which obs spaces, where the diag files are, and where output goes. It is
plain data: it never reads environment variables. Front doors build it:

* experiment runs: :func:`load_run_config` from a YAML file
* operational runs: the Rocoto/global-workflow job builds the same dict from
  its settings and calls :meth:`RunConfig.from_dict` (later PR)

Run YAML
--------
.. code-block:: yaml

    cycles:                       # either start/end ...
      start: 2026093000
      end: 2026100118
      interval_hours: 6
    # cycles: {end: 2026100118, n_cycles: 4, interval_hours: 6}   # ... or a trailing window

    source:
      type: com                   # global-workflow COM tarballs
      comroot: /scratch3/NCEPDEV/da/$USER/obsmon_data/prjedi
      run: gdas                   # optional, default gdas
    # source:
    #   type: glob                # plain files on disk; {component} optional
    #   template: /path/expt/diag_{obs_space}_{cycle:%Y%m%d%H}.nc

    obs_spaces: all               # or a list of names
    output_dir: /scratch3/NCEPDEV/da/$USER/obsmon_out
    work_dir: /scratch3/NCEPDEV/da/$USER/obsmon_work
    keep_work: false              # optional
    summary_template: /path/{obs_space}/summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc
                                  # optional; where per-cycle summaries are cached
                                  # (default: <output_dir>/summaries/...); {component} optional

Paths may use ``~`` and ``$VARS``; after expansion they must be absolute.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from obs_monitor.io.catalog import (
    DEFAULT_MEMBER_TEMPLATE,
    DEFAULT_TARBALL_TEMPLATE,
    ComTarballLocator,
    GlobLocator,
    Locator,
)
from obs_monitor.io.timewindow import CycleError, cycle_range, trailing_window
from .errors import ConfigError
from .obs_spaces import DEFAULT_OBS_SPACE_DIR, ObsSpaceConfig, load_obs_spaces

_TOP_KEYS = {"cycles", "source", "obs_spaces", "obs_space_config", "output_dir", "work_dir", "keep_work",
             "summary_template"}
_REQUIRED = {"cycles", "source", "obs_spaces", "output_dir", "work_dir"}

DEFAULT_SUMMARY_TEMPLATE = \
    "{output_dir}/summaries/{obs_space}/{variable}/summary_{obs_space}_{variable}_{cycle:%Y%m%d%H}.nc"


@dataclass(frozen=True)
class RunConfig:
    cycles: tuple[datetime, ...]
    obs_spaces: tuple[ObsSpaceConfig, ...]
    locators: Mapping[str, Locator]          # obs space name -> locator
    output_dir: Path
    work_dir: Path
    keep_work: bool = False
    summary_template: str = ""      # set by from_dict; see summary_path

    @property
    def obs_space_names(self) -> list[str]:
        return [o.name for o in self.obs_spaces]

    def summary_path(self, obs_space: ObsSpaceConfig, variable: str, cycle: datetime) -> Path:
        """Where the cached summary for (obs space, variable, cycle) lives."""
        template = self.summary_template or DEFAULT_SUMMARY_TEMPLATE.replace("{output_dir}", str(self.output_dir))
        return Path(template.format(obs_space=obs_space.name, variable=variable, cycle=cycle,
                                    component=obs_space.component))

    @classmethod
    def from_dict(cls, cfg: Mapping[str, Any], source_name: str = "run config") -> "RunConfig":
        if not isinstance(cfg, Mapping):
            raise ConfigError(f"{source_name}: must be a mapping.")
        unknown = set(cfg) - _TOP_KEYS
        if unknown:
            raise ConfigError(f"{source_name}: unknown key(s) {sorted(unknown)}. Allowed: {sorted(_TOP_KEYS)}")
        missing = _REQUIRED - set(cfg)
        if missing:
            raise ConfigError(f"{source_name}: missing required key(s) {sorted(missing)}.")

        cycles = _parse_cycles(cfg["cycles"], source_name)
        output_dir = _abs_path(cfg["output_dir"], "output_dir", source_name)
        work_dir = _abs_path(cfg["work_dir"], "work_dir", source_name)

        keep_work = cfg.get("keep_work", False)
        if not isinstance(keep_work, bool):
            raise ConfigError(f"{source_name}: keep_work must be true or false.")

        extra = cfg.get("obs_space_config")
        config_paths = [DEFAULT_OBS_SPACE_DIR]
        if extra is not None:
            extra = extra if isinstance(extra, list) else [extra]
            config_paths += [_abs_path(p, "obs_space_config", source_name) for p in extra]
        known = load_obs_spaces(config_paths)
        obs_spaces = _select_obs_spaces(cfg["obs_spaces"], known, source_name)

        locators = _build_locators(cfg["source"], obs_spaces, work_dir, source_name)

        summary_template = ""
        if cfg.get("summary_template") is not None:
            summary_template = _template(cfg["summary_template"], "summary_template", source_name,
                                         required=("{obs_space}", "{variable}", "{cycle"))
        return cls(cycles=tuple(cycles), obs_spaces=tuple(obs_spaces), locators=locators,
                   output_dir=output_dir, work_dir=work_dir, keep_work=keep_work,
                   summary_template=summary_template)


def load_run_config(path: str | Path) -> RunConfig:
    """Load and validate a run YAML (see module docstring)."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Run config not found: {path}")
    try:
        cfg = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    return RunConfig.from_dict(cfg, source_name=str(path))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _abs_path(value: Any, key: str, source_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{source_name}: {key} must be a path string.")
    expanded = os.path.expandvars(os.path.expanduser(value))
    if "$" in expanded:
        raise ConfigError(f"{source_name}: {key} '{value}' has an unset environment variable.")
    p = Path(expanded)
    if not p.is_absolute():
        raise ConfigError(f"{source_name}: {key} must be an absolute path, got '{value}'.")
    return p


def _template(value: Any, key: str, source_name: str, required: tuple[str, ...]) -> str:
    """An absolute path template containing every placeholder in ``required``; ~ and $VARS expanded."""
    if not isinstance(value, str) or not all(r in value for r in required):
        raise ConfigError(f"{source_name}: {key} must be a path template containing {' and '.join(required)}.")
    _abs_path(value.split("{", 1)[0] or "x", key, source_name)
    return os.path.expandvars(os.path.expanduser(value))


def _parse_cycles(spec: Any, source_name: str) -> list[datetime]:
    where = f"{source_name}: cycles"
    if not isinstance(spec, Mapping):
        raise ConfigError(f"{where} must be a mapping with start/end or end/n_cycles.")
    interval = spec.get("interval_hours", 6)
    keys = set(spec) - {"interval_hours"}
    try:
        if keys == {"start", "end"}:
            return cycle_range(spec["start"], spec["end"], interval)
        if keys == {"end", "n_cycles"}:
            return trailing_window(spec["end"], spec["n_cycles"], interval)
    except CycleError as exc:
        raise ConfigError(f"{where}: {exc}") from exc
    raise ConfigError(f"{where} must have either start+end or end+n_cycles (plus optional interval_hours); "
                      f"got {sorted(spec)}.")


def _select_obs_spaces(spec: Any, known: Mapping[str, ObsSpaceConfig], source_name: str) -> list[ObsSpaceConfig]:
    if spec == "all":
        return list(known.values())
    if not isinstance(spec, list) or not spec or not all(isinstance(s, str) for s in spec):
        raise ConfigError(f"{source_name}: obs_spaces must be 'all' or a list of obs space names.")
    unknown = [s for s in spec if s not in known]
    if unknown:
        raise ConfigError(f"{source_name}: unknown obs space(s) {unknown}. Known: {sorted(known)}")
    if len(set(spec)) != len(spec):
        raise ConfigError(f"{source_name}: obs_spaces lists a name more than once.")
    return [known[s] for s in spec]


def _build_locators(spec: Any, obs_spaces: list[ObsSpaceConfig], work_dir: Path,
                    source_name: str) -> dict[str, Locator]:
    where = f"{source_name}: source"
    if not isinstance(spec, Mapping) or "type" not in spec:
        raise ConfigError(f"{where} must be a mapping with a 'type' (com or glob).")
    kind = spec["type"]

    if kind == "glob":
        if set(spec) != {"type", "template"}:
            raise ConfigError(f"{where} (glob) takes exactly 'type' and 'template'.")
        template = spec["template"]
        if not isinstance(template, str) or "{obs_space}" not in template or "{cycle" not in template:
            raise ConfigError(f"{where} (glob) template must be a string containing {{obs_space}} and {{cycle:...}}.")
        _abs_path(template.split("{", 1)[0] or "x", "source.template", source_name)
        template = os.path.expandvars(os.path.expanduser(template))
        # {component} is filled per obs space, so one template can cover several components
        per_component = {c: GlobLocator(template.replace("{component}", c)) for c in {o.component for o in obs_spaces}}
        return {o.name: per_component[o.component] for o in obs_spaces}

    if kind == "com":
        allowed = {"type", "comroot", "run", "tarball_template", "member_template"}
        unknown = set(spec) - allowed
        if unknown:
            raise ConfigError(f"{where} (com) has unknown key(s) {sorted(unknown)}. Allowed: {sorted(allowed)}")
        if "comroot" not in spec:
            raise ConfigError(f"{where} (com) needs 'comroot'.")
        comroot = _abs_path(spec["comroot"], "source.comroot", source_name)
        per_component: dict[str, ComTarballLocator] = {}
        for o in obs_spaces:
            if o.component not in per_component:
                per_component[o.component] = ComTarballLocator(
                    comroot=comroot,
                    work_dir=work_dir / "diags",
                    component=o.component,
                    run=spec.get("run", "gdas"),
                    tarball_template=spec.get("tarball_template", DEFAULT_TARBALL_TEMPLATE),
                    member_template=spec.get("member_template", DEFAULT_MEMBER_TEMPLATE),
                )
        return {o.name: per_component[o.component] for o in obs_spaces}

    raise ConfigError(f"{where} type must be 'com' or 'glob', got {kind!r}.")
