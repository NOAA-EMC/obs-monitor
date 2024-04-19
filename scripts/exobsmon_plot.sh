#!/bin/bash

#------------------
# exobsmon_plot.sh
#------------------

jobname="OM_test"
logfile="${OM_LOGS}/${MODEL}/OM_log_test"
if [[ -e ${logfile} ]]; then rm ${logfile}; fi

#-------------------------------------------------------------
# locate $model_plots.yaml and instrument_channels.yaml files
#-------------------------------------------------------------
plot_yaml=${plot_yaml:-${PARMobsmon}/${MODEL}/${MODEL}_plots.yaml}

if [[ ! -e ${plot_yaml} ]]; then
   echo "ERROR:  yaml plot file ${plot_yaml} NOT FOUND"
   exit 1
fi

chan_yaml=${chan_yaml:-${PARMobsmon}/instrument_channels.yaml}
if [[ ! -e ${chan_yaml} ]]; then
   echo "ERROR:  yaml channel file ${chan_yaml} NOT FOUND"
   exit 2
fi

#----------------------------------------
# split $plot_yaml into sat/instr[/plot]
#
${APRUN_PY} ${USHobsmon}/splitPlotYaml.py -i ${plot_yaml} -c ${chan_yaml}

#exit 0

cmdfile="OM_test_jobscript"
>$cmdfile

ctr=0
for yaml in ./sat_*.yaml; do
   echo "${ctr} $yaml"
   echo "${ctr} ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
   ((ctr+=1))
done 
chmod 755 $cmdfile

echo "submitting job $jobname"

if [[ ${ctr} > 0 ]]; then
   $SUB --account ${ACCOUNT} -n ${ctr}  -o ${logfile} -D . -J ${jobname} --time=1:00:00 \
        --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}"
fi


#-----------------------------
# Copy output to COMOUTplots
#
#   This will now have to be done in a separate
#   job set to run after cmdfile completes.
#
#if [[ -d ./line_plots ]]; then
#   cp -r line_plots ${COMOUTplots}
#fi
#	
#if [[ -d ./map_plots ]]; then
#   cp -r map_plots ${COMOUTplots}
#fi


