#!/bin/bash
# arms.sh <cpus> <case>...: CEGAR from the all-cut start with each refinement strategy (E-cores, timed).
# The arms of a case share one models directory, so each assignment is built and checked once.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
R=~/.agent-worktrees/NeuroAbs-llm-refine
cpus=$1; shift
export RIC3_TMP_DIR=$RUN/.ric3tmp-$cpus; mkdir -p $RIC3_TMP_DIR
for c in "$@"; do
  d=$RUN/piccolo/$c
  for arm in one all bmc llm-1 llm-2 llm-3; do
    [ -s $d/arms/$arm/cegar.json ] && continue
    LLM_BUDGET_USD=1 taskset -c $cpus python3 $R/src/choice_abstraction.py cegar --wrapper $R/Piccolo_verification_done/$c/wrapper.v \
      --prop ila --workdir $d/arms/$arm --models $d/models --units $d/units.json --assignment coarsest \
      --time-limit 300 --max-iterations 8 --refine ${arm%-*} --description $R/Piccolo_verification_done/$c/description.txt \
      > $d/arms/$arm.log 2>&1
    echo "$c $arm $(tail -1 $d/arms/$arm.log)"
  done
done
