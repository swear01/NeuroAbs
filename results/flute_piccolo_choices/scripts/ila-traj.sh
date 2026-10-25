#!/bin/bash
# Refinement trajectories for Piccolo ADDI ILA with --refine one (P-cores, 600 s per model).
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp-p
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
W=$R/Piccolo_verification_done/ADDI/wrapper.v
d=choice/piccolo-ADDI-ila
taskset -c 8-15 python3 $R/src/choice_abstraction.py cegar --wrapper $W --prop ila --workdir $d/llm-one \
  --units $d/units.json --assignment $d/llm-deepseek/assignment.json --time-limit 600 --max-iterations 1 --refine one > $d/llm-one.log 2>&1
taskset -c 8-15 python3 $R/src/choice_abstraction.py cegar --wrapper $W --prop ila --workdir $d/coarsest-one \
  --units $d/units.json --assignment coarsest --time-limit 600 --max-iterations 6 --refine one > $d/coarsest-one.log 2>&1
touch $d/traj.done
