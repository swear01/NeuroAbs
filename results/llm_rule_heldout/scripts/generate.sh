#!/bin/bash
# generate.sh <deepseek|claude> <samples>: the prompt of PREREG.md (ADDI design, 7 examples) sent <samples> times.
set -euo pipefail
. "$(dirname "$0")/env.sh"
P=$H/problems/ADDI
mkdir -p $RUN/gen-$1
LLM_BUDGET_USD=3 python3 $R/src/llm_rule.py generate --wrapper $RUN/problems/ADDI/wrapper.v --units $P/units.json \
  --uf $P/candidates.json --description $R/Piccolo_verification_done/ADDI/description.txt --workdir $RUN/hier-ADDI \
  --examples $H/prompt/examples-ADDI.json --out $RUN/gen-$1 --samples $2 --backend $1
