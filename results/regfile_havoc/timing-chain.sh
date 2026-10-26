#!/bin/bash
# 2026-10-25: time regfile-havoc H0 (B0 + k=0 havoc) then H1 (B1 final + k=0 havoc) pinned to CPUs 16-31
O=/var/tmp/neuroabs-runtime/runs/regfile-havoc-20261025
. /var/tmp/neuroabs-runtime/env-20261024.sh
cd "$(dirname "$0")/../.."
PY=$(command -v python)
run(){ D=$O/timing-ric3-8c6df1b-$1; mkdir -p $D
  git rev-parse HEAD > $D/commit.txt; git diff --stat > $D/diff.txt; git status --short > $D/status.txt
  M=""; for c in add addi and bge ori sh slti sub xor; do M="$M --model $c-$1=$O/riscv_formal_$c/$1/picorv32_input.btor2"; done
  taskset -c 16-31 "$PY" src/run_decision_experiment.py time --ric3 "$RIC3_BIN" --repeats 3 --time-limit 3600 --parallel 1 --output $D/timing.json $M > $D/stdout.log 2>&1
  s=$?; echo "DONE exit=$s" >> $D/stdout.log; return $s; }
status=0
for a in "$@"; do run $a || status=1; done
[ $status -eq 0 ] && touch $O/timing-$(echo "$@" | tr ' ' '-').done
exit $status
