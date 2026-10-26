#!/bin/bash
# Copies the small result artifacts into the repository results folder.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
O=/home/swear01/.agent-worktrees/NeuroAbs-fine-gpr/results/fine_gpr_choices
mkdir -p $O/scripts $O/piccolo
cp $RUN/scripts/*.sh $RUN/scripts/*.py $O/scripts/
cp $RUN/q1.txt $RUN/q2.txt $RUN/q3.txt $O/scripts/
for c in ADDI LUI AUIPC JAL ANDI SLTI; do
  d=$RUN/piccolo-$c; [ -d $d ] || continue
  mkdir -p $O/piccolo/$c
  for f in units.json uf.json screen.log subs-sample.json specs-auto-sample.jsonl specs-llm-sample.jsonl specs-structural.jsonl specs-structural-sample.jsonl specs-llm.jsonl; do [ -s $d/$f ] && cp $d/$f $O/piccolo/$c/; done
  [ -s $d/llm/decisions.jsonl ] && python3 -c "
import json, sys
with open('$O/piccolo/$c/llm-decisions.jsonl', 'w') as o:
    for l in open('$d/llm/decisions.jsonl'):
        r = json.loads(l)
        o.write(json.dumps({k: r[k] for k in ('name', 'assignment', 'spec', 'probabilities', 'errors', 'served_model', 'usage', 'elapsed_seconds')}) + '\n')
"
  [ -s $d/b0/b0.json ] && cp $d/b0/b0.json $O/piccolo/$c/
  for a in $d/arm-*/; do [ -s $a/results.jsonl ] && cp $a/results.jsonl $O/piccolo/$c/$(basename $a).jsonl; done
  for s in $d/screen/*/; do [ -s $s/cegar.json ] && python3 -c "
import json
r = json.load(open('$s/cegar.json'))
for h in r['history']:
    for k in ('model',): h.pop(k, None)
json.dump(r, open('$O/piccolo/$c/screen-$(basename $s).json', 'w'), indent=1)
"; done
done
exit 0
