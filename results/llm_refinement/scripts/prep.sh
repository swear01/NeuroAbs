#!/bin/bash
# Units of the ILA property for every Piccolo case (P-cores, untimed), sized on the B0 models of the PR #14 run.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
OLD=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
R=~/.agent-worktrees/NeuroAbs-llm-refine
for c in $(cat $RUN/cases.txt); do
  d=$RUN/piccolo/$c; mkdir -p $d
  [ -s $d/units.json ] && [ $c != ADDI ] || taskset -c 8-11 python3 $R/src/choice_abstraction.py units \
    --wrapper $R/Piccolo_verification_done/$c/wrapper.v --prop ila --workdir $d/units-work --b0 $OLD/piccolo/$c/b0_ila.btor2 > $d/units.json
  echo $c $(python3 -c "import json; print([(u['id'], u['coi_state_bits'], u['levels']) for u in json.load(open('$d/units.json'))])")
done
