#!/bin/bash
# specs.sh: the rIC3 specs of rule 2 and rule 3 that differ from S (all of LUI, AUIPC, JAL; ADDI on the sample of
# fine_gpr_choices, rule 2 every other differing write case).
. "$(dirname "$0")/env.sh"
O=$R/results/llm_rule_pilot/piccolo
mkdir -p $RUN/specs
for r in rule2 rule3; do
  for c in LUI AUIPC JAL; do
    python3 $R/results/llm_rule_pilot/scripts/make_specs.py $O/compare-$r-$c.json $RUN/specs/$r-$c.jsonl
  done
  python3 $R/results/llm_rule_pilot/scripts/make_specs.py $O/compare-$r-ADDI.json $RUN/specs/$r-ADDI.jsonl \
    $P/ADDI/subs-sample.json $([ $r = rule2 ] && echo 2 || echo 1)
done
