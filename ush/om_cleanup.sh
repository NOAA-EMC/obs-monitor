#!/bin/bash

# ---------------------------------------------
# Sync image files with $COMOUTplots directory
# 
img_dirs=`ls -d ${DATA}/*_plots/`
for dir in $img_dirs; do
   echo "syncing ${dir} and ${COMOUTplots}/${dir}"
   base_name=$(basename ${dir})
   rsync -a ${dir} ${COMOUTplots}/${base_name} 
done

# ---------------------------------------------
# Conditionally remove temp working space
#
if [[ ${KEEPDATA} == "NO" ]]; then
   echo; echo "removing temp working space ${DATAROOT}/${NET}"; echo
   rm -rf ${DATAROOT}/${NET}
fi
