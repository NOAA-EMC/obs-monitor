#!/bin/bash

# -----------------------------------------------------
#  runObsMon.sh
#
#  This is a driver script to run the plotObsMon job.
# -----------------------------------------------------

#--------------------------------------------------------------------
#  usage
#--------------------------------------------------------------------
function usage {
  echo "Usage:  runObsMon.sh -p|--pdate pdate -m|--model, [-r|--run]"
  echo "            -p | --pdate 	cycle time to be processed, format yyyymmddhh"
  echo "              			if unspecified the last available date will be processed"
  echo "            -m | --model	model or experiment name (i.e. gfs, nam)"
  echo "	    -r | --run		optional, name of run (i.e. gfs, gdas)"
  echo " "
}


echo begin runObsMon.sh

nargs=$#
echo nargs: $nargs
if [[ ${nargs} -lt 4 || ${nargs} -gt 6 ]]; then
   usage
   exit 1
fi


#-----------------------------------------------
#  Process command line arguments
#

pdate=""
model=""
run=""

while [[ $# -ge 1 ]]
do
   key="$1"
   echo ${key}

   case ${key} in
      -p|--pdate)
         pdate="$2"
         shift # past argument
      ;;
      -m|--model)
         model="$2"
         shift # past argument
      ;;
      -r|--run)
         run="$2"
         shift # past argument
      ;;
   esac

   shift
done

echo pdate: $pdate
echo model: $model
echo run:   $run

export PDY=`echo ${pdate}|cut -c1-8`
export cyc=`echo ${pdate}|cut -c9-10`
export NET=obsmon
export MODEL=${model}
export RUN=${run}
export KEEPDATA="YES"

#--------------------------------
# locate and source config file
#
readonly dir_root=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )/.." && pwd -P)
om_config=${dir_root}/parm/OM_config
source ${om_config}

#-----------------------------
# define plot output location
#
export COMOUT=${COMOUT}/${NET}

#-------------------------
#  Set up & submit j-job
#
jobname="PlotObsMon"
jobfile="${JOBSobsmon}/JMON_PLOT_OBS"

logdir="${OM_LOGS}/${MODEL}"
if [[ ! -d ${logdir} ]]; then mkdir -p ${logdir}; fi

logfile="${OM_LOGS}/${MODEL}/OM_log"
if [[ -e ${logfile} ]]; then rm ${logfile}; fi

case ${MACHINE_ID} in
   hera)
      ${SUB} --account ${ACCOUNT}  --ntasks=1 --mem=400M --time=0:05:00 \
             -J ${jobname} --partition service -o ${logfile} ${jobfile}
      ;;

   wcoss2)	# NOTE:  this has not been tested; eva doesn't yet run on wcoss2
      $SUB -q $JOB_QUEUE -A $ACCOUNT -o ${logfile} -e ${logfile} \
           -V -l select=1:mem=500M -l walltime=0:05:00 -N ${jobname} ${jobfile}
      ;;
esac

echo end runObsMon.sh
