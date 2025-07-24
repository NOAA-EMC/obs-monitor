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
from wxflow.configuration import cast_as_dtype

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

def copy_plots_to_public(runtime_dir: Path, logger, public_root: Path = Path("/public") / "plots"):
    """
    Copies all plot PNGs from runtime_dir/plots/** into the public/plots/ directory,
    preserving all subdirectory structure.

    Args:
        runtime_dir (Path): Base runtime directory (which contains 'plots/' subfolder).
        logger: Logger instance.
        public_root (Path): Target base directory (default: 'public/plots/').
    """
    plots_dir = runtime_dir / "plots"
    if not plots_dir.exists():
        logger.warning(f"No 'plots/' directory found in runtime_dir: {runtime_dir}")
        return

    for plot_file in plots_dir.rglob("*.png"):
        rel_path = plot_file.relative_to(plots_dir)
        target_path = public_root / rel_path

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plot_file, target_path)
        logger.info(f"Copied {plot_file} → {target_path}")
        
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
        args (tuple): A tuple containing:
            - monitor_dict (dict): A dictionary with monitoring configuration details.
            - timestamp (str): A timestamp string in the format "%Y%m%d_%H%M%S".
    """
    monitor_dict, timestamp = args

    satellite = monitor_dict["satellite"]
    sensor = monitor_dict["sensor"]
    ob_type = f"{sensor}_{satellite}"

    logger = Logger(f"Obs Monitor - {ob_type}")
    logger.info("Starting Observation Monitoring")

    experiment_dir = Path(os.getenv("EXPDIR"))
    if not experiment_dir.exists():
        raise FileNotFoundError(f"Experiment directory not found: {experiment_dir}")

    runtime_root = Path(os.getenv("RUNTIME_DIR"))
    template_path = monitor_dict["template_path"]

    runtime_dir = runtime_root / f"runtime_{ob_type}_{timestamp}"
    runtime_dir.mkdir(parents=True, exist_ok=False)
    logger.info(f"Created runtime directory: {runtime_dir}")

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
        "satellite": satellite,
        "sensor": sensor,
        "ob_type": ob_type
    }

    template_path = os.path.expandvars(template_path)
    eva_config_path = generate_eva_config(template_path, runtime_dir / "eva_config.yaml", context)

    # Get the eva executable
    eva_exe = wxflow.executable.which("eva")

    try:
        subprocess.run([str(eva_exe), str(eva_config_path)], check=True)
        logger.info("EVA executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"EVA failed with exit code {e.returncode}")
        raise

    copy_data = cast_as_dtype(os.getenv("COPY_DATA"))
    keep_data = cast_as_dtype(os.getenv("KEEP_DATA"))
    
    # Copy plots to public
    if copy_data:
        copy_plots_to_public(runtime_dir, logger)

    # Check if user wants to keep data, if not then delete runtime dir.
    if not keep_data:
        if os.path.exists(runtime_dir):
            shutil.rmtree(runtime_dir)
            print(f"Deleted runtime directory: {runtime_dir}")
        else:
            print(f"Runtime directory not found: {runtime_dir}")
    else:
        print(f"KEEP_DATA is True. Data and figures can be found in {runtime_dir}.")
        

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
