"""make_specs.py <structural specs.jsonl> <out.jsonl> <split|no-uf> [name part]: derive specs from the S arm.

split: the same sub-property (states, case, rd_guard) on the unabstracted model.
no-uf: the S abstraction without the operator UF. With a name part, only names containing it are kept.
"""
import json
import sys

src, out, kind = sys.argv[1:4]
part = sys.argv[4] if len(sys.argv) > 4 else ""
with open(src) as f, open(out, "w") as g:
    for line in f:
        job = json.loads(line)
        if part not in job["name"]:
            continue
        spec = job["spec"]
        if kind == "split":
            spec = {k: spec[k] for k in ("states", "case", "rd_guard")}
        elif kind == "no-uf":
            spec = dict(spec, uf=[])
        else:
            raise ValueError("unknown kind " + kind)
        g.write(json.dumps({"name": job["name"], "spec": spec}) + "\n")
