#!/bin/bash
# enqueue.sh <case> <batch> <job name> <arm>...: specs of the arms on the sampled sub-properties of <case> (an LLM arm
# <model>-<i> is the rule $H/rules/<model>/rule-<i>.py), merged into $RUN/batches/<case>/<batch>.jsonl, and a queue
# job <job name> that runs the batch.  Specs are made on the spare CPUs 18-19.
set -euo pipefail
. "$(dirname "$0")/env.sh"
case=$1 batch=$2 job=$3
shift 3
mkdir -p $RUN/specs/$case $RUN/batches/$case $RUN/queue/pending
for a in "$@"; do
  case $a in
    split|S|auto) src=$a ;;
    *) src=$H/rules/${a%-*}/rule-${a##*-}.py ;;
  esac
  taskset -c 18,19,38,39 python3 $H/scripts/specs.py $RUN $case $src $RUN/specs/$case/$a.jsonl
done
python3 $H/scripts/batch.py $RUN/specs/$case $RUN/batches/$case/$batch.jsonl $RUN/batches/$case/$batch.map.json "$@"
printf '%s %s\n' $case $batch > $RUN/queue/$job.tmp
mv $RUN/queue/$job.tmp $RUN/queue/pending/$job
