#!/bin/bash
# neg.sh <name> <spec>: negated x5 conjunct on the derived model; SAT shows that matching traces survive the abstraction.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
export RIC3_TMP_DIR=$RUN/.ric3tmp/neg-$1; mkdir -p $RIC3_TMP_DIR
cd $RUN/sanity-neg || exit 1; echo "$2" > $1.json
taskset -c 4-7 python3 /home/swear01/.agent-worktrees/NeuroAbs-fine-gpr/src/fine_choice.py cegar --wrapper wrapper_neg.v \
  --units $RUN/piccolo-ADDI/units.json --spec $1.json --workdir $1 --time-limit 300 > $1.log 2>&1
