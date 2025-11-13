#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import re
from glob import glob
from pathlib import Path
from typing import Any, Dict, List

import yaml

# ---------------- Paths ----------------
ROOT = Path(__file__).parent.resolve()
CFG  = ROOT / "config"
FIGS = ROOT / "figures"

# -------------- YAML IO ---------------
def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text())

# ----------- Deep utilities -----------
def deep_merge(a: Any, b: Any) -> Any:
    """Return deep-merged copy of a overlaid with b."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return copy.deepcopy(b)
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out

# Jinja-safe formatter: don't format strings that contain {{ or }}
_JINJA_BRACE_RE = re.compile(r"{{|}}")

def _format_ok(s: str) -> bool:
    return _JINJA_BRACE_RE.search(s) is None

def deep_format_jinja_safe(obj: Any, params: Dict[str, Any]) -> Any:
    """Recursively apply str.format(**params) to strings that do NOT contain Jinja {{ }}."""
    if isinstance(obj, str):
        if _format_ok(obj):
            try:
                return obj.format(**params)
            except KeyError:
                # Leave unresolved placeholders for a later pass (e.g., layer_template expansion)
                return obj
        return obj
    elif isinstance(obj, list):
        return [deep_format_jinja_safe(x, params) for x in obj]
    elif isinstance(obj, dict):
        return {k: deep_format_jinja_safe(v, params) for k, v in obj.items()}
    else:
        return obj

def resolve_param_placeholders(params: Dict[str, Any]) -> Dict[str, Any]:
    """Format string params once using the same dict, skipping Jinja strings."""
    def fmt_one(v: Any) -> Any:
        if isinstance(v, str) and _format_ok(v):
            try:
                return v.format(**params)
            except KeyError:
                return v
        return v
    return {k: fmt_one(v) for k, v in params.items()}

# --------- Token replacement ----------
TOKEN_MAP = {
    "[[runtime_dir]]": "{{ runtime_dir }}",
    "[[variable]]": "{{ variable }}",
    "[[start_YMDH]]": "{{ start_time | to_YMDH }}",
    "[[end_YMDH]]": "{{ end_time | to_YMDH }}",
    "[[sensor]]": "{{ sensor }}",
    "[[satellite]]": "{{ satellite }}",
}

def replace_tokens(obj: Any) -> Any:
    """Convert [[tokens]] → EVA-time Jinja {{ ... }} at the very end."""
    if isinstance(obj, str):
        s = obj
        for k, v in TOKEN_MAP.items():
            s = s.replace(k, v)
        return s
    if isinstance(obj, list):
        return [replace_tokens(x) for x in obj]
    if isinstance(obj, dict):
        return {k: replace_tokens(v) for k, v in obj.items()}
    return obj

# ---- Pretty YAML without hard-coding ----
class FlowList(list):
    """List that dumps as a flow-style sequence, e.g. [1,1]."""

def _represent_flow_list(dumper, data):
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

def _represent_none_as_empty(dumper, _):
    # Render None as an empty scalar -> "key:" instead of "key: null"
    return dumper.represent_scalar('tag:yaml.org,2002:null', '')

yaml.add_representer(FlowList, _represent_flow_list, Dumper=yaml.SafeDumper)
yaml.add_representer(type(None), _represent_none_as_empty, Dumper=yaml.SafeDumper)

NUMERIC_KEYS = {"markersize", "linewidth", "alpha"}

def convert_numeric_scalars(obj):
    """Turn numeric-looking strings on known keys into numbers."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in NUMERIC_KEYS and isinstance(v, str):
                try:
                    obj[k] = int(v) if v.isdigit() else float(v)
                except ValueError:
                    pass
            else:
                convert_numeric_scalars(v)
    elif isinstance(obj, list):
        for v in obj:
            convert_numeric_scalars(v)
    return obj

OPTIONAL_STYLE_KEYS = {"vmin", "vmax", "norm"}  # extend if needed

def prune_optional_style(obj: Any) -> Any:
    """
    Remove optional style keys (vmin, vmax, norm, etc.) when they are effectively unset.
    Criteria:
      - value is None
      - value is empty string
      - value is a placeholder string like "{vmin}" that never got resolved
    Preserve FlowList so flow-style sequences (e.g., [1,1]) survive.
    """
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            v_clean = prune_optional_style(v)
            if k in OPTIONAL_STYLE_KEYS:
                if (
                    v_clean is None
                    or (isinstance(v_clean, str) and not v_clean.strip())
                    or (isinstance(v_clean, str) and v_clean.strip().startswith("{") and v_clean.strip().endswith("}"))
                ):
                    # skip this key entirely
                    continue
            new[k] = v_clean
        return new

    elif isinstance(obj, list):
        items = [prune_optional_style(v) for v in obj]
        # Preserve FlowList so SafeDumper uses flow_style
        return FlowList(items) if isinstance(obj, FlowList) else items

    else:
        return obj

