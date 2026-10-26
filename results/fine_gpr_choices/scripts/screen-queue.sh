#!/bin/bash
# screen-queue.sh <cpus> <file>: run screen.sh on each line "<case> <name> <limit> <iters> <spec>" in turn.
while read -r c n l i s; do /var/tmp/neuroabs-runtime/runs/fine-gpr-20261026/scripts/screen.sh $1 $c $n $l $i "$s"; done < $2
