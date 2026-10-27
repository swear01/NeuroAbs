#!/bin/bash
# generate.sh <samples>: write the prompt and ask DeepSeek for <samples> rules (ADDI training examples).
. "$(dirname "$0")/env.sh"
mkdir -p $RUN && cd $RUN
LLM_BUDGET_USD=3 taskset -c 4-5 python3 $R/src/llm_rule.py generate --wrapper $R/Piccolo_verification_done/ADDI/wrapper.v \
  --units $P/ADDI/units.json --uf $P/ADDI/uf.json --description $R/Piccolo_verification_done/ADDI/description.txt \
  --workdir $RUN/hier-ADDI --examples $R/results/llm_rule_pilot/prompt/examples-ADDI.json --out $RUN/gen --samples $1
