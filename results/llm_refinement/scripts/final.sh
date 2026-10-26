#!/bin/bash
# final.sh <cpus> <case>...: rIC3 portfolio for 1800 s on the three distinct final models of the arms (E-cores, timed).
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-refine-20261026
cpus=$1; shift
export RIC3_TMP_DIR=$RUN/.ric3tmp-final-$cpus; mkdir -p $RIC3_TMP_DIR
for c in "$@"; do
  mkdir -p $RUN/final/$c
  for a in csr_regfile=keep+gpr_regfile_regfile=keep+near_mem_dcache=keep+near_mem_icache=keep \
           csr_regfile=cut+gpr_regfile_regfile=keep+near_mem_dcache=keep+near_mem_icache=keep \
           csr_regfile=cut+gpr_regfile_regfile=keep+near_mem_dcache=cut+near_mem_icache=keep; do
    log=$RUN/final/$c/$a.log
    [ -s $log ] && continue
    /usr/bin/time -f "%e s" -o $log.time taskset -c $cpus timeout 1900 $RIC3_BIN check --ui false $RUN/piccolo/$c/models/$a/model.btor2 portfolio --time-limit 1800 > $log 2>&1
    echo "$c $a $(grep -E '^(SAT|UNSAT|UNKNOWN)$' $log) $(cat $log.time)"
  done
done
