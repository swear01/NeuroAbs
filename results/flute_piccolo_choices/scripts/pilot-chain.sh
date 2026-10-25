#!/bin/bash
# Waits for the Piccolo sanity B0 timing, then screens the Flute ADD pilot models (1 repeat each).
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
while [ ! -s timing-piccolo-sanity-b0/timing.json ]; do sleep 15; done
P=$PWD/pilot
taskset -c 16-31 python3 ~/.agent-worktrees/NeuroAbs-flute-piccolo/src/run_decision_experiment.py time --ric3 "$RIC3_BIN" --repeats 1 --time-limit 3600 --parallel 1 \
  --output $PWD/timing-pilot/timing.json \
  --model flute-ADD-sanity-P2=$P/flute-ADD-sanity-P2.btor2 \
  --model flute-ADD-sanity-P1=$P/flute-ADD-sanity-P1.btor2 \
  --model flute-ADD-ila-P2=$P/flute-ADD-ila-P2.btor2 \
  --model flute-ADD-ila-P1=$P/flute-ADD-ila-P1.btor2 \
  --model piccolo-ADDI-ila-B0=$PWD/piccolo/ADDI/b0_ila.btor2 \
  --model flute-ADD-sanity-B0=$PWD/flute/ADD/b0_sanity.btor2 \
  --model flute-ADD-ila-B0=$PWD/flute/ADD/b0_ila.btor2
touch timing-pilot.done
