#!/bin/bash
# arm.sh <case> <arm> <specs.jsonl> <cpu groups> <time-limit> <max-iterations>
set -euo pipefail
[ $# -eq 6 ] || { echo "usage: $0 <case> <arm> <specs.jsonl> <cpu groups> <time-limit> <max-iterations>" >&2; exit 2; }
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/split-baseline-20261026
OLD=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
R=$(cd "$(dirname "$0")/../../.." && pwd)
d=$RUN/piccolo-$1
mkdir -p "$d"; rm -f "$d/arm-$2.done" "$d/arm-$2.failed"
trap '[ -e "$d/arm-$2.done" ] || touch "$d/arm-$2.failed"' EXIT
python3 "$R/src/fine_batch.py" --wrapper "$R/Piccolo_verification_done/$1/wrapper.v" --units "$OLD/piccolo-$1/units.json" \
  --specs "$3" --workdir "$d/arm-$2" --cpus "$4" --time-limit "$5" --max-iterations "$6" >> "$d/arm-$2.log" 2>&1
cp "$d/arm-$2/results.jsonl" "$d/arm-$2.jsonl"
touch "$d/arm-$2.done"
