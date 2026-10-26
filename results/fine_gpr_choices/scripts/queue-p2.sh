#!/bin/bash
# After queue-p (its last screen is Q-whole-ack-long): structural arms of LUI and AUIPC on the P-cores.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until grep -q '^Q-whole-ack-long ' $RUN/piccolo-ADDI/screen.log 2>/dev/null; do sleep 30; done
for c in LUI AUIPC; do $RUN/scripts/arm.sh $c structural $RUN/piccolo-$c/specs-structural.jsonl 12-13/14-15 300 10; done
