#!/bin/bash
# repeat.sh: three alternating split-only / S rounds on the seven sampled LUI and JAL sub-properties,
# each on the CPU group of its S arm once the earlier arms there are done.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
# after <case/arm> <earlier case/arm>...: wait for the first arm; stop if it or an arm of its chain failed.
after() {
  while [ ! -e $RUN/piccolo-${1%/*}/arm-${1#*/}.done ]; do
    for a in "$@"; do
      [ -e $RUN/piccolo-${a%/*}/arm-${a#*/}.failed ] && { echo "$a failed; not starting rounds after $1" >&2; exit 1; }
    done
    sleep 60
  done
}
rounds() {
  for i in 1 2 3; do
    $S/arm.sh $1 rep-split-$i $RUN/piccolo-$1/specs-rep-split.jsonl $2 300 0
    $S/arm.sh $1 rep-s-$i $RUN/piccolo-$1/specs-rep-s.jsonl $2 300 10
  done
}
(after AUIPC/split LUI/split; rounds LUI 12-13/14-15) & l=$!
(after ADDI/split-long JAL/split; rounds JAL 28-29/30-31) & j=$!
rc=0; wait $l || rc=1; wait $j || rc=1; exit $rc