# --------- Figure preset system --------
def load_presets() -> Dict[str, dict]:
    presets: Dict[str, dict] = {}
    for fp in glob(str(FIGS / "*.yaml")):
        data = load_yaml(Path(fp))
        name = data.get("name")
        if not name:
            raise ValueError(f"Figure preset missing 'name' in {fp}")
        if name in presets:
            raise ValueError(f"Duplicate figure preset name: {name}")
        presets[name] = data
    return presets

def resolve_extends(name: str, presets: Dict[str, dict], seen=None) -> dict:
    seen = seen or set()
    if name in seen:
        raise ValueError(f"Cycle in figure presets: {name}")
    seen.add(name)
    node = copy.deepcopy(presets[name])
    parent = node.get("extends")
    if parent:
        base = resolve_extends(parent, presets, seen)
        node.pop("extends", None)
        node = deep_merge(base, node)
    return node

def render_figures(fig_specs: List[dict], ob_ctx: Dict[str, Any], presets: Dict[str, dict]) -> List[dict]:
    out = []
    for spec in fig_specs:
        preset_name = spec.get("use")
        if not preset_name:
            raise ValueError("Figure spec missing 'use'")

        if preset_name not in presets:
            raise ValueError(f"Preset '{preset_name}' not found. Available: {sorted(presets)}")

        resolved = resolve_extends(preset_name, presets)
        if not isinstance(resolved, dict):
            raise ValueError(f"Preset '{preset_name}' resolved to {type(resolved).__name__}, expected mapping.")

        defaults = resolved.get("params", {}) or {}
        caller   = spec.get("params", {}) or {}
        params   = {**defaults, **ob_ctx, **caller}
        params   = resolve_param_placeholders(params)  # resolve nested like "{variable} (Mean)"

        # Pull layer_template out before formatting block
        layer_tmpl_raw = resolved.get("layer_template")

        # Build the figure block (drop metadata & layer_template)
        block = {k: v for k, v in resolved.items() if k not in ("name", "version", "params", "layer_template")}
        block = deep_format_jinja_safe(block, params)
        block = replace_tokens(block)

        # Robust guards
        if not isinstance(block, dict):
            # Helpful debug snapshot
            raise ValueError(
                f"Preset '{preset_name}' did not resolve to a mapping; got {type(block).__name__}. "
                f"Check that the preset defines 'figure' and 'plots' (and they are not null)."
            )

        if "figure" not in block or block["figure"] is None:
            raise ValueError(f"Preset '{preset_name}' must define 'figure' (missing or null).")

        if "plots" not in block or block["plots"] is None:
            raise ValueError(f"Preset '{preset_name}' must define 'plots' (missing or null).")

        plots = block.get("plots")
        if not isinstance(plots, list):
            raise ValueError(f"Preset '{preset_name}' 'plots' must be a list (got {type(plots).__name__}).")

        # Expand series using the template, if provided
        if layer_tmpl_raw is not None:
            layer_tmpl = deep_format_jinja_safe(copy.deepcopy(layer_tmpl_raw), params)
            layer_tmpl = replace_tokens(layer_tmpl)

            series = params.get("series") or []
            built_layers = []
            for item in series:
                line_params = {**params, **item}
                one = deep_format_jinja_safe(copy.deepcopy(layer_tmpl), line_params)
                one = replace_tokens(one)
                convert_numeric_scalars(one)
                built_layers.append(one)

            if plots and isinstance(plots[0], dict):
                plots[0].setdefault("layers", [])
                plots[0]["layers"].extend(built_layers)

        # Pretty touches
        fig = block.get("figure")
        if isinstance(fig, dict):
            if isinstance(fig.get("layout"), list):
                fig["layout"] = FlowList(fig["layout"])
            if isinstance(fig.get("figure size"), list):
                fig["figure size"] = FlowList(fig["figure size"])

        convert_numeric_scalars(block)
        block = prune_optional_style(block)

        out.append(block)
    return out

# --------- Output dir helper ----------
def compute_output_dir(ob_type: str, ob_spec: dict) -> str:
    """
    Default: one folder per ob_type -> [[runtime_dir]]/plots/{ob_type}
    Optional override: output_subpath: "custom/sub/dir"
    (Kept for compatibility; many presets now take full {output}.)
    """
    sub = ob_spec.get("output_subpath") or "{ob_type}"
    return f"[[runtime_dir]]/plots/{sub}"

