#!/bin/bash
# build_b0.sh <repo> <Core_verification_done/CASE> <outdir>: B0 BTOR2 for the ILA and sanity properties.
set -euo pipefail
repo=$1; case=$2; out=$3
mkdir -p "$out"
src="$repo/$case/wrapper.v"
for prop in ila sanity; do
  if [ $prop = ila ]; then remove=sanitycheck; else remove=normalassert; fi
  cat > "$out/b0_$prop.ys" <<YS
read_verilog -formal $src
hierarchy -check -top wrapper
proc
chformal -assume -early;
select wrapper/$remove
chformal -remove
select *
memory;
flatten
setundef -undriven -expose;
chformal -lower;
sim -clock clk -reset rst -rstlen 1 -n 1 -w wrapper
write_btor -s $out/b0_$prop.btor2
YS
  /usr/bin/time -f "%e s %M KB" -o "$out/b0_$prop.buildtime" "$YOSYS_BIN" -q -s "$out/b0_$prop.ys" > "$out/b0_$prop.yosys.log" 2>&1
done
