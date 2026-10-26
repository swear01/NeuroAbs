#!/bin/bash
# After full-e1 on E-cores 28-31: LLM arms for LUI, AUIPC and JAL.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
for c in LUI AUIPC JAL; do mkdir -p $RUN/piccolo-$c; rm -f $RUN/piccolo-$c/arm-llm.failed; done
trap 'for c in LUI AUIPC JAL; do [ -e $RUN/piccolo-$c/arm-llm.done ] || touch $RUN/piccolo-$c/arm-llm.failed; done' EXIT
until [ -e $RUN/piccolo-ADDI/arm-full-e1.done ]; do [ -e $RUN/piccolo-ADDI/arm-full-e1.failed ] && exit 1; sleep 30; done
for c in LUI AUIPC JAL; do
  until [ -s $RUN/piccolo-$c/llm/decisions.jsonl ] && [ $(wc -l < $RUN/piccolo-$c/llm/decisions.jsonl) -ge 63 ]; do sleep 30; done
  python3 -c "
import json
with open('$RUN/piccolo-$c/specs-llm.jsonl','w') as o:
  for l in open('$RUN/piccolo-$c/llm/decisions.jsonl'):
    d=json.loads(l); o.write(json.dumps({'name':d['name'],'spec':d['spec']})+'\n')" || exit 1
  $RUN/scripts/arm.sh $c llm $RUN/piccolo-$c/specs-llm.jsonl 28-29/30-31 300 10 || exit 1
done
