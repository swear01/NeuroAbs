#!/bin/bash
# long.sh: four ADDI write cases on the unabstracted model for 1800 s, after the JAL split arm frees CPUs 28-31.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
while [ ! -e $RUN/piccolo-JAL/arm-split.done ]; do sleep 60; done
$S/arm.sh ADDI split-long $RUN/piccolo-ADDI/specs-split-long.jsonl 28-29/30-31 1800 0
