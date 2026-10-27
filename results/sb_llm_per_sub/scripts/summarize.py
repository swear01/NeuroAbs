"""summarize.py <run dir> <state> <out.jsonl>: per arm and sub-property of <state>, the last fine_batch record of its run
(status, refinements, final COI state bits, seconds), and per arm the UNSAT count, refinements and COI bit totals."""
import json
import os
import sys


def main():
    run, state, out = sys.argv[1:4]
    with open(os.path.join(run, "batches", state + ".map.json")) as f:
        mapping = json.load(f)
    last = {}
    with open(os.path.join(run, "runs", state, "results.jsonl")) as f:
        for r in map(json.loads, filter(str.strip, f)):
            last[r["name"]] = r
    rows = []
    for arm, subs in mapping.items():
        for sub, name in subs.items():
            r = last.get(name, {"status": "missing"})
            rows.append({"arm": arm, "sub": sub, "run": name, "status": r["status"], "refinements": r.get("refinements"),
                         "final_coi_state_bits": r.get("final_coi_state_bits"), "total_seconds": r.get("total_seconds"),
                         "ric3": [i.get("ric3") for i in r.get("iterations") or []], "final_uf": (r.get("final_spec") or {}).get("uf")})
    with open(out, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    for arm in mapping:
        sel = [r for r in rows if r["arm"] == arm]
        built = [r for r in sel if r["status"] not in ("ERROR", "missing")]
        print(json.dumps({"arm": arm, "n": len(sel), "UNSAT": sum(r["status"] == "UNSAT" for r in sel),
                          "statuses": {s: sum(r["status"] == s for r in sel) for s in sorted({r["status"] for r in sel})},
                          "refinements": sum(r["refinements"] or 0 for r in built),
                          "coi_bits": sum(r["final_coi_state_bits"] or 0 for r in built),
                          "coi_bits_unsat": sum(r["final_coi_state_bits"] for r in sel if r["status"] == "UNSAT"),
                          "seconds": round(sum(r["total_seconds"] or 0 for r in built), 1)}))


if __name__ == "__main__":
    main()
