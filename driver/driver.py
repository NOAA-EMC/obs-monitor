import argparse
import os
import yaml
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse as parse_datetime
from wxflow import Logger, Jinja
from multiprocessing import Pool


def generate_eva_config(template_path: str, output_path: str, context: dict):
    """
    Render a Jinja template to create an EVA configuration file.

    Args:
        template_path (str): Path to the Jinja template file.
        output_path (str): Path where the rendered config file will be saved.
        context (dict): Dictionary containing the data used for rendering the template.

    Returns:
        str: Path to the rendered EVA configuration file.
    """
    jinja_render = Jinja(template_path_or_string=template_path, data=context)
    jinja_render.save(output_file=output_path)
    return output_path


def run_monitoring_job(args):
    """
    Main driver function for observation monitoring workflow.

    This function:
    - Creates a timestamped runtime directory
    - Copies NetCDF files matching the observation type to that directory
    - Generates a Jinja2-based EVA configuration file
    - Runs the EVA command using the config
    - (Optional) Copies the results to an output directory

    Args:
        ars (dict): list including monitor_dict and timestamp
    """
    monitor_dict, timestamp = args

    logger = Logger(f"Obs Monitor - {monitor_dict['ob_type']}")
    logger.info("Starting Observation Monitoring")

    # Validate required directories
    experiment_dir = Path(monitor_dict["experiment_dir"])
    if not experiment_dir.exists():
        raise FileNotFoundError(f"Experiment directory not found: {experiment_dir}")

    runtime_root = monitor_dict.get("runtime_dir", "./runtime")
    outdir = Path(monitor_dict.get("outdir", "./outdir"))
    template_path = monitor_dict["template_path"]

    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template path not found: {template_path}")

    # Create runtime directory
    runtime_dir = Path(os.path.join(runtime_root, f"runtime_{monitor_dict['ob_type']}_{timestamp}"))
    runtime_dir.mkdir(parents=True, exist_ok=False)
    logging.info(f"Created runtime directory: {runtime_dir}")

    # Copy experiment files
    ob_type = monitor_dict["ob_type"]
    nc_files = list(experiment_dir.glob(f"*{ob_type}_*.nc"))
    if not nc_files:
        logging.warning(f"No NetCDF files found matching *{ob_type}_*.nc in {experiment_dir}")
    for file in nc_files:
        shutil.copy2(file, runtime_dir / file.name)
        logging.info(f"Copied: {file.name}")

    interval_hours = monitor_dict.get("interval_hours")
    ncycles = monitor_dict.get("ncycles")
    
    # Compute end_time (from command line) and start_time (derived)
    end_time = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    start_time = end_time - timedelta(hours=interval_hours * ncycles)
    
    # Generate EVA config
    context = {
        "runtime_dir": str(runtime_dir),
        "start_time": start_time,
        "end_time": end_time,
        "interval_hours": interval_hours,
    }
    eva_config_path = generate_eva_config(template_path, runtime_dir / "eva_config.yaml", context)

    # Run EVA
    try:
        subprocess.run(["eva", str(eva_config_path)], check=True)
        logging.info("EVA executed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"EVA failed with exit code {e.returncode}")
        raise

    # Optionally copy results to output directory (still commented out)
    # outdir.mkdir(parents=True, exist_ok=True)
    # for file in runtime_dir.glob("*"):
    #     if file.is_file():
    #         shutil.copy2(file, outdir / file.name)
    #         logging.info(f"Moved {file.name} to output directory: {outdir}")


def main():
    """
    Entry point for the script. Parses command-line arguments and loads configuration.
    """
    parser = argparse.ArgumentParser(description="Run obs-monitor driver.")
    parser.add_argument("-y", "--config", type=str, required=True, help="Path to YAML config file.")
    parser.add_argument("-c", "--cycle", type=str, required=True, help="Cycle datetime in YYYYMMDDHH format.")
    args = parser.parse_args()

    try:
        cycle_dt = datetime.strptime(args.cycle, "%Y%m%d%H")
        timestamp = cycle_dt.strftime("%Y%m%d_%H%M%S")
    except ValueError:
        raise ValueError("Invalid cycle format. Use YYYYMMDDHH.")

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
        logging.info(f"Loaded config from {args.config}")

    # Support original config format and new format for testing
    if isinstance(config, dict) and "jobs" in config:
        monitor_config = config["jobs"]
    else:
        monitor_config = config if isinstance(config, list) else [config]

    job_args = [(job, timestamp) for job in monitor_config]

    try:
        with Pool(processes=min(len(job_args), os.cpu_count())) as pool:
            pool.map(run_monitoring_job, job_args)
    except Exception as e:
        logging.exception("One or more monitoring jobs failed.")
        raise


if __name__ == "__main__":
    main()
    