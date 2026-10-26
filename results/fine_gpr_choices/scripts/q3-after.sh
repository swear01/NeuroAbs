#!/bin/bash
RUN=/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026
while pgrep -f "q1[.]txt" > /dev/null; do sleep 20; done
$RUN/scripts/screen-queue.sh 12-13 $RUN/q3.txt
