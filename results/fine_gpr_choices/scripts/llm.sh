#!/bin/bash
# llm.sh <case> <subs.json> <uf.json> <workdir>: DeepSeek choices for every sub-property (resumable).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
R=/home/swear01/.agent-worktrees/NeuroAbs-fine-gpr
cd $RUN/piccolo-$1
LLM_BUDGET_USD=${LLM_BUDGET_USD:-3} PYTHONPATH=$R/src taskset -c 4-7 python3 $R/src/fine_choice_llm.py --wrapper $R/Piccolo_verification_done/$1/wrapper.v \
  --units units.json --subs $2 --uf $3 --description $R/Piccolo_verification_done/$1/description.txt --workdir $4 >> $4.log 2>&1
