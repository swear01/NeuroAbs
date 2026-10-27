#!/bin/bash
# batch.sh <case> <batch> <specs.jsonl> <cpu groups> <time-limit> <max-iterations>: run fine_batch.py on one Piccolo case.
# The wrapper is $RUN/piccolo-<case>/wrapper.v if that exists (SB-named), else the repo wrapper of <case>.
set -euo pipefail
[ $# -eq 6 ] || { echo "usage: $0 <case> <batch> <specs.jsonl> <cpu groups> <time-limit> <max-iterations>" >&2; exit 2; }
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/semantic-cand-20261027
R=$(cd "$(dirname "$0")/../../.." && pwd)
d=$RUN/piccolo-$1
w=$R/Piccolo_verification_done/$1/wrapper.v; [ -e "$d/wrapper.v" ] && w=$d/wrapper.v
trap '[ -e "$d/$2.done" ] || touch "$d/$2.failed"' EXIT
mkdir -p "$d"; rm -f "$d/$2.done" "$d/$2.failed"
python3 "$R/src/fine_batch.py" --wrapper "$w" --units "$d/units.json" \
  --specs "$3" --workdir "$d/$2" --cpus "$4" --time-limit "$5" --max-iterations "$6" >> "$d/$2.log" 2>&1
cp "$d/$2/results.jsonl" "$d/$2.jsonl"
touch "$d/$2.done"
