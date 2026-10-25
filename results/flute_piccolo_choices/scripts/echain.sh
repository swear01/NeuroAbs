#!/bin/bash
# E-core timing after the pilot chain: Piccolo sanity CEGAR arms (3 repeats), then the ADDI ILA pair model.
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
while [ ! -e timing-pilot.done ]; do sleep 15; done
mkdir -p timing-sanity-cegar
for rep in 1 2 3; do
  for c in ADD_Flatten ADDI ANDI AUIPC BEQ BNE_new JAL LUI OR SLTI SUB XOR; do
    d=choice/piccolo-$c-sanity
    for arm in coarsest llm; do
      a=coarsest; [ $arm = llm ] && a=$d/llm-deepseek/assignment.json
      w=timing-sanity-cegar/$c-$arm-$rep
      taskset -c 16-31 python3 $R/src/choice_abstraction.py cegar --wrapper $R/Piccolo_verification_done/$c/wrapper.v --prop sanity \
        --workdir $w --units $d/units.json --assignment $a --time-limit 600 --refine one > $w.log 2>&1
      echo "{\"case\": \"$c\", \"arm\": \"$arm\", \"repeat\": $rep, \"result\": $(head -1 $w.log)}" >> timing-sanity-cegar/results.jsonl
    done
  done
done
d=choice/piccolo-ADDI-ila
taskset -c 16-31 python3 $R/src/choice_abstraction.py cegar --wrapper $R/Piccolo_verification_done/ADDI/wrapper.v --prop ila \
  --workdir timing-ila-pair --units $d/units.json --assignment $d/oracle-pair.json --time-limit 3600 --max-iterations 0 > timing-ila-pair.log 2>&1
touch echain.done
