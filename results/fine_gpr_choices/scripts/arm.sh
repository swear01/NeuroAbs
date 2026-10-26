#!/bin/bash
# arm.sh <case> <arm> <specs.jsonl> <cpu groups> <time-limit> <max-iterations>
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
R=/home/swear01/.agent-worktrees/NeuroAbs-fine-gpr
d=$RUN/piccolo-$1
mkdir -p $d; rm -f $d/arm-$2.done $d/arm-$2.failed
if python3 $R/src/fine_batch.py --wrapper $R/Piccolo_verification_done/$1/wrapper.v --units $d/units.json \
  --specs $3 --workdir $d/arm-$2 --cpus $4 --time-limit $5 --max-iterations $6 > $d/arm-$2.log 2>&1; then
  touch $d/arm-$2.done
else
  touch $d/arm-$2.failed; exit 1
fi
