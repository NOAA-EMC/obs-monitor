#!/usr/bin/env bash

source "${HOMEobsmon}/ush/detect_machine.sh"

###############################################################
# Source workflow modules for machine dependent lua files
module use ${HOMEobsmon}/modulefiles
module load obs-monitor/${MACHINE_ID} 

export job="obsmon_driver"
export jobid="${job}.$$"

###############################################################
# Execute the JJOB
python "${HOMEobsmon}/driver/driver.py"

exit $?

