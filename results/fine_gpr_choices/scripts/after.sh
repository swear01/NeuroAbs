#!/bin/bash
# after.sh <pid-pattern> <cmd...>: wait until no process other than this script and its ancestors matches, then run the command.
p=$1; shift
skip=" "; q=$$; while [ "$q" -gt 1 ]; do skip="$skip$q "; q=$(ps -o ppid= -p "$q" | tr -d ' '); done
running() { for q in $(pgrep -f "$p"); do [[ $skip == *" $q "* ]] || return 0; done; return 1; }
while running; do sleep 20; done; "$@"
