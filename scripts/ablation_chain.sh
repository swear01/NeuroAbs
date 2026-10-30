# usage (on mazu): bash ablation_chain.sh ROOT SRCDIR   -- Experiment A, sequential, resumable
# bench dirs (prep/design/case.json) are taken from the PR #29 work dirs adaptive-<name>-20261030
. /var/tmp/neuroabs-runtime/env-20261024.sh
ROOT=$1; SRC=$2
B=/var/tmp/neuroabs-runtime
declare -A DIR=([lrg_arb]=lrg-arb [fifo_vis]=fifo-vis [simple_cam_8]=simple-cam-8 [fifo_ref_16]=fifo-ref-16)
for rep in 1 2 3; do for b in lrg_arb fifo_vis simple_cam_8 fifo_ref_16; do for mode in hint nohint; do
  W=$ROOT/$b-$mode-$rep
  [ -f $W/.done ] && continue
  mkdir -p $W; cp -r $B/adaptive-${DIR[$b]}-20261030/bench $W/; cp -r $SRC $W/src
  cd $W
  python src/case_study.py init --workdir . > init.out 2>&1 || { echo FAIL-init $W >> $ROOT/chain.status; continue; }
  FLAG=""; [ $mode = nohint ] && FLAG="--no-index-hint"
  uptime > uptime_start.txt; t0=$(date +%s.%N)
  python src/case_study.py run --workdir . --budget 1200 $FLAG > run.out 2>&1; echo $? > run.rc
  echo "$(date +%s.%N) - $t0" | bc > wall_s.txt; uptime > uptime_run_end.txt
  python src/case_study.py report --workdir . > report.out 2>&1
  timeout 1800 python src/case_study.py vacuity --workdir . > vacuity.out 2>&1
  uptime > uptime_end.txt
  rm -f flat_*.il *.btor2 *_k0.v *_k0.il *_reach.* *_nv.* ; touch .done
  echo "DONE $W rc=$(cat run.rc) wall=$(cat wall_s.txt)" >> $ROOT/chain.status
done; done; done
echo CHAIN-FINISHED >> $ROOT/chain.status
