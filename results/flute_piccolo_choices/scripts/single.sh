#!/bin/bash
# single.sh <case-dir> <wrapper> <prop> <time-limit>: rIC3 on every single-unit abstraction.
. /var/tmp/neuroabs-runtime/env-20261024.sh
export RIC3_TMP_DIR=/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/.ric3tmp-p
R=~/.agent-worktrees/NeuroAbs-flute-piccolo
mkdir -p "$1/single"
PYTHONPATH=$R/src python3 - "$@" <<'PY'
import json, os, sys
import choice_abstraction as c
d, wrapper, prop, limit = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
units = json.load(open(d + "/units.json"))
for u in units:
    for level in u["levels"][1:]:
        model = os.path.abspath("{}/single/{}-{}.btor2".format(d, u["id"], level))
        c.build(wrapper, prop, c.assignment_choices(units, {u["id"]: level}), model, model + ".work")
        verdict, depth, seconds = c.ric3_check(model, limit, model + ".ric3.log")
        print(json.dumps({"unit": u["id"], "level": level, "verdict": verdict, "depth": depth,
                          "seconds": round(seconds, 1), "coi_state_bits": sum(c.coi_state_bits(model).values())}),
              flush=True)
PY
