#!/bin/bash
# After full-p on P-cores: the rest of the full proof (part e2), then the whole property with UF for 1800 s.
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
until [ -e $RUN/piccolo-ADDI/arm-full-p.done ]; do [ -e $RUN/piccolo-ADDI/arm-full-p.failed ] && exit 1; sleep 30; done
$RUN/scripts/arm.sh ADDI full-e2 $RUN/piccolo-ADDI/specs-full-e2.jsonl 12-13/14-15 300 10 || exit 1
ALL='["load_en","pc","store_en","x0","x1","x10","x11","x12","x13","x14","x15","x16","x17","x18","x19","x2","x20","x21","x22","x23","x24","x25","x26","x27","x28","x29","x3","x30","x31","x4","x5","x6","x7","x8","x9"]'
$RUN/scripts/screen.sh 12-15 ADDI Q-whole-ack-long 1800 0 "{\"states\":$ALL,\"keep_gprs\":\"all\",\"units\":{\"csr_regfile\":\"cut\",\"near_mem_dcache\":\"cut\"},\"uf\":[{\"ila\":\"n110\",\"rtl\":\"rd_val___1__h6550\"}]}"