# --------------- Builder --------------
def build_template_for_ob_type(ob_type: str) -> dict:
    # Router: config/monitor_types.yaml → ob_type_index
    idx_doc = load_yaml(CFG / "monitor_types.yaml")
    idx = idx_doc.get("ob_type_index")
    if not idx:
        raise KeyError("monitor_types.yaml must define 'ob_type_index': { ob_type: {monitor_type, path} }")

    entry = idx.get(ob_type)
    if not entry:
        raise KeyError(f"ob_type '{ob_type}' not found in monitor_types.yaml")

    mt_path = ROOT / entry["path"]
    mt_doc  = load_yaml(mt_path)

    common_mt = mt_doc.get("common", {})        # e.g., variable, groups (optional)
    ob_map    = mt_doc.get("ob_types") or {}
    if ob_type not in ob_map:
        raise KeyError(f"'{ob_type}' not defined under 'ob_types' in {mt_path}")

    # Merge monitor_type-level common → this ob_type
    ob_spec = deep_merge(common_mt, ob_map[ob_type])

    # Global defaults
    defaults = load_yaml(CFG / "defaults" / "common.yaml")
    dataset_defaults   = defaults.get("dataset_template", {})
    graphics_defaults  = defaults.get("graphics_template", {})
    transform_defaults = defaults.get("transform_defaults", {})  # <-- NEW

    # Build an object context we can reuse everywhere (graphics, transforms, etc.)
    ob_ctx = {
        "ob_type": ob_type,
        "variable": ob_spec.get("variable", ""),
        "output_dir": compute_output_dir(ob_type, ob_spec),
        # include if you use them in output paths
        "sensor": ob_spec.get("sensor", ""),
        "satellite": ob_spec.get("satellite", ""),
    }

    # Datasets: merge defaults into each dataset; carry common groups if not overridden
    datasets = []
    for ds in ob_spec.get("datasets", []):
        # If monitor_type-level 'groups' are defined and this ds doesn't override, inherit them
        if "groups" not in ds and "groups" in ob_spec:
            ds = deep_merge({"groups": ob_spec["groups"]}, ds)

        # Only apply dataset_defaults to ObsMonitor/IodaStats-style datasets
        if ds.get("type") == "IodaStats":
            ds = deep_merge(dataset_defaults, ds)

        datasets.append(ds)

    # Transforms: merge defaults → per-ob_type, then render with ob_ctx and convert tokens
    transforms_out = []
    for tr in ob_spec.get("transforms", []):
        trm = deep_merge(transform_defaults, tr)           # apply transform defaults
        trm = deep_format_jinja_safe(trm, ob_ctx)          # fill any {placeholders}
        trm = replace_tokens(trm)                          # [[token]] → {{ jinja }}
        transforms_out.append(trm)

    # Graphics: build from figure presets if present, else pass-through
    if "figures" in ob_spec:
        presets = load_presets()
        figure_list = render_figures(ob_spec["figures"], ob_ctx, presets)
        graphics = deep_merge(graphics_defaults, {"figure_list": figure_list})
    else:
        graphics = deep_merge(graphics_defaults, ob_spec.get("graphics", {}))

    # Assemble doc (keep key order: datasets → transforms → graphics)
    doc = {"datasets": datasets}
    if transforms_out:
        doc["transforms"] = transforms_out
    doc["graphics"] = graphics
    return doc


# ----------------- CLI ----------------
def main():
    ap = argparse.ArgumentParser(description="Build EVA YAML template from monitor_type + presets (template-only).")
    ap.add_argument("--ob-type", help="ob_type key (e.g., viirs_npp)")
    ap.add_argument("--out", help="Output file (suggest .yaml.j2). Prints to stdout if omitted.")
    ap.add_argument("--list", action="store_true", help="List available ob_types by monitor_type")
    args = ap.parse_args()

    if args.list:
        idx_doc = load_yaml(CFG / "monitor_types.yaml")
        idx = idx_doc.get("ob_type_index") or {}
        by_mt: Dict[str, List[str]] = {}
        for name, entry in idx.items():
            mt = entry.get("monitor_type", "unknown")
            by_mt.setdefault(mt, []).append(name)
        for mt, names in by_mt.items():
            print(f"[{mt}]")
            for n in sorted(names):
                print(f"  - {n}")
        return

    if not args.ob_type:
        ap.error("--ob-type is required (or use --list)")

    doc  = build_template_for_ob_type(args.ob_type)
    text = yaml.safe_dump(doc, sort_keys=False, width=1000)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    else:
        print(text)

if __name__ == "__main__":
    main()
