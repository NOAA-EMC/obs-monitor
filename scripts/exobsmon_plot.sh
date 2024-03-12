#!/bin/bash

#------------------
# exobsmon_plot.sh
#------------------

#---------------------------
# Generate requested plots
#
${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${PARMobsmon}/${MODEL}/gfs_plots.yaml  -p ${PDATE}

#-----------------------------
# Copy output to COMOUTplots
#
if [[ -d ./line_plots ]]; then
   cp -r line_plots ${COMOUTplots}
fi
	
if [[ -d ./map_plots ]]; then
   cp -r map_plots ${COMOUTplots}
fi


