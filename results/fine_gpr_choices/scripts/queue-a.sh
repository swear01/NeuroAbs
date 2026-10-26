#!/bin/bash
# After the B0 runs (queue-e2): auto arm on seven sub-properties of LUI, AUIPC and JAL, E-cores 24-27.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -s $RUN/piccolo-JAL/b0/b0.json ]; do sleep 30; done
for c in LUI AUIPC JAL; do $RUN/scripts/arm.sh $c auto-sample $RUN/piccolo-$c/specs-auto-sample.jsonl 24-25/26-27 300 10; done
