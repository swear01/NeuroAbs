#!/bin/bash
# After queue-p: structural arms of LUI and AUIPC on the P-cores.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-ADDI/queue-p.done ]; do [ -e $RUN/piccolo-ADDI/queue-p.failed ] && exit 1; sleep 30; done
for c in LUI AUIPC; do $RUN/scripts/arm.sh $c structural $RUN/piccolo-$c/specs-structural.jsonl 12-13/14-15 300 10; done
