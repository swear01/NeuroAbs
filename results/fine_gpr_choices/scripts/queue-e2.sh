#!/bin/bash
# After the auto sample arm on E-cores 24-27: the structural rule on the ADDI sample, then B0 for LUI, AUIPC and JAL.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
trap '[ -e $RUN/piccolo-JAL/b0/b0.done ] || { mkdir -p $RUN/piccolo-JAL/b0; touch $RUN/piccolo-JAL/b0/b0.failed; }' EXIT
until [ -e $RUN/piccolo-ADDI/arm-auto-sample.done ]; do [ -e $RUN/piccolo-ADDI/arm-auto-sample.failed ] && exit 1; sleep 30; done
$RUN/scripts/arm.sh ADDI structural-sample $RUN/piccolo-ADDI/specs-structural-sample.jsonl 24-25/26-27 300 10 || exit 1
$RUN/scripts/b0.sh LUI 24-25 1800 & p=$!; rc=0
$RUN/scripts/b0.sh AUIPC 26-27 1800 || rc=1; wait $p || rc=1; [ $rc -eq 0 ] || exit 1
$RUN/scripts/b0.sh JAL 24-25 1800
