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
  echo "Usage:  runObsMon.sh -p|--pdate pdate -m|--model, [-y|--yaml]"
  echo "            -p | --pdate 	cycle time to be processed, format yyyymmddhh."
  echo "              			If unspecified the last available date will be processed."
  echo "            -m | --model	model or experiment name (i.e. gfs, exp1, etc.)"
  echo "            -y | --yaml 	yaml plot file, with full or relative path."
  echo "                                If no yaml file is specified the default is "
  echo "                                parm/[model]/[model]_plot.yaml"
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
yaml_file=""

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
      -y|--yaml)
         yaml_file="$2"
         shift # past argument
      ;;
   esac

   shift
done

echo pdate: $pdate
echo model: $model

if [ -n "${yaml_file}" ]; then 
   if  [ ! -e ${yaml_file} ]; then
      echo "ERROR:  input yaml file ${yaml_file} not found"
      exit 1 
   fi
   yaml_file=`realpath ${yaml_file}`
fi
echo yaml_file:  $yaml_file

export PDY=`echo ${pdate}|cut -c1-8`
export cyc=`echo ${pdate}|cut -c9-10`
export NET=obsmon
export MODEL=${model}
export YAML_FILE=${yaml_file}
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
jobname="PlotObsMon_setup"
jobfile="${JOBSobsmon}/JMON_PLOT_OBS"

logdir="${OM_LOGS}/${MODEL}"
if [[ ! -d ${logdir} ]]; then mkdir -p ${logdir}; fi

logfile="${logdir}/OM_setup.log"
if [[ -e ${logfile} ]]; then rm ${logfile}; fi

case ${MACHINE_ID} in
   hera|orion|hercules)
      ${SUB} --account ${ACCOUNT}  --ntasks=1 --mem=400M --time=0:05:00 \
             -J ${jobname} --partition service -o ${logfile} ${jobfile}
      ;;

   wcoss2)	
      $SUB -q ${JOB_QUEUE} -A ${ACCOUNT} -o ${logfile} -e ${logfile} \
	   -v "PYTHONPATH=${PYTHONPATH}, PATH=${PATH}, HOMEobsmon=${HOMEobsmon}, COMOUT=${COMOUT}, \
	       MODEL=${MODEL}, PDY=${PDY}, cyc=${cyc}, DATAROOT=${DATAROOT}, APRUN_PY=${APRUN_PY}, \
	       MACHINE_ID=${MACHINE_ID}, ACCOUNT=${ACCOUNT}, JOB_QUEUE=${JOB_QUEUE}, SUB=${SUB}, \
	       OM_LOGS=${OM_LOGS}, YAML_FILE=${YAML_FILE}, CARTOPY_DATA_DIR=${CARTOPY_DATA_DIR}, \
	       OM_PLOTS=${OM_PLOTS}" \
           -l select=1:mem=500mb -l walltime=0:05:00 -N ${jobname} ${jobfile}
      ;;
esac

echo end runObsMon.sh
