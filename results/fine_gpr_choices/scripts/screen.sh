#!/bin/bash
# screen.sh <cpus> <case> <name> <time-limit> <max-iter> <spec-json>: one sub-property spec with rIC3 (+CEGAR).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
R=/home/swear01/.agent-worktrees/NeuroAbs-fine-gpr
cpus=$1; case=$2; name=$3; limit=$4; iters=$5; spec=$6
d=$RUN/piccolo-$case/screen/$name
mkdir -p $d
echo "$spec" > $d/spec.json
export RIC3_TMP_DIR=$RUN/.ric3tmp/$case-$name; mkdir -p $RIC3_TMP_DIR
taskset -c $cpus python3 $R/src/fine_choice.py cegar --wrapper $R/Piccolo_verification_done/$case/wrapper.v \
  --units $RUN/piccolo-$case/units.json --spec $d/spec.json --workdir $d --time-limit $limit --max-iterations $iters > $d/out.log 2>&1
echo "$name $(cat $d/out.log | tail -1)" >> $RUN/piccolo-$case/screen.log
