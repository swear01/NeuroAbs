#!/bin/bash
# full-e-after.sh <sample arm> <part> <cpu groups>: start a part of the full ADDI proof once a sample arm is done.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-ADDI/arm-$1.done ]; do sleep 30; done
$RUN/scripts/arm.sh ADDI full-$2 $RUN/piccolo-ADDI/specs-full-$2.jsonl $3 300 10
