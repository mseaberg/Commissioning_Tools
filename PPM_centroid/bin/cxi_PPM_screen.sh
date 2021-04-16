#!/bin/env bash
source /reg/g/pcds/pyps/apps/hutch-python/cxi/cxienv
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/Python/lcls_beamline_toolbox

cd /cds/home/s/seaberg/dev/Commissioning_Tools/PPM_centroid

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM1L0"
fi

python run_interface.py -c $IMAGER &
