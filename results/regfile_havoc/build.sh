#!/bin/bash
# Build H0 (B0 RTL + k=0 havoc) and H1 (B1 final-model RTL + k=0 havoc) for the nine cases.
R=/var/tmp/neuroabs-runtime/runs/decision-20261022
O=/var/tmp/neuroabs-runtime/runs/regfile-havoc-20261025
mkdir -p "$O"
. /var/tmp/neuroabs-runtime/env-20261024.sh
cd "$(dirname "$0")/../.."
for c in add addi and bge ori sh slti sub xor; do
  m=$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["final_model"])' $R/riscv_formal_$c/B1/arm_summary.json)
  echo "taskset -c 0-15 python src/regfile_havoc.py build --src-dir $R/riscv_formal_$c/B0 --verilog $R/riscv_formal_$c/B0/picorv32_input.v --out-dir $O/riscv_formal_$c/H0 --k 0 > $O/build-$c-H0.log 2>&1; echo $c H0 \$?"
  echo "taskset -c 0-15 python src/regfile_havoc.py build --src-dir $R/riscv_formal_$c/B1 --verilog ${m%.btor2}.v --out-dir $O/riscv_formal_$c/H1 --k 0 > $O/build-$c-H1.log 2>&1; echo $c H1 \$?"
done | xargs -P 8 -I{} sh -c '{}'
python src/regfile_havoc.py stats $R/riscv_formal_*/B0/picorv32_input.btor2 $O/riscv_formal_*/H?/picorv32_input.btor2 | sed 's#/var/tmp/neuroabs-runtime/runs/##' > $O/stats-k0.txt
