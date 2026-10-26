#!/bin/bash
# after.sh <pid-pattern> <cmd...>: wait until no process other than this script and its ancestors matches, then run the command.
p=$1; shift
[ -n "$p" ] || { echo "after.sh: missing pid-pattern" >&2; exit 2; }
skip=" "; q=$$; while [ "$q" -gt 1 ]; do skip="$skip$q "; q=$(ps -o ppid= -p "$q" | tr -d ' '); case $q in ''|*[!0-9]*) break;; esac; done
running() { for q in $(pgrep -f "$p"); do [[ $skip == *" $q "* ]] || return 0; done; return 1; }
while running; do sleep 20; done; "$@"
