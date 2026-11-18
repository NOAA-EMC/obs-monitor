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

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

import yaml

from obs_monitor.config.errors import ConfigError

DEFAULT_FIGURES_FILE = Path(__file__).parent / "yaml" / "figures.yaml"

# Mirrors obs_monitor.stats (FIELD_QC, STATS, QC_CLASSES); a test keeps them in step.
FIELDS = ("ombg", "oman", "obs")
STATS = ("count", "mean", "rms", "std")
QC_CLASSES = ("all", "assimilated", "monitored", "rejected")


@dataclass(frozen=True)
class _TypeRules:
    required: frozenset            # keys besides "type"
    optional: frozenset
    stats: tuple = ()              # allowed values of "stat" (if it's a key for this type)
    qcs: tuple = QC_CLASSES        # allowed QC classes
    qc_list: bool = False          # "qc" is a list of classes (one line / colour each)
    defaults: tuple = ()           # (key, value) filled in when absent


_MAP_OPTIONS = {"title", "projection", "map_domain"}

#: Every figure type and its keys. ``latest`` types are drawn from the newest
#: diag file in the window (raw points), the rest from the cycle summaries.
FIGURE_TYPES: dict[str, _TypeRules] = {
    "time_series": _TypeRules(frozenset({"field", "stat", "qc"}), frozenset({"domains", "title", "y_label"}),
                              stats=STATS),
    "map_gridded": _TypeRules(frozenset({"field", "stat", "qc"}),
                              frozenset({"colorbar_label", "cmap", "vmin", "vmax"} | _MAP_OPTIONS),
                              stats=("mean", "count"), qcs=("assimilated",)),
    "count_series": _TypeRules(frozenset({"field"}), frozenset({"qc", "domains", "title", "y_label", "log_scale"}),
                               qc_list=True, defaults=(("qc", list(QC_CLASSES)), ("domains", ["Global"]))),
    "coverage_map": _TypeRules(frozenset(), frozenset({"field", "qc", "marker_size"} | _MAP_OPTIONS),
                               qc_list=True,
                               defaults=(("field", "ombg"), ("qc", ["assimilated"]))),
    "scatter_map": _TypeRules(frozenset({"field", "qc"}),
                              frozenset({"colorbar_label", "cmap", "vmin", "vmax", "marker_size"} | _MAP_OPTIONS)),
}
LATEST_TYPES = frozenset({"coverage_map", "scatter_map"})


@dataclass(frozen=True)
class FigureSpec:
    type: str
    field: str = ""
    stat: str = ""
    qc: str = ""                                    # one class (time_series, map_gridded, scatter_map)
    domains: tuple[str, ...] | None = None          # time_series, count_series; None = all
    options: dict[str, Any] = dc_field(default_factory=dict)   # title, y_label, cmap, ...
    qcs: tuple[str, ...] = ()                       # several classes (count_series, coverage_map)

    @property
    def latest(self) -> bool:
        """Drawn from the newest diag file in the window rather than the summaries."""
        return self.type in LATEST_TYPES


def parse_figure_spec(spec: Any, where: str) -> FigureSpec:
    if not isinstance(spec, dict):
        raise ConfigError(f"{where} must be a mapping.")
    if "type" not in spec:
        raise ConfigError(f"{where} is missing ['type'].")
    ftype = spec["type"]
    if ftype not in FIGURE_TYPES:
        raise ConfigError(f"{where} type must be one of {sorted(FIGURE_TYPES)}, got {ftype!r}.")
    rules = FIGURE_TYPES[ftype]
    missing = rules.required - set(spec)
    if missing:
        raise ConfigError(f"{where} ({ftype}) is missing {sorted(missing)}.")
    unknown = set(spec) - {"type"} - rules.required - rules.optional
    if unknown:
        raise ConfigError(f"{where} ({ftype}) has unknown key(s) {sorted(unknown)}. "
                          f"Allowed: {sorted({'type'} | rules.required | rules.optional)}")
    spec = {**dict(rules.defaults), **spec}

    fld = spec.get("field", "")
    if fld and fld not in FIELDS:
        raise ConfigError(f"{where} field must be one of {list(FIELDS)}, got {fld!r}.")
    stat = spec.get("stat", "count" if ftype == "count_series" else "")
    if rules.stats and stat not in rules.stats:
        raise ConfigError(f"{where} stat for {ftype} must be one of {list(rules.stats)}, got {stat!r}.")

    qc, qcs = "", ()
    if rules.qc_list:
        value = spec["qc"]
        value = [value] if isinstance(value, str) else value
        if not isinstance(value, list) or not value or any(v not in rules.qcs for v in value) \
                or len(set(value)) != len(value):
            raise ConfigError(f"{where} qc for {ftype} must be a list of distinct classes from "
                              f"{list(rules.qcs)}, got {spec['qc']!r}.")
        qcs = tuple(value)
    elif "qc" in spec:
        qc = spec["qc"]
        if qc not in rules.qcs:
            raise ConfigError(f"{where} qc for {ftype} must be one of {list(rules.qcs)}, got {qc!r}.")

    domains = spec.get("domains")
    if domains is not None:
        if not isinstance(domains, list) or not domains or not all(isinstance(d, str) for d in domains):
            raise ConfigError(f"{where} domains must be a non-empty list of domain names.")
        domains = tuple(domains)
    if "marker_size" in spec and not (isinstance(spec["marker_size"], (int, float)) and spec["marker_size"] > 0):
        raise ConfigError(f"{where} marker_size must be a positive number.")
    if "log_scale" in spec and not isinstance(spec["log_scale"], bool):
        raise ConfigError(f"{where} log_scale must be true or false.")
    options = {k: v for k, v in spec.items() if k not in {"type", "field", "stat", "qc", "domains"}}
    return FigureSpec(ftype, fld, stat, qc, domains, options, qcs)


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
