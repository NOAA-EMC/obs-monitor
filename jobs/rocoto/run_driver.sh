#!/usr/bin/env bash

source "${HOMEobsmon}/ush/preamble.sh"

###############################################################
# Source workflow modules
. "${HOMEobsmon}/ush/load_obsmon_modules.sh"

export job="obsmon_driver"
export jobid="${job}.$$"

###############################################################
# Execute the JJOB
python "${HOMEobsmon}/driver/driver.py"

exit $?

