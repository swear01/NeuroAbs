#!/bin/bash
# flute-arms.sh <cpus> <arm>...: CEGAR on Flute ADD ILA from the all-cut start (P-cores, screening only, 300 s per model).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
R=~/.agent-worktrees/NeuroAbs-llm-refine
cpus=$1; shift
export RIC3_TMP_DIR=$RUN/.ric3tmp-flute; mkdir -p $RIC3_TMP_DIR
d=$RUN/flute/ADD
for arm in "$@"; do
  [ -s $d/arms/$arm/cegar.json ] && continue
  mkdir -p $d/arms
  LLM_BUDGET_USD=1 taskset -c $cpus python3 $R/src/choice_abstraction.py cegar --wrapper $R/Flute_verification_done/ADD/wrapper.v \
    --prop ila --workdir $d/arms/$arm --models $d/models --units $d/units.json --assignment coarsest \
    --time-limit 300 --max-iterations 10 --refine ${arm%-*} --description $R/Flute_verification_done/ADD/description.txt \
    > $d/arms/$arm.log 2>&1
  echo "$arm $(tail -1 $d/arms/$arm.log)"
done
