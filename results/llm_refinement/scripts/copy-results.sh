#!/bin/bash
# Copies the small result artifacts into the repository results folder.
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
O=~/.agent-worktrees/NeuroAbs-llm-refine/results/llm_refinement
mkdir -p $O/scripts
cp $RUN/scripts/*.sh $RUN/scripts/*.py $RUN/cases.txt $O/scripts/
cp $RUN/piccolo/ADDI/units.json $O/piccolo-units.json
for c in $(cat $RUN/cases.txt); do
  d=$O/piccolo/$c; mkdir -p $d
  cp $RUN/piccolo/$c/{ground_truth.json,screen.jsonl,evaluation.json} $d/
  for a in $RUN/piccolo/$c/arms/*/; do
    n=$(basename $a); mkdir -p $d/$n; cp $a/cegar.json $d/$n/
    cp $a/refine-iter*.json $d/$n/ 2>/dev/null
  done
done
cp $RUN/piccolo/ADDI/screen.600s.jsonl $O/piccolo/ADDI/
mkdir -p $O/flute/ADD; cp $RUN/flute/ADD/units.json $O/flute/ADD/
for a in $RUN/flute/ADD/arms/*/; do n=$(basename $a); mkdir -p $O/flute/ADD/$n; cp $a/cegar.json $O/flute/ADD/$n/; cp $a/refine-iter*.json $O/flute/ADD/$n/ 2>/dev/null; done
mkdir -p $O/final; cp $RUN/final/summary.txt $O/final/ 2>/dev/null
# Absolute run-directory paths in the copied JSON stay as recorded.
