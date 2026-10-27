#!/bin/bash
# job.sh <case> <batch>: fine_batch CEGAR (300 s per model, at most 10 refinements) on the 3 CPU groups of mazu (P-cores 0-11) for
# $RUN/batches/<case>/<batch>.jsonl; results in $RUN/runs/<case>/<batch>/results.jsonl.
set -euo pipefail
. "$(dirname "$0")/env.sh"
[ "$(hostname)" = mazu ] || { echo "timed runs only on mazu" >&2; exit 1; }
python3 $R/src/fine_batch.py --wrapper $RUN/problems/$1/wrapper.v --units $H/problems/$1/units.json \
  --specs $RUN/batches/$1/$2.jsonl --workdir $RUN/runs/$1/$2 --cpus $CPUS --time-limit 300 --max-iterations 10
