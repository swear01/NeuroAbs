#!/bin/bash
# feedback.sh <deepseek|claude> <training batch json name>: the feedback round of PREREG.md section 4, on mazu.
# The messages come from training.py on zeus ($RUN/training/<batch>-feedback-<model>.json, copied here first).
set -euo pipefail
. "$(dirname "$0")/env.sh"
LLM_BUDGET_USD=${LLM_BUDGET_USD:?remaining DeepSeek budget} python3 $R/src/llm_rule.py feedback --out $RUN/gen-$1 \
  --feedback $RUN/training/$2-feedback-$1.json
