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
# Submit OM_plots job if split yields any *.yaml files
#
if compgen -G "${DATA}/*.yaml" > /dev/null; then

   jobname="OM_plot_all"
   export logfile="${OM_LOGS}/${MODEL}/OM_plot.log"
   if [[ -e ${logfile} ]]; then rm ${logfile}; fi

   cmdfile="OM_sat_jobscript"
   >$cmdfile

   ctr=0
   for yaml in ${DATA}/*.yaml; do
      case ${MACHINE_ID} in
         hera)
            echo "${ctr} ${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
	 ;;
 	 wcoss2)  
            echo "${APRUN_PY} ${USHobsmon}/plotObsMon.py -i ${yaml}  -p ${PDATE}" >> $cmdfile
  	 ;;
      esac
      ((ctr+=1))
   done 


   if (( ${ctr} > 0 )); then
      case ${MACHINE_ID} in
         hera)
	    ${SUB} --account ${ACCOUNT}  --ntasks=1 --mem=80000M --time=0:50:00 \
	           -J ${jobname} --partition service -o ${logfile} ${cmdfile}
         ;;

	 wcoss2)  
            chmod 775 ${cmdfile}
            mem=$((4*${ctr})) 
            echo "submitting ${jobname} on wcoss2, ctr = $ctr, mem = $mem, cmdfile = ${cmdfile}"
	    cp ${USHobsmon}/runWcoss.sh .
	    ${SUB} -q $JOB_QUEUE -A $ACCOUNT -o ${logfile} -e ${logfile} \
	        -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, MODEL=${MODEL}, \
		    CNTRLobsmon=${CNTRLobsmon}, PARMobsmon=${PARMobsmon}, DATA=${DATA}, \
		    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}, cmdfile=${cmdfile}, ncpus=${ctr}" \
                -l place=vscatter,select=1:ncpus=${ctr}:mem=${mem}gb,walltime=1:30:00 -N ${jobname} ./runWcoss.sh
         ;;     
      esac
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


