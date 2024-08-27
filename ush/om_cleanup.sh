#!/bin/bash

# om_cleanup.sh
#
#    1.  Sync image files with $COMOUTplots directory
#    2.  Conditionally remove temp working space
#

echo "Begin om_cleanup.sh"; echo

img_dirs=`ls -d ./*_plots/`
for dir in $img_dirs; do
   echo "syncing ${DATA}/${dir} and ${COMOUTplots}/${dir}"
   rsync -a ${DATA}/${dir} ${COMOUTplots}/${dir} 
done

if [ ${KEEPDATA} = NO ] ; then
   echo; echo "removing temp working space ${DATAROOT}/${NET}"; echo
   rm -rf ${DATAROOT}/${NET}
fi

echo "End om_cleanup.sh"; echo 
