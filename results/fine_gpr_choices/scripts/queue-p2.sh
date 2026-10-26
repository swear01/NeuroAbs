#!/bin/bash
# Structural arms of LUI and AUIPC on the idle P-cores (queue-s skips sub-properties already done).
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
for c in LUI AUIPC; do $RUN/scripts/arm.sh $c structural $RUN/piccolo-$c/specs-structural.jsonl 12-13/14-15 300 10; done
