#!/bin/bash
cd /var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025
while [ ! -e choice/piccolo-ADDI-ila/traj.done ]; do sleep 15; done
d=choice/flute-ADD-ila
taskset -c 8-15 ./single.sh $d ~/.agent-worktrees/NeuroAbs-flute-piccolo/Flute_verification_done/ADD/wrapper.v ila 600 > $d/single.jsonl 2> $d/single.err
touch $d/single.done
