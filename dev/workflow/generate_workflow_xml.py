from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

import yaml
from jinja2 import Environment, FileSystemLoader


class ConfigError(Exception):
    """Raised when the YAML configuration is missing keys or contains invalid values."""


ALLOWED_COMPONENTS = {"atmos", "snow", "ocean", "chem", "ice"}


def normalize_and_validate_components(raw) -> str:
    """
    Normalize and validate the `component` field from YAML.

    Accepts list (e.g., ["atmos","snow"]) or comma-separated string ("atmos, snow").
    Lowercases, trims, de-duplicates (preserving order), and validates against
    ALLOWED_COMPONENTS.

    Returns
    -------
    str
        Comma-separated, lowercase string of validated components.

    Raises
    ------
    ValueError
        If type is not list/str or contains invalid values.
    """
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p).strip().lower() for p in raw]
    else:
        raise ValueError("`component` must be a list or comma-separated string.")

    seen, deduped = set(), []
    for p in parts:
        if p not in seen:
            deduped.append(p)
            seen.add(p)

    invalid = [p for p in deduped if p not in ALLOWED_COMPONENTS]
    if invalid:
        allowed_str = ", ".join(sorted(ALLOWED_COMPONENTS))
        raise ValueError(f"Invalid component(s): {', '.join(invalid)}. Allowed: {allowed_str}")

    return ",".join(deduped)


def normalize_cycle_dt_ymdhm(s: Any) -> str:
    """
    Validate a cycle datetime string strictly as YYYYMMDDHHMM (12 digits).

    Parameters
    ----------
    s : Any
        Value to validate/normalize (will be cast to str).

    Returns
    -------
    str
        The same string if valid.

    Raises
    ------
    ValueError
        If not exactly 12 numeric chars or not a real calendar datetime.
    """
    s = str(s)
    if not (s.isdigit() and len(s) == 12):
        raise ValueError("Cycle datetimes must be exactly 12 digits: 'YYYYMMDDHHMM'.")
    # Validate calendar correctness
    datetime.strptime(s, "%Y%m%d%H%M")
    return s


