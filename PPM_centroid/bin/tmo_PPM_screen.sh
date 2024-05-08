#!/bin/env bash
source /reg/g/pcds/pyps/apps/hutch-python/tmo/tmoenv
#export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/Python/lcls_beamline_toolbox
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/dev/lcls_beamline_toolbox

HERE=`dirname $(readlink -f $0)`

#cd /cds/home/s/seaberg/dev/Commissioning_Tools/PPM_centroid

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM2K0"
fi

python $HERE/../run_interface.py -c $IMAGER &
