#!/bin/bash
# Waits for the 64 sample decisions, writes the LLM specs and starts the LLM arm on E-cores 28-31.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
cd $RUN/piccolo-ADDI
until [ -s llm/decisions.jsonl ] && [ $(wc -l < llm/decisions.jsonl) -ge 64 ]; do sleep 10; done
python3 -c "
import json
with open('specs-llm-sample.jsonl','w') as o:
  for l in open('llm/decisions.jsonl'):
    d=json.loads(l); o.write(json.dumps({'name':d['name'],'spec':d['spec']})+'\n')"
[ -e arm-llm-sample.done ] || $RUN/scripts/arm.sh ADDI llm-sample $RUN/piccolo-ADDI/specs-llm-sample.jsonl 28-29/30-31 300 10