def load_config(path: Path) -> Dict[str, Any]:
    """
    Load and validate the YAML configuration file (no env/tilde expansion).

    Ensures required keys exist, applies defaults, validates components and
    cycle datetime formats (strictly YYYYMMDDHHMM), and prepares derived fields
    for template rendering. Also checks that end_date >= start_date.

    Parameters
    ----------
    path : Path
        Path to the YAML config file.

    Returns
    -------
    Dict[str, Any]
        Validated/normalized configuration dictionary.

    Raises
    ------
    ConfigError
        If the file is missing, keys are missing, or values are invalid.
    """
    if not path.exists():
        raise ConfigError(f"Config not found: {path}")
    with path.open("r") as f:
        cfg = yaml.safe_load(f) or {}

    # Required top-level keys
    required = ["pslot", "component", "start_date", "end_date", "paths"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ConfigError(f"Missing required keys in YAML: {', '.join(missing)}")

    # Required nested path keys
    path_required = ["obsmondir", "expdir", "rundir", "comroot", "dataroot"]
    pmiss = [k for k in path_required if k not in cfg["paths"]]
    if pmiss:
        raise ConfigError(f"Missing required keys under paths: {', '.join(pmiss)}")

    # Defaults
    cfg.setdefault("run", "gdas")
    cfg.setdefault("interval_hours", 6)
    cfg.setdefault("hpc", {})
    cfg["hpc"].setdefault("account", "da-cpu")
    cfg["hpc"].setdefault("queue", "batch")
    cfg["hpc"].setdefault("scheduler", "slurm")
    cfg.setdefault("resources", {})
    cfg["resources"].setdefault("walltime", "00:15:00")
    cfg["resources"].setdefault("task_nodes", "1:ppn=1:tpp=1")
    cfg["resources"].setdefault("task_mem", "4G")
    cfg.setdefault("flags", {})
    cfg["flags"].setdefault("copy_data", False)
    cfg["flags"].setdefault("keep_data", False)
    cfg["flags"].setdefault("create_stubs", False)

    # Validate/normalize fields
    try:
        cfg["component_str"] = normalize_and_validate_components(cfg["component"])
        cfg["start_date"] = normalize_cycle_dt_ymdhm(cfg["start_date"])
        cfg["end_date"] = normalize_cycle_dt_ymdhm(cfg["end_date"])
    except ValueError as e:
        raise ConfigError(str(e)) from e

    # Ensure end >= start
    sdt = datetime.strptime(cfg["start_date"], "%Y%m%d%H%M")
    edt = datetime.strptime(cfg["end_date"], "%Y%m%d%H%M")
    if edt < sdt:
        raise ConfigError("end_date must be greater than or equal to start_date (YYYYMMDDHHMM).")

    return cfg


def parse_args() -> Path:
    """
    Require a YAML configuration path via -y/--yaml. No default.

    Returns
    -------
    Path
        Path to the YAML file.

    Raises
    ------
    SystemExit
        If the argument is missing or the extension is not .yml/.yaml.
    """
    parser = argparse.ArgumentParser(description="Generate Rocoto XML from YAML config.")
    parser.add_argument(
        "-y", "--yaml",
        type=Path,
        required=True,
        help="Path to YAML config (required; .yaml or .yml)",
    )
    args = parser.parse_args()
    if args.yaml.suffix.lower() not in (".yml", ".yaml"):
        parser.error("Config must be a .yml or .yaml file")
    return args.yaml


def main() -> None:
    """
    Entrypoint: load config, render Jinja template, and write Rocoto XML.
    """
    yaml_path = parse_args()
    cfg = load_config(yaml_path)

    pslot = cfg["pslot"]
    component_str = cfg["component_str"]
    paths = cfg["paths"]
    machine_id = cfg.get("machine_id")
    
    obsmondir = Path(paths["obsmondir"])
    expdir = Path(paths["expdir"])
    runtime_dir = Path(paths["rundir"])
    comroot = Path(paths["comroot"])
    dataroot = Path(paths["dataroot"])

    # Path used by your downstream driver
    config_yaml_for_driver = obsmondir / "src/obs_monitor/driver/config.yaml"

    # Output XML path
    output_path = expdir / f"{pslot}_obsmon_rocoto.xml"

    # Load Jinja template
    env = Environment(loader=FileSystemLoader(str(obsmondir)))
    template = env.get_template("parm/monitor_rocoto_template.xml.j2")

    render_kwargs = {
        "PSLOT": pslot,
        "COMPONENT": component_str,
        "HOMEobsmon": str(obsmondir),
        "COMROOT": str(comroot),
        "EXPDIR": str(expdir),
        "DATAROOT": str(dataroot),
        "RUNTIME_DIR": str(runtime_dir),
        "CONFIG_YAML": config_yaml_for_driver,
        "SCHEDULER": str(cfg["hpc"]["scheduler"]),
        "SDATE": str(cfg["start_date"]),
        "EDATE": str(cfg["end_date"]),
        "INTERVAL_HOURS": int(cfg["interval_hours"]),
        "ACCOUNT": str(cfg["hpc"]["account"]),
        "QUEUE": str(cfg["hpc"]["queue"]),
        "WALLTIME": str(cfg["resources"]["walltime"]),
        "TASK_NODES": str(cfg["resources"]["task_nodes"]),
        "TASK_MEM": str(cfg["resources"]["task_mem"]),
        "RUN": str(cfg["run"]),
        "COPY_DATA": bool(cfg["flags"]["copy_data"]),
        "KEEP_DATA": bool(cfg["flags"]["keep_data"]),
        "CREATE_STUBS": bool(cfg["flags"]["create_stubs"]),
        "CYCLES": cfg.get("cycles"),
    }

    # Add MACHINE_ID only if it has a value
    if machine_id:
        render_kwargs["MACHINE_ID"] = machine_id

    output = template.render(**render_kwargs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write(output)

    print(f"Rocoto workflow written to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)
