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

   export logfile_clnup="${OM_LOGS}/${MODEL}/OM_cleanup.log"
   if [[ -e ${logfile_clnup} ]]; then rm ${logfile_clnup}; fi

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
            # submit plot job
            plotjob_id=$(${SUB} --account ${ACCOUNT} -n ${ctr}  -o ${logfile} -D . -J ${jobname} --time=0:05:00 \
                   --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}")

            # submit cleanup job to run after plot job
            plotjob_id=`echo ${plotjob_id} | gawk '{ print $4 }'`
            ${SUB} --account ${ACCOUNT} -n 1 -o ${logfile_clnup} -D . -J "OM_cleanup" --time=0:10:00 \
                   -p ${SERVICE_PARTITION} --dependency=afterok:${plotjob_id} ${USHobsmon}/om_cleanup.sh

         ;;

	 wcoss2)  
            # submit plot job
            mem=$((12*${ctr})) 
	    plotjob_id=$(${SUB} -q $JOB_QUEUE -A $ACCOUNT -o ${logfile} -e ${logfile} \
	        -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, MODEL=${MODEL}, \
		    CNTRLobsmon=${CNTRLobsmon}, PARMobsmon=${PARMobsmon}, DATA=${DATA}, CARTOPY_DATA_DIR=${CARTOPY_DATA_DIR}, \
		    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}, cmdfile=${cmdfile}, ncpus=${ctr}, OM_PLOTS=${OM_PLOTS}" \
	        -l place=vscatter,select=1:ncpus=${ctr}:mem=${mem}gb:prepost=true,walltime=1:00:00 -N ${jobname} ${USHobsmon}/plot_wcoss2.sh)

            # submit cleanup job to run after plot job
 	    ${SUB} -q $JOB_QUEUE -A $ACCOUNT -o ${logfile_clnup} -e ${logfile_clnup} \
  	        -v "DATA=${DATA}, KEEPDATA=${KEEPDATA}, NET=${NET}, DATAROOT=${DATAROOT}, \
 	    COMOUTplots=${COMOUTplots}, DATA=${DATA}, MACHINE_ID=${MACHINE_ID}" \
                -l select=1:mem=500mb,walltime=1:00:00 -W depend=afterok:${plotjob_id} -N "OM_cleanup" ${USHobsmon}/om_cleanup.sh

         ;;     
      esac
   fi
fi

