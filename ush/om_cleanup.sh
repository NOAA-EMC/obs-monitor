#!/bin/bash

echo "NET: $NET"
echo "RUN: $RUN"
echo "DATA: $DATA"
echo "COMOUTplots: $COMOUTplots"

# ---------------------------------------------
# Sync image files with $COMOUTplots directory
# 
img_dirs=`ls -d ${DATA}/*/*plots/`

for dir in $img_dirs; do

   base_name=$(basename ${dir})
   destination=${COMOUTplots}/${base_name}
   echo "syncing ${dir} and ${destination}"
   echo ""

   rsync -a ${dir} ${destination} 
done

# ---------------------------------------------
# Conditionally remove temp working space
#
if [[ ${KEEPDATA} == "NO" ]]; then
   echo; echo "removing temp working space ${DATAROOT}/${NET}"; echo
   rm -rf ${DATAROOT}/${NET}
fi
