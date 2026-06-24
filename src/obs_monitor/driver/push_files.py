"""
Observation Monitoring File Push Script

This script runs an rsync command to push image directories and files
to a webserver.

Algorithm:
    - Get the current cycle window endpoint from PDY (YYYYMMDD)
      and CYC (HH) or CDATE.
    - Create latestCycle.json file for the current cycle.
    - Run rsync command to push image directories and files to server
      while preserving the server's project configuration files.

Environment (set by Rocoto):
  PDY (YYYYMMDD), CYC (HH), PSLOT, COMPONENT,
  RUN, COMROOT, SERVER, SERVER_PATH, SERVER_USER,
"""

import os
import subprocess
import json

from pathlib import Path
from wxflow import Logger


def create_latest_cycle_json(path: Path, cdate, logger):
    output_file = Path(path) / "latestCycle.json"
    cycle_data = {"cycleTime": str(cdate)}

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cycle_data, f, indent=4)
        logger.info(f"Successfully created: {output_file}")

    except Exception as e:
        logger.error(f"Failed to write JSON: {e}")
        raise


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    """
    Determine the current cycle time from CDATE or PDY/CYC, create a
    latestCycle.json file in COMROOT for that cycle, and run an rsync
    command to push image directories and files to the configured server.
    """
    main_logger = Logger("Obs Monitor File Push - main")

    cdate = os.getenv("CDATE")
    pdy = os.getenv("PDY")
    cyc = os.getenv("CYC")

    if not (cdate) and not (pdy and cyc):
        raise EnvironmentError("CDATE or both PDY and CYC must be set.")

    if not (cdate):
        cdate = pdy + cyc

    pslot = os.getenv("PSLOT")
    comroot = os.getenv("COMROOT")
    server = os.getenv("SERVER")
    server_path = os.getenv("SERVER_PATH")
    server_user = os.getenv("SERVER_USER")

    # -------------------------------------
    # Add latestCycle.json file to comroot
    # -------------------------------------
    create_latest_cycle_json(comroot, cdate, main_logger)

    command = [
        "/usr/bin/rsync",
        "-ave", "ssh",
        "--update",
        "--delete-during",
        "--exclude", str(pslot),
        "--exclude", "/atmos",
        f"{comroot}/",
        f"{server_user}@{server}:{server_path}",
    ]
    main_logger.info(f"rsync command: {' '.join(command)}")

    result = subprocess.run(command, shell=False, capture_output=True, text=True)

    main_logger.info(f"Output: {result.stdout}")
    main_logger.info(f"Return Code: {result.returncode}")  # 0 means success


if __name__ == "__main__":
    main()
