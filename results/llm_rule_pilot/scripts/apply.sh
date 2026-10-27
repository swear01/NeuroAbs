#!/bin/bash
# apply.sh <rule.py> <tag>: apply a rule to every sub-property of ADDI, LUI, AUIPC and JAL; compare with S.
. "$(dirname "$0")/env.sh"
out=$R/results/llm_rule_pilot/piccolo
mkdir -p $out
for c in ADDI LUI AUIPC JAL; do
  python3 $R/src/fine_choice.py split --wrapper $R/Piccolo_verification_done/$c/wrapper.v > $RUN/subs-$c.json
  echo -n "$2 $c "
  python3 $R/src/llm_rule.py apply --wrapper $R/Piccolo_verification_done/$c/wrapper.v --units $P/$c/units.json \
    --uf $P/$c/uf.json --description $R/Piccolo_verification_done/$c/description.txt --workdir $RUN/hier-$c \
    --rule $1 --subs $RUN/subs-$c.json --out $out/compare-$2-$c.json
done
