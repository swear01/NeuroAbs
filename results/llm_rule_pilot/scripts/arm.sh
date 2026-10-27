#!/bin/bash
# arm.sh <case> <arm> <specs.jsonl> <cpu groups>: fine_batch CEGAR with the limits of the S arm (300 s, 10 refinements).
. "$(dirname "$0")/env.sh"
d=$RUN/piccolo-$1
mkdir -p $d
python3 $R/src/fine_batch.py --wrapper $R/Piccolo_verification_done/$1/wrapper.v --units $P/$1/units.json \
  --specs $3 --workdir $d/arm-$2 --cpus $4 --time-limit 300 --max-iterations 10 >> $d/arm-$2.log 2>&1
