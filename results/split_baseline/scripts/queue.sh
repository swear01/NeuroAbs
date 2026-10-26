#!/bin/bash
# queue.sh: the split-only arms on the CPU groups of the matching S arms, then the ADDI no-UF ablation.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
($S/arm.sh ADDI split $RUN/piccolo-ADDI/specs-split.jsonl 24-25/26-27 300 0
 $S/arm.sh ADDI no-uf $RUN/piccolo-ADDI/specs-no-uf.jsonl 24-25/26-27 300 10) &
$S/arm.sh JAL split $RUN/piccolo-JAL/specs-split.jsonl 28-29/30-31 300 0 &
($S/arm.sh LUI split $RUN/piccolo-LUI/specs-split.jsonl 12-13/14-15 300 0
 $S/arm.sh AUIPC split $RUN/piccolo-AUIPC/specs-split.jsonl 12-13/14-15 300 0) &
wait
