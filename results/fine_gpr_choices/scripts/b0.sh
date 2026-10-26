#!/bin/bash
# b0.sh <case> <cpus> <time-limit>: rIC3 on the concrete ILA model B0 of PR #14.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
OLD=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
export RIC3_TMP_DIR=$RUN/.ric3tmp/b0-$1; mkdir -p $RIC3_TMP_DIR $RUN/piccolo-$1/b0
trap '[ -e $RUN/piccolo-$1/b0/b0.done ] || touch $RUN/piccolo-$1/b0/b0.failed' EXIT
cd $RUN/piccolo-$1/b0 || exit 1; rm -f b0.json b0.done b0.failed
PYTHONPATH=/home/swear01/.agent-worktrees/NeuroAbs-fine-gpr/src taskset -c $2 python3 -c "
import json, choice_abstraction as ca
v, d, s = ca.ric3_check('$OLD/piccolo/$1/b0_ila.btor2', $3, 'ric3.log')
json.dump({'case': '$1', 'ric3': v, 'cex_depth': d, 'ric3_seconds': s,
           'coi_state_bits': sum(ca.coi_state_bits('$OLD/piccolo/$1/b0_ila.btor2').values())}, open('b0.json', 'w'))
" && touch b0.done
