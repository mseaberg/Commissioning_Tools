#!/bin/env bash
source /reg/g/pcds/pyps/apps/hutch-python/xcs/xcsenv
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/Python/lcls_beamline_toolbox

HERE=`dirname $(readlink -f $0)`

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM1L0"
fi

python $HERE/../run_interface.py -c $IMAGER &
