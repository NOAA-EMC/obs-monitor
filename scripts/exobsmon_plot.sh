#!/bin/bash

#------------------
# exobsmon_plot.sh
#------------------

#-------------------------------------------------------------
# locate yaml_file and instrument_channels.yaml files
#-------------------------------------------------------------
yaml_file=${YAML_FILE:-${PARMobsmon}/${MODEL}/${MODEL}_plots.yaml}
if [[ ! -e ${yaml_file} ]]; then
   echo "ERROR:  yaml plot file ${yaml_file} NOT FOUND"
   exit 1
fi

chan_yaml=${chan_yaml:-${PARMobsmon}/instrument_channels.yaml}
if [[ ! -e ${chan_yaml} ]]; then
   echo "ERROR:  yaml channel file ${chan_yaml} NOT FOUND"
   exit 2
fi

#---------------------------------------------------------------
# split $yaml_file into sat/instr[/plot], minimization, and obs
# in order to reduce the plot jobs to a more managable size 
#
${APRUN_PY} ${USHobsmon}/splitPlotYaml.py -i ${yaml_file} -c ${chan_yaml}

#--------------------------------------------------------------
# Submit OM_plots job if split yields any *.yaml files
#
if compgen -G "${DATA}/OM_PLOT*.yaml" > /dev/null; then

   jobname="OM_plots"
   export logfile="${OM_LOGS}/${MODEL}/OM_plot.log"
   if [[ -e ${logfile} ]]; then rm ${logfile}; fi

   cmdfile="OM_jobscript"
   >${cmdfile}

   ctr=0
   for yaml in ${DATA}/OM_PLOT*.yaml; do
      echo "processing yaml: $ctr $yaml"
      case ${MACHINE_ID} in
         hera|orion|hercules)
            echo "${ctr} ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> ${cmdfile}
	 ;;
 	 wcoss2)  
            echo "${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> ${cmdfile}
  	 ;;
      esac
      ((ctr+=1))
   done 


   if (( ${ctr} > 0 )); then
      case ${MACHINE_ID} in
         hera|orion|hercules)
            ${SUB} --account ${ACCOUNT} -n ${ctr}  -o ${logfile} -D . -J ${jobname} --time=1:00:00 \
                   --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}"
         ;;

	 wcoss2)  
            mem=$((8*${ctr})) 
            echo "submitting ${jobname} on wcoss2, ctr = $ctr, mem = $mem, cmdfile = ${cmdfile}"

	    ${SUB} -q $JOB_QUEUE -A $ACCOUNT -o ${logfile} -e ${logfile} \
	        -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, MODEL=${MODEL}, \
		    CNTRLobsmon=${CNTRLobsmon}, PARMobsmon=${PARMobsmon}, DATA=${DATA}, \
		    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}, cmdfile=${cmdfile}, ncpus=${ctr}" \
                -l place=vscatter,select=1:ncpus=${ctr}:mem=${mem}gb:prepost=true,walltime=1:00:00 -N ${jobname} ${USHobsmon}/plot_wcoss2.sh
         ;;     
      esac
   fi
fi

#
# Need a new job to run following the plot job to clean up $DATA
#

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


