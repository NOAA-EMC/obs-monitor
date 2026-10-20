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

# Run the operational pipeline (diag files -> summaries -> figures + status)
echo "Executing obs-monitor operational pipeline"
python -m obs_monitor.pipelines.operational "$@"

exit $?
