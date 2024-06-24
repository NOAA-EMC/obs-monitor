#!/bin/bash

st=`date`

module reset

module load libfabric/1.11.0.0.
module load PrgEnv-intel/8.3.3
module load craype
module load cray-pals
module load git/2.29.0
module load intel/19.1.3.304
module load python/3.10.4
module load ve/evs/1.0

export PATH=${PATH}:/lfs/h2/emc/da/noscrub/edward.safford/eva/opt/bin
export PYTHONPATH=${PYTHONPATH}:/lfs/h2/emc/da/noscrub/edward.safford/eva/opt/

if [ ! -z ${PBS_O_WORKDIR} ]; then cd ${PBS_O_WORKDIR}; fi

./${cmdfile}

end=`date`
echo "start: ${st}"
echo "end:   ${end}"
