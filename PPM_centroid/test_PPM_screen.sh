#!/bin/env bash
source /cds/home/s/seaberg/beamlineconda.sh
export PYTHONPATH=$PYTHONPATH:/cds/home/s/seaberg/TMO_IP2/lcls_beamline_toolbox

cd /cds/home/s/seaberg/TMO_IP2/Commissioning_Tools/PPM_centroid

if [ $# -eq 1 ]; then
    IMAGER=$1
else
    IMAGER="IM1L0"
fi

python run_interface.py -c $IMAGER &
