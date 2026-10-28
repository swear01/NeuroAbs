"""batch.py <specs dir> <out run-specs.jsonl> <out map.json> <arm>...: one rIC3 run per distinct spec.

Reads <specs dir>/<arm>.jsonl for every arm.  Specs of one sub-property that define the same abstraction (key) share
one run, named <sub>.<first 10 hex digits of the SHA-256 of the key>; map.json maps arm -> sub -> run name.  Run names
already in the output file are kept, so batches of one case can be extended; fine_batch skips finished runs.
"""
import hashlib
import json
import os
import sys

NUM_GPRS = 32


def key(spec):
    keep = list(range(NUM_GPRS)) if spec.get("keep_gprs", "all") == "all" else sorted(spec["keep_gprs"])
    return json.dumps({"states": spec["states"], "case": spec.get("case"), "rd_guard": bool(spec.get("rd_guard")),
                       "keep_gprs": keep, "word_gprs": sorted(spec.get("word_gprs", [])),
                       "units": {k: v for k, v in sorted(spec.get("units", {}).items()) if v != "keep"},
                       "uf": sorted((u["ila"], u["rtl"]) for u in spec.get("uf", []))}, sort_keys=True)


def run_name(sub, spec):
    return "{:s}.{:s}".format(sub, hashlib.sha256(key(spec).encode()).hexdigest()[:10])


def main():
    specs_dir, out, map_path = sys.argv[1:4]
    arms = sys.argv[4:]
    runs = {}
    if os.path.exists(out):
        with open(out) as f:
            runs = {r["name"]: r for r in map(json.loads, filter(str.strip, f))}
    mapping = {}
    if os.path.exists(map_path):
        with open(map_path) as f:
            mapping = json.load(f)
    added = 0
    for arm in arms:
        mapping[arm] = {}
        with open(os.path.join(specs_dir, arm + ".jsonl")) as f:
            for r in map(json.loads, filter(str.strip, f)):
                name = run_name(r["name"], r["spec"])
                mapping[arm][r["name"]] = name
                if name not in runs:
                    runs[name] = {"name": name, "spec": r["spec"]}
                    added += 1
    with open(out, "w") as f:
        for r in runs.values():
            f.write(json.dumps(r) + "\n")
    with open(map_path, "w") as f:
        json.dump(mapping, f, indent=1)
    print(json.dumps({"runs": len(runs), "added": added, "arms": {a: len(mapping[a]) for a in arms}}))


if __name__ == "__main__":
    main()
