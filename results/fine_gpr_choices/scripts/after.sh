#!/bin/bash
# after.sh <pid-pattern> <cmd...>: wait until no process matches, then run the command.
p=$1; shift; while pgrep -f "$p" > /dev/null; do sleep 20; done; "$@"
