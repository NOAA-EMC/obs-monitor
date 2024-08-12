#!/bin/bash

module reset
module list

module load libfabric/1.11.0.0.
module load PrgEnv-intel/8.3.3
module load craype
module load cray-mpich/8.1.12
module load cray-pals
module load cfp/2.0.4

module load git/2.29.0
module load intel/19.1.3.304
module load netcdf/4.7.4
module load python/3.10.4
module load ve/evs/1.0

module list

export PATH=/lfs/h2/emc/da/noscrub/edward.safford/eva/opt/bin:${PATH}
export PYTHONPATH=/lfs/h2/emc/da/noscrub/edward.safford/eva/opt:${PYTHONPATH}

# cd to working directory from which this was launched
if [ ! -z ${PBS_O_WORKDIR} ]; then cd ${PBS_O_WORKDIR}; fi

mpiexec -np ${ncpus} --cpu-bind core cfp ${cmdfile}
