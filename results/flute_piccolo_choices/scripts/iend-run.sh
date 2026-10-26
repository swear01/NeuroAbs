#!/bin/bash
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=$PWD/tmp
for m in piccolo-ADDI-iend-B0 flute-ADD-iend-P1; do
  /usr/bin/time -f "%e s" -o $m.time taskset -c 4-7 $RIC3_BIN check --ui false --cex $m.btor2 portfolio --time-limit 7200 > $m.ric3.log 2>&1
done
