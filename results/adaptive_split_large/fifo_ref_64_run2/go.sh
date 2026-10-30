. /var/tmp/neuroabs-runtime/env-20261024.sh
cd /var/tmp/neuroabs-runtime/large-B/fifo_ref_64-run2
python src/case_study.py init --workdir . > init.out 2>&1
uptime > uptime_start.txt; t0=$(date +%s.%N)
python src/case_study.py run --workdir . --budget 1800 > run.out 2>&1; echo $? > run.rc
echo "$(date +%s.%N) - $t0" | bc > wall_s.txt; uptime > uptime_run_end.txt
python src/case_study.py report --workdir . > report.out 2>&1
echo "DONE /var/tmp/neuroabs-runtime/large-B/fifo_ref_64-run2 rc=$(cat run.rc) wall=$(cat wall_s.txt)" >> /var/tmp/neuroabs-runtime/large-B/chain.status
