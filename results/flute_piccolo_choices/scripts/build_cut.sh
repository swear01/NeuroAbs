#!/bin/bash
# build_cut.sh <wrapper.v> <ila|sanity> <out.btor2> [memory names to havoc...]
set -euo pipefail
src=$1; prop=$2; out=$3; shift 3
if [ $prop = ila ]; then remove=sanitycheck; else remove=normalassert; fi
sel=""
for m in "$@"; do sel="$sel wrapper/$m"; done
ys=${out%.btor2}.ys
{
echo "read_verilog -formal $src"
echo "hierarchy -check -top wrapper"
echo "proc"
echo "chformal -assume -early;"
echo "select wrapper/$remove"
echo "chformal -remove"
echo "select *"
echo "flatten"
echo "memory -nomap"
[ -n "$sel" ] && echo "cutpoint$sel"
echo "memory"
echo "setundef -undriven -expose;"
echo "chformal -lower;"
echo "sim -clock clk -reset rst -rstlen 1 -n 1 -w wrapper"
echo "write_btor -s $out"
} > "$ys"
"${YOSYS_BIN:-yosys}" -q -s "$ys" > "${out%.btor2}.yosys.log" 2>&1
