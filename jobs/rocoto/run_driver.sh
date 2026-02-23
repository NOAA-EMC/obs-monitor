#!/usr/bin/env bash
# enable debug mode
set -x


echo "Starting obs-monitor workflow"
MACHINE="UNKNOWN"
source "${HOMEobsmon}/ush/detect_machine.sh"

###############################################################
# Source workflow modules for machine dependent lua files
module use ${HOMEobsmon}/modulefiles
module load obs-monitor/${MACHINE_ID} 

export job="obsmon_driver"
export jobid="${job}.$$"

###############################################################
# Ensure the package root is importable
export PYTHONPATH="${HOMEobsmon}/src:${PYTHONPATH:-}"

# Execute the JJOB
echo "Executing Python driver module"
python -m obs_monitor.driver.driver "$@"

exit $?

