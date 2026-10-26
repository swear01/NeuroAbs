#!/bin/bash
# Screens Piccolo ADDI sanity choices on the P-cores (not timed for the paper comparison).
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp-p
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
W=$R/Piccolo_verification_done/ADDI/wrapper.v
d=choice/piccolo-ADDI-sanity
taskset -c 8-15 ./single.sh $d $W sanity 300 > $d/single.jsonl 2> $d/single.err
for arm in coarsest llm; do
  a=coarsest; [ $arm = llm ] && a=$d/llm-deepseek/assignment.json
  taskset -c 8-15 python3 $R/src/choice_abstraction.py cegar --wrapper $W --prop sanity --workdir $d/$arm-one \
    --units $d/units.json --assignment $a --time-limit 600 --refine one > $d/$arm-one.log 2>&1
done
touch $d/done
