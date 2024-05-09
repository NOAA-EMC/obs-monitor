#!/bin/bash

#------------------
# exobsmon_plot.sh
#------------------

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

#-----------------------------------------------------------
# split $plot_yaml into sat/instr[/plot], minimization, obs
#
${APRUN_PY} ${USHobsmon}/splitPlotYaml.py -i ${plot_yaml} -c ${chan_yaml}

#--------------------------------------------------------------
# Submit OM_sat_plots job if split yields any sat_*.yaml files
#
if compgen -G "${DATA}/sat_*.yaml" > /dev/null; then

   jobname="OM_sat_plots"
   logfile="${OM_LOGS}/${MODEL}/OM_sat_plot.log"
   if [[ -e ${logfile} ]]; then rm ${logfile}; fi

   cmdfile="OM_sat_jobscript"
   >$cmdfile
   ctr=0

   for yaml in ${DATA}/sat_*.yaml; do
      case ${MACHINE_ID} in
         hera)
            echo "${ctr} ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
            ((ctr+=1))
	 ;;
	 wcoss2)  
            echo "${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
	 ;;
      esac
   done 
   cat $cmdfile
   chmod 755 $cmdfile

   echo "ctr: $ctr"
   echo "submitting job ${jobname}"
   exit

   if [[ ${ctr} > 0 ]]; then
      case ${MACHINE_ID} in
         hera)
	    ${SUB} --account ${ACCOUNT}  --ntasks=1 --mem=400M --time=0:05:00 \
	           -J ${jobname} --partition service -o ${logfile} ${cmdfile}
         ;;

	 wcoss2)  
	    ${SUB} -q $JOB_QUEUE -A $ACCOUNT -o ${logfile} -e ${logfile} \
		 -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, COMOUT=${COMOUT}, \
		     MODEL=${MODEL}, PDY=${PDY}, cyc=${cyc}, DATAROOT=${DATAROOT}, APRUN_PY=${APRUN_PY}, \
		     MACHINE_ID=${MACHINE_ID}" \
		 -l select=1:mem=500M -l walltime=0:10:00 -N ${jobname} ${cmdfile}
         ;;
      esac
   fi

#   if [[ ${ctr} > 0 ]]; then
#      $SUB --account ${ACCOUNT} -n ${ctr}  -o ${logfile} -D . -J ${jobname} --time=1:00:00 \
#           --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}"
#   fi

fi

#------------------------------------------------------------------
# Submit OM_min_plots job if split yields a minimization.yaml file
#
if compgen -G "${DATA}/minimization.yaml" > /dev/null; then

   jobname="OM_min_plots"
   echo "submitting job ${jobname}"
   logfile="${OM_LOGS}/${MODEL}/OM_min_plot.log"

   if [[ -e ${logfile} ]]; then rm ${logfile}; fi
   cmdfile="OM_min_jobscript"

   case ${MACHINE_ID} in
      hera)
         echo "0 ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${DATA}/minimization.yaml  -p ${PDATE}" > $cmdfile
#        chmod 755 $cmdfile
         ${SUB} --account ${ACCOUNT} -n 1  -o ${logfile} -D . -J ${jobname} --time=0:05:00 \
              --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}"
      ;;
      wcoss2)
         echo "${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${DATA}/minimization.yaml  -p ${PDATE}" > $cmdfile
#        chmod 755 $cmdfile
         ${SUB} -q ${JOB_QUEUE} -A ${ACCOUNT} -o ${logfile} -e ${logfile} \
	        -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, COMOUT=${COMOUT}, \
	            MODEL=${MODEL}, DATAROOT=${DATAROOT}, APRUN_PY=${APRUN_PY}, MACHINE_ID=${MACHINE_ID}" \
		-l select=1:mem=500M -l walltime=0:10:00 -N ${jobname} ${cmdfile}
      ;;
   esac
fi

#------------------------------------------------------------------
# Submit OM_con_plots job if split yields any obs_*.yaml files
#
if compgen -G "${DATA}/obs*.yaml" > /dev/null; then
   echo "have OBS plots"
   jobname="OM_obs_plots"
   logfile="${OM_LOGS}/${MODEL}/OM_obs_plot.log"
   if [[ -e ${logfile} ]]; then rm ${logfile}; fi

   cmdfile="OM_obs_jobscript"
   >$cmdfile
   ctr=0

   for yaml in ${DATA}/obs*.yaml; do
      echo "${ctr} $yaml"
      echo "${ctr} ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
      ((ctr+=1))
   done 
   chmod 755 $cmdfile

   echo "ctr: $ctr"
   echo "submitting job ${jobname}"

   if [[ ${ctr} > 0 ]]; then
      $SUB --account ${ACCOUNT} -n ${ctr}  -o ${logfile} -D . -J ${jobname} --time=1:00:00 \
           --mem=80000M --wrap "srun -l --multi-prog ${cmdfile}"
   fi
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


