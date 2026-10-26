#!/bin/bash
# After the LLM arms of LUI, AUIPC and JAL (queue-e1): their structural arms on E-cores 28-31.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-JAL/arm-llm.done ]; do sleep 30; done
for c in LUI AUIPC JAL; do $RUN/scripts/arm.sh $c structural $RUN/piccolo-$c/specs-structural.jsonl 28-29/30-31 300 10; done
