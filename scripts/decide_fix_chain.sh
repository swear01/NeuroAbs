# usage (on mazu): bash decide_fix_chain.sh ROOT SRCDIR   -- reruns after the decide-quota fix, sequential, resumable
# fifo_ref_64 twice (budget 1800), then 3 runs of each ablation cell that got stuck in decide (budget 1200)
. /var/tmp/neuroabs-runtime/env-20261024.sh
ROOT=$1; SRC=$2
B=/var/tmp/neuroabs-runtime
RUNS="fifo_ref_64:large-B/fifo_ref_64:hint:1800:1 fifo_ref_64:large-B/fifo_ref_64:hint:1800:2"
for rep in 1 2 3; do
  RUNS="$RUNS fifo_ref_16:adaptive-fifo-ref-16-20261030:hint:1200:$rep fifo_vis:adaptive-fifo-vis-20261030:hint:1200:$rep"
  RUNS="$RUNS fifo_vis:adaptive-fifo-vis-20261030:nohint:1200:$rep simple_cam_8:adaptive-simple-cam-8-20261030:nohint:1200:$rep"
done
for r in $RUNS; do
  IFS=: read b dir mode budget rep <<< "$r"
  W=$ROOT/$b-$mode-$rep
  [ -f $W/.done ] && continue
  rm -rf $W; mkdir -p $W; cp -r $B/$dir/bench $W/; cp -r $SRC $W/src
  cd $W
  python src/case_study.py init --workdir . > init.out 2>&1 || { echo FAIL-init $W >> $ROOT/chain.status; continue; }
  FLAG=""; [ $mode = nohint ] && FLAG="--no-index-hint"
  uptime > uptime_start.txt; t0=$(date +%s.%N)
  python src/case_study.py run --workdir . --budget $budget $FLAG > run.out 2>&1; echo $? > run.rc
  echo "$(date +%s.%N) - $t0" | bc > wall_s.txt; uptime > uptime_run_end.txt
  python src/case_study.py report --workdir . > report.out 2>&1
  timeout 1800 python src/case_study.py vacuity --workdir . > vacuity.out 2>&1
  uptime > uptime_end.txt
  rm -f flat_*.il *.btor2 *_k0.v *_k0.il *_reach.* *_nv.* ; touch .done
  echo "DONE $W rc=$(cat run.rc) wall=$(cat wall_s.txt)" >> $ROOT/chain.status
done
echo CHAIN-FINISHED >> $ROOT/chain.status
