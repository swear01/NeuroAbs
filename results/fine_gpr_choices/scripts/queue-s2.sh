#!/bin/bash
# After the JAL LLM arm (queue-e1): JAL structural arm on E-cores 28-31 (LUI and AUIPC run in queue-p2).
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-JAL/arm-llm.done ]; do sleep 30; done
$RUN/scripts/arm.sh JAL structural $RUN/piccolo-JAL/specs-structural.jsonl 28-29/30-31 300 10
