#!/usr/bin/env bash

#source "${HOMEobsmon}/ush/preamble.sh"

###############################################################
# Source workflow modules
module use ${HOMEobsmon}/modulefiles
module load obs-monitor/ursa # This needs to be machine dependant

#source /scratch3/NCEPDEV/da/Kevin.Dougherty/pyenv/spack-stack-pyenv.sh

export job="obsmon_driver"
export jobid="${job}.$$"

###############################################################
# Execute the JJOB
python "${HOMEobsmon}/driver/driver.py"

exit $?

