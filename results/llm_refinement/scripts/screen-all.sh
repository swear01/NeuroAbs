#!/bin/bash
# screen-all.sh <cpu> <case>...: BMC ground truth, bound 20, one P-core per worker (untimed).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
cpu=$1; shift
export RIC3_TMP_DIR=$RUN/.ric3tmp-p$cpu; mkdir -p $RIC3_TMP_DIR
for c in "$@"; do
  [ -s $RUN/piccolo/$c/ground_truth.json ] && continue
  taskset -c $cpu python3 $RUN/scripts/screen.py $c 20 900 > $RUN/piccolo/$c/screen.log 2>&1
  echo "$c $(cat $RUN/piccolo/$c/ground_truth.json | tr -d '\n ')"
done
