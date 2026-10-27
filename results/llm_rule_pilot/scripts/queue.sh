#!/bin/bash
# queue.sh: every rIC3 run of the pilot, in order, on P-cores 12-13 / 14-15.
. "$(dirname "$0")/env.sh"
S="$(dirname "$0")"
C=12-13/14-15
rm -f $RUN/queue.done $RUN/queue.failed
trap '[ -e $RUN/queue.done ] || touch $RUN/queue.failed' EXIT
set -e
for c in LUI AUIPC JAL; do
  (cd $P && python3 $R/results/llm_rule_pilot/scripts/control_specs.py $c $RUN/subs-$c.json $RUN/specs/S-$c.jsonl \
    mem x1.frame x5.frame x17.frame x1.write x5.write x17.write)
  $S/arm.sh $c S-control $RUN/specs/S-$c.jsonl $C
  $S/arm.sh $c rule2 $RUN/specs/rule2-$c.jsonl $C
  $S/arm.sh $c rule3 $RUN/specs/rule3-$c.jsonl $C
done
(cd $P && python3 $R/results/llm_rule_pilot/scripts/control_specs.py ADDI $RUN/subs-ADDI.json $RUN/specs/S-ADDI.jsonl \
  mem x1.frame x5.frame x17.frame x5.rs1=0 x19.rs1=2 x2.rs1=4 x16.rs1=6)
$S/arm.sh ADDI S-control $RUN/specs/S-ADDI.jsonl $C
$S/arm.sh ADDI rule2 $RUN/specs/rule2-ADDI.jsonl $C
$S/arm.sh ADDI rule3 $RUN/specs/rule3-ADDI.jsonl $C
touch $RUN/queue.done
