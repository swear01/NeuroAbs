"""make_specs.py <compare.json> <out.jsonl> [names.json [every]]: the specs of a rule that differ from S.

With names.json (a JSON list of sub-properties), keep only those names; with every = n, keep every n-th
of the differing write cases (and all other differing ones), in the order of names.json.
"""
import json
import sys

rows = json.load(open(sys.argv[1]))
diff = {r["name"]: r["spec"] for r in rows if r.get("same") is False}
names = [s["name"] for s in json.load(open(sys.argv[3]))] if len(sys.argv) > 3 else [r["name"] for r in rows]
every = int(sys.argv[4]) if len(sys.argv) > 4 else 1
picked, writes = [], 0
for n in names:
    if n not in diff:
        continue
    if n != "mem" and not n.endswith(".frame"):
        writes += 1
        if (writes - 1) % every:
            continue
    picked.append(n)
with open(sys.argv[2], "w") as f:
    for n in picked:
        f.write(json.dumps({"name": n, "spec": diff[n]}) + "\n")
print(len(picked), "of", len(diff), "differing")
