"""
Observation Monitoring Driver Script

This script runs EVA processing for multiple observation types using multiprocessing.
Each job:
    - Finds matching NetCDF observation files
    - Copies them to a unique runtime directory
    - Generates a YAML config using Jinja templates
    - Runs EVA using that config
    - Optionally copies output plots to a public directory
    - Cleans up runtime data unless KEEP_DATA is set

Environment variables drive key configuration parameters.
"""

import os
import uuid
import shutil
import logging
import subprocess
import yaml
import glob
import re
import csv
import numpy as np
import xarray as xr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from multiprocessing import Pool, cpu_count

from wxflow import Logger, Jinja
from wxflow.configuration import cast_as_dtype
import wxflow
from stubs import (
    clone_schema_stub,
    write_generic_stub,
    guess_domain_size,
)


# ------------------------
# Configuration Class
# ------------------------

class MonitoringConfig:
    """
    Encapsulates configuration for a single observation monitoring job.
    Handles environment variables, time window calculation, and paths.
    """
    def __init__(self, monitor_dict: dict, timestamp: str):
        self.monitor_type = monitor_dict['monitor_type']
        if self.monitor_type == 'radiance':
            self.satellite = monitor_dict["satellite"]
            self.sensor = monitor_dict["sensor"]
            self.ob_type = f"{self.sensor}_{self.satellite}"
        elif self.monitor_type == 'conventional':
            self.variable = monitor_dict["variable"]
            self.ob_type = f"{self.variable}"
        self.template_path = os.path.expandvars(monitor_dict["template_path"])
        self.timestamp = timestamp
        self.component = Path(os.getenv("COMPONENT"))
        self.filename_template = monitor_dict.get("filename_template")

        # Construct a unique runtime directory using UUID
        self.runtime_root = Path(os.getenv("RUNTIME_DIR"))
        self.runtime_dir = self.runtime_root / f"runtime_{self.ob_type}_{timestamp}_{uuid.uuid4().hex[:8]}"
        self.runtime_dir.mkdir(parents=True, exist_ok=False)

        self.experiment_dir = Path(os.getenv("EXPDIR"))
        self.dataroot = Path(os.getenv("DATAROOT"))

        # Parse time-related and behavior flags
        self.start_time = datetime.strptime(os.getenv("SDATE"), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        self.end_time = datetime.strptime(os.getenv("EDATE"), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        self.interval_hours = int(os.getenv("INTERVAL_HOURS"))
        self.ncycles = int((self.end_time - self.start_time) / timedelta(hours=self.interval_hours))
        self.run = Path(os.getenv("RUN"))
        self.pdy = Path(os.getenv("PDY"))
        self.cyc = Path(os.getenv("CYC"))
        self.copy_data = cast_as_dtype(os.getenv("COPY_DATA"))
        self.keep_data = cast_as_dtype(os.getenv("KEEP_DATA"))
        self.create_stubs = cast_as_dtype(os.getenv("CREATE_STUBS"))

    def get_jinja_context(self):
        """
        Build the context dictionary passed to the Jinja template engine.
        """
        d = {
            "runtime_dir": str(self.runtime_dir),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "interval_hours": self.interval_hours,
            "ob_type": self.ob_type
        }
        if self.monitor_type == 'radiance':
            d['satellite'] = self.satellite
            d['sensor'] = self.sensor
        elif self.monitor_type == 'conventional':
            d['variable'] = self.variable

        return d


# ------------------------
# Helper Functions
# ------------------------

def infer_schema_from_template(cfg) -> tuple[str, bool]:
    """
    Inspect the Jinja YAML template to infer (product_group, include_gridded_bins).
    Looks at lines under 'groups:' with 'name: <path>'.
    """
    pg = None
    include_gridded = False

    try:
        with open(cfg.template_path, "r") as tf:
            for line in tf:
                m = re.search(r"name:\s*([A-Za-z0-9_\/]+)", line)
                if not m:
                    continue
                path = m.group(1).strip()
                parts = path.split("/")
                if parts and parts[0] == "griddedBins":
                    include_gridded = True
                # last component tends to be the product group (e.g., totalSnowDepth, aerosolOpticalDepth)
                if len(parts) >= 1:
                    pg = parts[-1]
    except Exception:
        pass

    # Sensible fallbacks if template scan didn't find anything
    if not pg:
        ob = cfg.ob_type.lower()
        if "snow" in ob or "snocvr" in ob:
            pg = "totalSnowDepth"
        elif "aod" in ob or "viirs" in ob:
            pg = "aerosolOpticalDepth"
        else:
            pg = "value"

    return pg, include_gridded


def expected_stub_filename(cfg, dt, reference_path: str | Path | None) -> str:
    """
    Use per-job filename_template when provided; else clone a reference name; else fallback.
    """
    ts = dt.strftime("%Y%m%d%H")

    if getattr(cfg, "filename_template", None):
        return dt.strftime(cfg.filename_template)

    if reference_path:
        ref_name = Path(reference_path).name
        return re.sub(r"\d{10,14}", ts, ref_name, count=1)

    # last-resort heuristic (should rarely run now)
    return f"{cfg.ob_type}_{ts}.nc"


def write_coverage_report(expected_times, found_times, out_path, logger):
    """
    Write a lightweight CSV coverage report for expected and found times for
    easy, digestable way to view report of file coverage. Can be used with cron
    to report users of missing files based on threshold value and can provide
    service level indicator stats.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    found = {dt for dt in found_times}
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "present"])
        for t in expected_times:
            w.writerow([t.strftime("%Y-%m-%d %H:%M"), int(t in found)])
        cov_num = f"{len(found)}/{len(expected_times)}"
        cov_pct = f"{(len(found)/len(expected_times))*100:.0f}%" if expected_times else "n/a"
        w.writerow([])
        w.writerow(["coverage", cov_num])
        w.writerow(["coverage_pct", cov_pct])
    logger.info(f"[coverage] {cov_num} ({cov_pct}) -> {out_path}")

    return f"{cov_num} ({cov_pct})"


def create_stub_for_missing_cycle(cfg: MonitoringConfig, dt: datetime, logger, reference_path: str | Path | None = None):
    """
    Try to clone schema from any real file we found this run; if none, write a minimal byDomains stub.
    """
    # exact filename EVA expects for this cycle
    fname = expected_stub_filename(cfg, dt, reference_path)
    out = cfg.runtime_dir / fname

    # Prefer clone-from-real if any real file exists
    if reference_path:
        try:
            clone_schema_stub(reference_path, out, dt)
            logger.info(f"[{cfg.ob_type}] Stub cloned from real: {Path(reference_path).name} -> {out.name}")
            return True
        except Exception as e:
            logger.warning(f"[{cfg.ob_type}] Clone failed; falling back to generic stub: {e}")

    # Infer product_group + whether gridded bins appear from the Jinja template
    product_group, include_gridded = infer_schema_from_template(cfg)

    try:
        write_generic_stub(
            out_path=out,
            dt=dt,
            ob_type=cfg.ob_type,
            product_group=product_group,
            include_gridded_bins=include_gridded,
        )
        logger.info(f"[{cfg.ob_type}] Generic stub written: {out.name} (pg={product_group}, gridded={include_gridded})")
        return True
    except Exception as e:
        logger.error(f"[{cfg.ob_type}] Failed to write generic stub {out.name}: {e}")
        return False


def extract_timestamp(file: Path) -> str | None:
    """
    Extract a timestamp string from the filename stem.

    This function searches for the first sequence of 10 to 14 digits in the
    file's stem (filename without extension), which typically represents a
    timestamp in the formats: YYYYMMDDHH, YYYYMMDDHHMM, or YYYYMMDDHHMMSS.

    Parameters:
        file (Path): The full path to the file.

    Returns:
        str | None: The matched timestamp string if found, otherwise None.
    """
    match = re.search(r'\d{10,14}', file.stem)
    if match:
        return match.group(0)
    return None


def find_matching_nc_files(cfg: MonitoringConfig, logger):
    """
    Scan DATAROOT for NetCDF files corresponding to expected cycles between start_time and end_time,
    using interval_hours. Return matched files, full expected timeline, and found timestamps.

    Returns:
        (List[Path], List[datetime], List[datetime])
        (nc_files, expected_times, found_times)
    """
    nc_files = []
    found_times = []
    pattern = f"{cfg.ob_type}_*.nc"

    logger.info(f"Finding {cfg.ob_type} files from {cfg.start_time} to {cfg.end_time} every {cfg.interval_hours} hours")

    # Generate all expected datetime objects based on interval_hours
    expected_times = [
        cfg.start_time + timedelta(hours=i * cfg.interval_hours)
        for i in range(cfg.ncycles + 1)
    ]

    for dt in expected_times:
        pdy_str = dt.strftime("%Y%m%d")     # gdas.PDY directory
        cyc_str = dt.strftime("%H")         # CYC subdirectory
        run_dir = cfg.dataroot / f"gdas.{pdy_str}" / f"{cyc_str}/products/{cfg.component}/anlmon"

        if not run_dir.exists():
            logger.warning(f"Expected directory does not exist: {run_dir}")
            continue

        if getattr(cfg, "filename_template", None):
            expected_name = dt.strftime(cfg.filename_template)
            f = run_dir / expected_name
            if f.exists():
                nc_files.append(f)
                found_times.append(dt)
            else:
                logger.warning(f"Missing expected file {f}")
            continue  # skip globbing; we know the exact name

        # Find files matching ob_type in this directory
        matched_files = []
        for file in run_dir.glob(pattern):
            timestamp_str = extract_timestamp(file)
            if not timestamp_str:
                logger.debug(f"No timestamp found in {file.name}, skipping")
                continue

            # Only match the first 10 digits (YYYYMMDDHH)
            file_cycle = timestamp_str[:10]
            if file_cycle == dt.strftime("%Y%m%d%H"):
                matched_files.append(file)

        if not matched_files:
            logger.warning(f"No files found for expected cycle {dt.strftime('%Y%m%d%H')} in {run_dir}")
        else:
            nc_files.extend(matched_files)
            found_times.append(dt)

    logger.info(f"Found {len(nc_files)} matching NetCDF files for {cfg.ob_type}")
    return sorted(nc_files), expected_times, found_times


def copy_nc_files_to_runtime(nc_files, cfg: MonitoringConfig, logger):
    """
    Copies matched NetCDF files to the runtime directory. Logs and continues on per-file errors.
    """
    copied = 0
    for file in nc_files:
        try:
            shutil.copy2(file, cfg.runtime_dir / file.name)
            copied += 1
            logger.info(f"[{cfg.ob_type}] Copied: {file.name}")
        except FileNotFoundError:
            logger.warning(f"[{cfg.ob_type}] Source vanished before copy: {file}")
        except PermissionError as e:
            logger.error(f"[{cfg.ob_type}] Permission error copying {file}: {e}")
        except Exception as e:
            logger.error(f"[{cfg.ob_type}] Unexpected error copying {file}: {e}")
    if copied == 0:
        logger.warning(f"[{cfg.ob_type}] No files were copied into runtime dir {cfg.runtime_dir}")


def generate_eva_config(cfg: MonitoringConfig, logger) -> Path:
    """
    Generates a YAML configuration file for EVA using a Jinja template.

    Returns:
        Path to the generated EVA config file.
    """
    context = cfg.get_jinja_context()
    output_path = cfg.runtime_dir / "eva_config.yaml"
    jinja = Jinja(template_path_or_string=cfg.template_path, data=context)
    jinja.save(output_file=output_path)
    logger.info(f"Generated EVA config: {output_path}")

    return output_path


def run_eva(cfg: MonitoringConfig, eva_config_path: Path, logger):
    """
    Executes the EVA application with the generated config file.
    Logs and returns on failure (non-fatal).
    """
    eva_exe = wxflow.executable.which("eva")
    if not eva_exe:
        logger.error(f"[{cfg.ob_type}] EVA executable not found in PATH. Skipping EVA.")
        return

    try:
        subprocess.run([str(eva_exe), str(eva_config_path)], check=True)
        logger.info(f"[{cfg.ob_type}] EVA completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[{cfg.ob_type}] EVA failed with code {e.returncode}. Continuing.")
    except FileNotFoundError:
        logger.error(f"[{cfg.ob_type}] EVA executable not found at runtime. Continuing.")
    except Exception as e:
        logger.error(f"[{cfg.ob_type}] Unexpected EVA error: {e}. Continuing.")


def copy_plots_to_public(cfg: MonitoringConfig, logger, public_root: Path = Path("/public") / "plots"):
    """
    Copies generated PNG plots from the runtime directory to a public location.
    """
    plots_dir = cfg.runtime_dir / "plots"
    if not plots_dir.exists():
        logger.warning(f"No plots/ directory in {cfg.runtime_dir}")
        return

    for plot_file in plots_dir.rglob("*.png"):
        rel_path = plot_file.relative_to(plots_dir)
        target_path = public_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plot_file, target_path)
        logger.info(f"Copied plot to public: {target_path}")


def cleanup_runtime(cfg: MonitoringConfig, logger):
    """
    Deletes the runtime directory unless KEEP_DATA is True.
    """
    if cfg.runtime_dir.exists() and cfg.runtime_dir.is_dir() and "runtime_" in cfg.runtime_dir.name:
        shutil.rmtree(cfg.runtime_dir)
        logger.info(f"Deleted runtime dir: {cfg.runtime_dir}")
    else:
        logger.warning(f"Runtime dir not deleted (invalid path?): {cfg.runtime_dir}")


# ------------------------
# Main Job Execution
# ------------------------

def run_monitoring_job(args):
    """
    Run one complete monitoring job:
    - Match and copy NetCDF files
    - Optionally create stubs for missing cycles
    - Generate EVA config
    - Run EVA (if inputs exist)
    - Copy plots
    - Clean up
    """
    monitor_dict, timestamp = args
    cfg = MonitoringConfig(monitor_dict, timestamp)
    logger = Logger(f"Obs Monitor - {cfg.ob_type}")
    logger.info(f"Starting job for {cfg.ob_type}")

    try:
        # after discovery
        nc_files, expected_times, found_times = find_matching_nc_files(cfg, logger)
        cov_str = write_coverage_report(expected_times, found_times, cfg.runtime_dir / "coverage.csv", logger)

        # NEW: pick a reference if any real file exists
        ref_path = nc_files[0] if nc_files else None

        # optional stubs
        if cfg.create_stubs and expected_times:
            missing = [dt for dt in expected_times if dt not in set(found_times)]
            if missing:
                logger.info(f"[{cfg.ob_type}] Creating {len(missing)} stub files for missing cycles")
                for dt in missing:
                    create_stub_for_missing_cycle(cfg, dt, logger, reference_path=ref_path)

        # Now stage real files
        copy_nc_files_to_runtime(nc_files, cfg, logger)

        # If the runtime has no .nc at all (neither real nor stubs), skip EVA
        if not any(cfg.runtime_dir.glob("*.nc")):
            logger.warning(f"[{cfg.ob_type}] No runtime inputs (.nc). Skipping EVA. Coverage: {cov_str}")
            return {"ob_type": cfg.ob_type, "status": "skipped_no_input", "coverage": cov_str}

        eva_config_path = generate_eva_config(cfg, logger)
        run_eva(cfg, eva_config_path, logger)

        if cfg.copy_data:
            copy_plots_to_public(cfg, logger)

        return {"ob_type": cfg.ob_type, "status": "ok", "coverage": cov_str}

    except Exception as e:
        logger.error(f"[{cfg.ob_type}] Job failed: {e}")
        return {"ob_type": cfg.ob_type, "status": "failed", "error": str(e)}

    finally:
        if not cfg.keep_data:
            try:
                cleanup_runtime(cfg, logger)
            except Exception as e:
                logger.warning(f"[{cfg.ob_type}] Cleanup issue: {e}")
        else:
            logger.info(f"[{cfg.ob_type}] KEEP_DATA=True. Results kept in: {cfg.runtime_dir}")


# ------------------------
# Main Entry Point
# ------------------------

def main():
    """
    Parses environment variables and runs all monitoring jobs in parallel.
    """
    main_logger = Logger("Obs Monitor - main")

    cdate = os.getenv("CDATE")
    if not cdate:
        raise EnvironmentError("CDATE is not set")

    try:
        timestamp = datetime.strptime(cdate, "%Y%m%d%H").strftime("%Y%m%d_%H%M%S")
    except ValueError:
        raise ValueError("CDATE must be in format YYYYMMDDHH")

    config_yaml = os.getenv("CONFIG_YAML")
    if not config_yaml:
        raise EnvironmentError("CONFIG_YAML is not set")

    with open(config_yaml, "r") as f:
        config = yaml.safe_load(f)

    job_list = config["jobs"] if isinstance(config, dict) and "jobs" in config else config
    if not isinstance(job_list, list):
        job_list = [job_list]

    component_filter = os.getenv("COMPONENT")
    if component_filter:
        requested_components = {c.strip() for c in component_filter.split(",")}
        original_count = len(job_list)
        job_list = [job for job in job_list if job.get("component") in requested_components]
        skipped = original_count - len(job_list)
        main_logger.info(
            f"Filtered jobs: running {len(job_list)} matching components "
            f"({', '.join(requested_components)}), skipped {skipped}."
        )

    if not job_list:
        main_logger.warning("No jobs match the given COMPONENT filter. Exiting ...")
        return

    job_args = [(job, timestamp) for job in job_list]
    nprocs = min(cpu_count(), len(job_args))
    main_logger.info(f"Starting multiprocessing with {nprocs} processes")

    logging.info(f"Starting multiprocessing with {min(cpu_count(), len(job_args))} processes")

    with Pool(processes=min(cpu_count(), len(job_args))) as pool:
        results = pool.map(run_monitoring_job, job_args)

    ok = sum(1 for r in results if r.get("status") == "ok")
    skipped = [r for r in results if r.get("status", "").startswith("skipped")]
    failed = [r for r in results if r.get("status") == "failed"]
    logging.info(f"Job summary: {ok} ok, {len(skipped)} skipped, {len(failed)} failed (non-fatal).")
    for r in skipped:
        logging.info(f"Skipped {r['ob_type']}: {r['status']} — coverage {r.get('coverage')}")
    for r in failed:
        logging.info(f"Failed {r['ob_type']}: {r.get('error')}")


if __name__ == "__main__":
    main()
