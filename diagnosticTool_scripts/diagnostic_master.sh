#!/bin/bash

#$ -cwd
#$ -j yes
#$ -pe smp 4
export PATH=/home/ae42909/Programs/Kraken/kraken-0.10.5-beta/builddir:/mnt/apps/jellyfish/1.1.11/bin:$PATH

python /home/ae42909/scripts/diagnosticTool_scripts/diagnostic_master.py