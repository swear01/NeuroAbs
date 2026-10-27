"""control_specs.py <case> <subs.json> <out.jsonl> <name>...: S specs (fine_choice.structural) of the named sub-properties."""
import json
import sys

import fine_choice

case, subs, out, names = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4:]
units = json.load(open("{:s}/units.json".format(case)))
ufs = json.load(open("{:s}/uf.json".format(case)))
with open(out, "w") as f:
    for s in subs:
        if s["name"] in names:
            f.write(json.dumps({"name": s["name"], "spec": fine_choice.structural(s, units, ufs)}) + "\n")
