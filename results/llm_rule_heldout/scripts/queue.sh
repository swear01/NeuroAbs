#!/bin/bash
# queue.sh: run the jobs of $RUN/queue/pending one at a time, in name order; each job file holds "<case> <batch>".
# A job moves to done or failed.  The queue ends when it is empty and $RUN/queue/stop exists.
. "$(dirname "$0")/env.sh"
S="$(cd "$(dirname "$0")" && pwd)"
Q=$RUN/queue
mkdir -p $Q/pending $Q/done $Q/failed $Q/logs
while true; do
  job=$(ls $Q/pending | sort | head -1)
  if [ -z "$job" ]; then
    [ -e $Q/stop ] && exit 0
    sleep 30
    continue
  fi
  mv $Q/pending/$job $Q/running
  echo "$(date -Is) start $job $(cat $Q/running)" >> $Q/queue.log
  if bash "$S/job.sh" $(cat $Q/running) > $Q/logs/$job.log 2>&1; then d=done; else d=failed; fi
  echo "$(date -Is) $d $job" >> $Q/queue.log
  mv $Q/running $Q/$d/$job
done
