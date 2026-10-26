#!/bin/bash
# smoke.sh <refine>: CEGAR on Piccolo ADDI ILA from the all-cut start (P-cores, 120 s per model).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
export RIC3_TMP_DIR=$RUN/.ric3tmp-p; mkdir -p $RIC3_TMP_DIR
R=~/.agent-worktrees/NeuroAbs-llm-refine
c=ADDI; d=$RUN/smoke/$c; mkdir -p $d
LLM_BUDGET_USD=1 taskset -c 8-11 python3 $R/src/choice_abstraction.py cegar --wrapper $R/Piccolo_verification_done/$c/wrapper.v \
  --prop ila --workdir $d/$1 --models $d/models --units $RUN/piccolo/$c/units.json --assignment coarsest \
  --time-limit 120 --max-iterations 6 --refine $1 --description $R/Piccolo_verification_done/$c/description.txt
