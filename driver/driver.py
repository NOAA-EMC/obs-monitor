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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from multiprocessing import Pool, cpu_count

from wxflow import Logger, Jinja
from wxflow.configuration import cast_as_dtype
import wxflow


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
        self.copy_data = cast_as_dtype(os.getenv("COPY_DATA"))
        self.keep_data = cast_as_dtype(os.getenv("KEEP_DATA"))

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
    Scan DATAROOT for NetCDF files that match the ob_type and fall within the time window.

    Returns:
        List of Path objects pointing to matched NetCDF files.
    """
    pattern = f"{cfg.ob_type}_*.nc"
    nc_files = []

    for file in cfg.dataroot.glob(pattern):
        try:
            timestamp_str = extract_timestamp(file)  # extract timestamp suffix
            file_time = datetime.strptime(timestamp_str, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            if cfg.start_time <= file_time <= cfg.end_time:
                nc_files.append(file)
        except ValueError:
            logger.warning(f"Skipping file with bad timestamp: {file.name}")

    logger.info(f"Found {len(nc_files)} matching NetCDF files for {cfg.ob_type}")

    return nc_files


def copy_nc_files_to_runtime(nc_files, cfg: MonitoringConfig, logger):
    """
    Copies matched NetCDF files to the runtime directory.
    """
    for file in nc_files:
        shutil.copy2(file, cfg.runtime_dir / file.name)
        logger.info(f"Copied: {file.name}")


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
    """
    # Get the eva executable
    eva_exe = wxflow.executable.which("eva")
    if not eva_exe:
        logger.error("EVA executable not found in PATH.")
        raise FileNotFoundError("EVA executable not found")

    try:
        subprocess.run([str(eva_exe), str(eva_config_path)], check=True)
        logger.info("EVA completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"EVA failed with code {e.returncode}")
        raise


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
    - Generate EVA config
    - Run EVA
    - Copy plots
    - Clean up
    """
    monitor_dict, timestamp = args
    cfg = MonitoringConfig(monitor_dict, timestamp)
    logger = Logger(f"Obs Monitor - {cfg.ob_type}")
    logger.info(f"Starting job for {cfg.ob_type}")

    nc_files = find_matching_nc_files(cfg, logger)
    copy_nc_files_to_runtime(nc_files, cfg, logger)
    eva_config_path = generate_eva_config(cfg, logger)
    run_eva(cfg, eva_config_path, logger)

    if cfg.copy_data:
        copy_plots_to_public(cfg, logger)

    if not cfg.keep_data:
        cleanup_runtime(cfg, logger)
    else:
        logger.info(f"KEEP_DATA=True. Results kept in: {cfg.runtime_dir}")


# ------------------------
# Main Entry Point
# ------------------------

def main():
    """
    Parses environment variables and runs all monitoring jobs in parallel.
    """
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

    job_args = [(job, timestamp) for job in job_list]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info(f"Starting multiprocessing with {min(cpu_count(), len(job_args))} processes")

    with Pool(processes=min(cpu_count(), len(job_args))) as pool:
        pool.map(run_monitoring_job, job_args)


if __name__ == "__main__":
    main()
