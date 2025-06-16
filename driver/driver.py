import argparse
import os
import yaml
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from wxflow import Logger, Jinja
import jinja2
from datetime import datetime
from dateutil.parser import parse as parse_datetime


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


def driver(monitor_dict: dict):
    """
    Main driver function for observation monitoring workflow.

    This function:
    - Creates a timestamped runtime directory
    - Copies NetCDF files matching the observation type to that directory
    - Generates a Jinja2-based EVA configuration file
    - Runs the EVA command using the config
    - (Optional) Copies the results to an output directory

    Args:
        monitor_dict (dict): Dictionary containing configuration values
    """

    # Add logger
    logger = Logger('Observation Monitoring')

    logger.info('Starting Observation Monitoring')

    # Validate required directories
    experiment_dir = Path(monitor_dict["experiment_dir"])
    if not experiment_dir.exists():
        raise FileNotFoundError(f"Experiment directory not found: {experiment_dir}")

    runtime_root = Path(monitor_dict.get("runtime_dir", "./runtime"))
    outdir = Path(monitor_dict.get("outdir", "./outdir"))
    template_path = monitor_dict["template_path"]

    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template path not found: {template_path}")

    # Create runtime directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    runtime_dir = runtime_root / f"runtime_{timestamp}"
    runtime_dir.mkdir(parents=True, exist_ok=False)
    logging.info(f"Created runtime directory: {runtime_dir}")

    # Copy experiment files
    ob_type = monitor_dict["ob type"]
    nc_files = list(experiment_dir.glob(f"*{ob_type}_*.nc"))
    if not nc_files:
        logging.warning(f"No NetCDF files found matching *{ob_type}_*.nc in {experiment_dir}")
    for file in nc_files:
        shutil.copy2(file, runtime_dir / file.name)
        logging.info(f"Copied: {file.name}")

    # Generate EVA config
    context = {
        "runtime_dir": str(runtime_dir),
        "start_time": parse_datetime(monitor_dict["start"]),
        "end_time": parse_datetime(monitor_dict["end"]),
        "interval_hours": monitor_dict.get("interval_hours", 6),
    }
    eva_config_path = generate_eva_config(template_path, runtime_dir / "eva_config.yaml", context)

    # Run EVA
    try:
        subprocess.run(["eva", str(eva_config_path)], check=True)
        logging.info("EVA executed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"EVA failed with exit code {e.returncode}")
        raise

    # Copy results to output directory
    # outdir.mkdir(parents=True, exist_ok=True)
    # for file in runtime_dir.glob("*"):
    #     if file.is_file():
    #         shutil.copy2(file, outdir / file.name)
    #         logging.info(f"Moved {file.name} to output directory: {outdir}")



def main():
    """
    Entry point for the script. Parses command-line arguments and loads configuration.

    If a config YAML file is provided, it loads and passes it to the driver function.
    """
    parser = argparse.ArgumentParser(description="Run obs-monitor driver.")
    parser.add_argument("-c", "--config", type=str, required=False,
                        help="Path to YAML config file.")
    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f:
            monitor_config = yaml.safe_load(f)
            logging.info(f"Loaded config from {args.config}")

    try:
        driver(monitor_config)
    except Exception as e:
        logging.exception("Driver failed.")
        raise


if __name__ == "__main__":
    main()
    