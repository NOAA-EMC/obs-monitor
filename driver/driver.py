import os
import yaml
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
import subprocess
import wxflow
from wxflow import Logger, Jinja

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

    experiment_dir = Path(os.getenv("EXPDIR"))
    if not experiment_dir.exists():
        raise FileNotFoundError(f"Experiment directory not found: {experiment_dir}")

    runtime_root = Path(os.getenv("RUNTIME_DIR"))
    template_path = monitor_dict["template_path"]
    print(template_path)

    runtime_dir = runtime_root / f"runtime_{monitor_dict['ob_type']}_{timestamp}"
    runtime_dir.mkdir(parents=True, exist_ok=False)
    logger.info(f"Created runtime directory: {runtime_dir}")

    ob_type = monitor_dict["ob_type"]
    dataroot = Path(os.getenv("DATAROOT"))
    # Going to need to clean this up a bit so we grab the right dates etc.
    nc_files = list(dataroot.glob(f"*{ob_type}_*.nc"))
    for file in nc_files:
        shutil.copy2(file, runtime_dir / file.name)
        logger.info(f"Copied: {file.name}")

    interval_hours = int(os.getenv("INTERVAL_HOURS"))
    ncycles = int(os.getenv("NCYCLES"))

    end_time = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    start_time = end_time - timedelta(hours=interval_hours * ncycles)

    context = {
        "runtime_dir": str(runtime_dir),
        "start_time": start_time,
        "end_time": end_time,
        "interval_hours": interval_hours,
        "ob_type": ob_type
    }

    eva_config_path = generate_eva_config(template_path, runtime_dir / "eva_config.yaml", context)

    # Get the eva executable
    eva_exe = wxflow.executable.which("eva")

    try:
        subprocess.run([str(eva_exe), str(eva_config_path)], check=True)
        logger.info("EVA executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"EVA failed with exit code {e.returncode}")
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
    # Read environment variables set by Rocoto task's <envar>
    cdate_str = os.getenv("CDATE")
    if not cdate_str:
        raise EnvironmentError("CDATE environment variable not set")

    try:
        cycle_dt = datetime.strptime(cdate_str, "%Y%m%d%H")
        timestamp = cycle_dt.strftime("%Y%m%d_%H%M%S")
    except ValueError:
        raise ValueError("Invalid CDATE format, expected YYYYMMDDHH")

    config_path = Path(os.getenv("CONFIG_YAML"))
    if not config_path:
        raise EnvironmentError("CONFIG_YAML environment variable not set")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Normalize config to a list of jobs
    if isinstance(config, dict) and "jobs" in config:
        monitor_jobs = config["jobs"]
    else:
        monitor_jobs = config if isinstance(config, list) else [config]

    # Inject runtime_dir from environment or default
    runtime_dir = Path(os.getenv("RUNTIME_DIR"))
    for job in monitor_jobs:
        job.setdefault("runtime_dir", runtime_dir)

    job_args = [(job, timestamp) for job in monitor_jobs]

    with Pool(processes=min(len(job_args), os.cpu_count())) as pool:
        pool.map(run_monitoring_job, job_args)

if __name__ == "__main__":
    main()
