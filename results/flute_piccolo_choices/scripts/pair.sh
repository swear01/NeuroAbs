#!/bin/bash
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp-p
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
d=choice/piccolo-ADDI-ila
taskset -c 8-15 python3 $R/src/choice_abstraction.py cegar --wrapper $R/Piccolo_verification_done/ADDI/wrapper.v --prop ila \
  --workdir $d/pair --units $d/units.json --assignment $d/oracle-pair.json --time-limit 3600 --max-iterations 0 > $d/pair.log 2>&1
