#!/bin/bash
# repeat.sh: three alternating split-only / S rounds on the seven sampled LUI and JAL sub-properties,
# each on the CPU group of its S arm once the earlier arms there are done.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
after() {
  while [ ! -e $RUN/piccolo-$1/arm-$2.done ]; do [ -e $RUN/piccolo-$1/arm-$2.failed ] && exit 1; sleep 60; done
}
rounds() {
  for i in 1 2 3; do
    $S/arm.sh $1 rep-split-$i $RUN/piccolo-$1/specs-rep-split.jsonl $2 300 0
    $S/arm.sh $1 rep-s-$i $RUN/piccolo-$1/specs-rep-s.jsonl $2 300 10
  done
}
(after AUIPC split; rounds LUI 12-13/14-15) & l=$!
(after ADDI split-long; rounds JAL 28-29/30-31) & j=$!
wait $l; wait $j
