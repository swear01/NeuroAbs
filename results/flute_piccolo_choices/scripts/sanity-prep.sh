#!/bin/bash
# Units and DeepSeek choices for the Piccolo sanity cases (cores 4-7, untimed).
. /var/tmp/neuroabs-runtime/env-20261024.sh
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
for c in ADD_Flatten ADDI ANDI AUIPC BEQ BNE_new JAL LUI OR SLTI SUB XOR; do
  W=$R/Piccolo_verification_done/$c/wrapper.v
  d=$PWD/choice/piccolo-$c-sanity; mkdir -p $d/llm-deepseek
  [ -s $d/units.json ] || taskset -c 4-7 python3 $R/src/choice_abstraction.py units --wrapper $W --prop sanity --workdir $d \
    --b0 $PWD/piccolo/$c/b0_sanity.btor2 > $d/units.json 2> $d/units.err
  [ -s $d/llm-deepseek/assignment.json ] || (cd $d/llm-deepseek && LLM_BUDGET_USD=1 PYTHONPATH=$R/src taskset -c 4-7 python3 $R/src/choice_llm.py \
    --wrapper $W --prop sanity --units ../units.json --description $R/Piccolo_verification_done/$c/description.txt --workdir . > llm.log 2>&1)
  echo $c $(cat $d/llm-deepseek/assignment.json | tr -d '\n ')
done
touch choice/sanity-prep.done
