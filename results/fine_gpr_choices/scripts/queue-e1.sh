#!/bin/bash
# After full-e1 on E-cores 28-31: LLM arms for LUI, AUIPC and JAL.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-ADDI/arm-full-e1.done ]; do sleep 30; done
for c in LUI AUIPC JAL; do
  until [ $(wc -l < $RUN/piccolo-$c/llm/decisions.jsonl) -ge 63 ]; do sleep 30; done
  python3 -c "
import json
with open('$RUN/piccolo-$c/specs-llm.jsonl','w') as o:
  for l in open('$RUN/piccolo-$c/llm/decisions.jsonl'):
    d=json.loads(l); o.write(json.dumps({'name':d['name'],'spec':d['spec']})+'\n')"
  $RUN/scripts/arm.sh $c llm $RUN/piccolo-$c/specs-llm.jsonl 28-29/30-31 300 10
done
