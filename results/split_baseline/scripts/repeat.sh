#!/bin/bash
# repeat.sh: three alternating split-only / S rounds on the seven sampled LUI and JAL sub-properties,
# each on the CPU group of its S arm once the earlier arms there are done.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
rounds() {
  for i in 1 2 3; do
    $S/arm.sh $1 rep-split-$i $RUN/piccolo-$1/specs-rep-split.jsonl $2 300 0
    $S/arm.sh $1 rep-s-$i $RUN/piccolo-$1/specs-rep-s.jsonl $2 300 10
  done
}
(while [ ! -e $RUN/piccolo-AUIPC/arm-split.done ]; do sleep 60; done; rounds LUI 12-13/14-15) &
(while [ ! -e $RUN/piccolo-ADDI/arm-split-long.done ]; do sleep 60; done; rounds JAL 28-29/30-31) &
wait
