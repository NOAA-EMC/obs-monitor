"""
obs_monitor.config.figures
==========================

Which figures to make, in terms of the summary contract (field / statistic /
QC class), not file layout. Defaults for every obs space live in
``config/yaml/figures.yaml``; an obs space can replace them with its own
``figures:`` list. See that file for the keys.

Domain names are checked when plotting (an unknown domain is skipped with a
warning), since the domain list comes from ``regions.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from obs_monitor.config.errors import ConfigError

DEFAULT_FIGURES_FILE = Path(__file__).parent / "yaml" / "figures.yaml"

# Mirrors obs_monitor.stats (FIELD_QC, STATS, QC_CLASSES); a test keeps them in step.
FIELDS = ("ombg", "oman", "obs")
STATS = ("count", "mean", "rms", "std")
QC_CLASSES = ("all", "assimilated", "monitored", "rejected")

FIGURE_TYPES = {
    # type: (allowed stats, allowed qc classes)
    "time_series": (STATS, QC_CLASSES),
    "map_gridded": (("mean", "count"), ("assimilated",)),
}

_REQUIRED = {"type", "field", "stat", "qc"}
_OPTIONAL = {
    "time_series": {"domains", "title", "y_label"},
    "map_gridded": {"title", "colorbar_label", "cmap", "vmin", "vmax", "projection", "map_domain"},
}


@dataclass(frozen=True)
class FigureSpec:
    type: str
    field: str
    stat: str
    qc: str
    domains: tuple[str, ...] | None = None          # time_series; None = all
    options: dict[str, Any] = field(default_factory=dict)   # title, y_label, cmap, ...


def parse_figure_spec(spec: Any, where: str) -> FigureSpec:
    if not isinstance(spec, dict):
        raise ConfigError(f"{where} must be a mapping.")
    missing = _REQUIRED - set(spec)
    if missing:
        raise ConfigError(f"{where} is missing {sorted(missing)}.")
    ftype = spec["type"]
    if ftype not in FIGURE_TYPES:
        raise ConfigError(f"{where} type must be one of {sorted(FIGURE_TYPES)}, got {ftype!r}.")
    allowed_stats, allowed_qc = FIGURE_TYPES[ftype]
    unknown = set(spec) - _REQUIRED - _OPTIONAL[ftype]
    if unknown:
        raise ConfigError(f"{where} ({ftype}) has unknown key(s) {sorted(unknown)}. "
                          f"Allowed: {sorted(_REQUIRED | _OPTIONAL[ftype])}")
    if spec["field"] not in FIELDS:
        raise ConfigError(f"{where} field must be one of {list(FIELDS)}, got {spec['field']!r}.")
    if spec["stat"] not in allowed_stats:
        raise ConfigError(f"{where} stat for {ftype} must be one of {list(allowed_stats)}, got {spec['stat']!r}.")
    if spec["qc"] not in allowed_qc:
        raise ConfigError(f"{where} qc for {ftype} must be one of {list(allowed_qc)}, got {spec['qc']!r}.")

    domains = spec.get("domains")
    if domains is not None:
        if not isinstance(domains, list) or not domains or not all(isinstance(d, str) for d in domains):
            raise ConfigError(f"{where} domains must be a non-empty list of domain names.")
        domains = tuple(domains)
    options = {k: v for k, v in spec.items() if k not in _REQUIRED | {"domains"}}
    return FigureSpec(ftype, spec["field"], spec["stat"], spec["qc"], domains, options)


def parse_figure_specs(specs: Any, where: str) -> tuple[FigureSpec, ...]:
    if not isinstance(specs, list) or not specs:
        raise ConfigError(f"{where} must be a non-empty list of figure specs.")
    return tuple(parse_figure_spec(s, f"{where}[{i}]") for i, s in enumerate(specs))


def load_default_figures(path: str | Path = DEFAULT_FIGURES_FILE) -> tuple[FigureSpec, ...]:
    """The figure list used for obs spaces that don't define their own."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Figures file not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"defaults"}:
        raise ConfigError(f"{path}: must contain exactly one top-level key 'defaults'.")
    return parse_figure_specs(doc["defaults"], f"{path.name}: defaults")
