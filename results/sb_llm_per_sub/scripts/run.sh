#!/bin/bash
# run.sh <state> <arm>...: the specs of the arms on the sampled SB sub-properties of <state> (store_en or pc), merged
# into $O/batches/<state>.jsonl by llm_rule_heldout/scripts/batch.py, then fine_batch CEGAR (300 s per model, at most
# 10 refinements) on mazu CPUs 12-15, two runs at a time.  Arms: deepseek and claude (decisions.jsonl of ask.py),
# S and claude-fb2 (the specs that llm_rule_heldout made on zeus, copied to $O/zeus-specs), claude-fb2-rev and S-rev
# (order.py, candidates reversed, in $O/order) and single-<dir> (ask.py --single answers in $O/<dir>).
set -euo pipefail
. /var/tmp/neuroabs-runtime/env-20261024.sh
O=/var/tmp/neuroabs-runtime/runs/sb-llm-per-sub-20261028
R=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
H=$R/results/llm_rule_heldout
export PYTHONPATH=/home/swear01/NeuroAbs/Pyverilog_NeuroAbs:$R/src
[ "$(hostname)" = mazu ] || { echo "runs only on mazu" >&2; exit 1; }
state=$1
shift
mkdir -p $O/specs-$state $O/batches
for a in "$@"; do
  case $a in
    deepseek|claude) python3 -c 'import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r["name"].startswith(sys.argv[2] + "."):
        print(json.dumps({"name": r["name"], "spec": r["spec"]}))' $O/$a/decisions.jsonl $state > $O/specs-$state/$a.jsonl ;;
    S|claude-fb2) grep "\"name\": \"$state\." $O/zeus-specs/$a.jsonl > $O/specs-$state/$a.jsonl ;;
    claude-fb2-rev|S-rev) grep "\"name\": \"$state\." $O/order/${a%-rev}.jsonl > $O/specs-$state/$a.jsonl ;;
    single-*) grep "\"name\": \"$state\." $O/${a#single-}/specs.jsonl > $O/specs-$state/$a.jsonl ;;
    *) echo "unknown arm $a" >&2; exit 1 ;;
  esac
  case $a in
    single-*) ;;
    *) [ "$(wc -l < $O/specs-$state/$a.jsonl)" = 10 ] || { echo "$a: not 10 $state specs" >&2; exit 1; } ;;
  esac
done
python3 $H/scripts/batch.py $O/specs-$state $O/batches/$state.jsonl $O/batches/$state.map.json "$@"
python3 $R/src/fine_batch.py --wrapper /var/tmp/neuroabs-runtime/runs/llm-heldout-20261027/problems/SB/wrapper.v \
  --units $H/problems/SB/units.json --specs $O/batches/$state.jsonl --workdir $O/runs/$state \
  --cpus 12,13/14,15 --time-limit 300 --max-iterations 10
