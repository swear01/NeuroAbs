# usage (on mazu): bash large_chain.sh ROOT SRCDIR   -- Experiment B, sequential: run --budget 1800, split-only control on the same leaves, vacuity, report
. /var/tmp/neuroabs-runtime/env-20261024.sh
ROOT=$1; SRC=$2
for b in simple_cam_16 fifo_ref_64; do
  W=$ROOT/$b
  [ -f $W/.done ] && continue
  cd $W
  python src/case_study.py init --workdir . > init.out 2>&1 || { echo FAIL-init $W >> $ROOT/chain.status; continue; }
  uptime > uptime_start.txt; t0=$(date +%s.%N)
  python src/case_study.py run --workdir . --budget 1800 > run.out 2>&1; echo $? > run.rc
  echo "$(date +%s.%N) - $t0" | bc > wall_s.txt; uptime > uptime_run_end.txt
  python src/case_study.py report --workdir . > report.out 2>&1
  python src/case_study.py split-only --workdir . --timeout 120 > split_only.out 2>&1; uptime > uptime_split_only_end.txt
  timeout 1800 python src/case_study.py vacuity --workdir . > vacuity.out 2>&1
  rm -f flat_*.il *.btor2 *_k0.v *_k0.il *_reach.* *_nv.* ; touch .done
  echo "DONE $W rc=$(cat run.rc) wall=$(cat wall_s.txt)" >> $ROOT/chain.status
done
echo CHAIN-FINISHED >> $ROOT/chain.status
