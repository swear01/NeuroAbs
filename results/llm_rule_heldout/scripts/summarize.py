"""summarize.py <run dir> <arm>...: per test case and arm, the results of PREREG.md section 7.

For every case with <run>/batches/<case>/test.map.json: UNSAT count (of the sampled sub-properties; rejected counts as
not proved), the other statuses, refinements, final COI state bits (all checked sub-properties, and UNSAT only) and
total time.  Writes JSON to stdout.
"""
import collections
import json
import os
import sys

CASES = ["ADD_Flatten", "SUB", "OR", "XOR", "ANDI", "SLTI", "LUI", "AUIPC", "JAL", "BEQ", "BNE_new", "SB", "SH"]


def jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    run = sys.argv[1]
    arms = sys.argv[2:]
    out = {}
    for case in CASES:
        map_path = os.path.join(run, "batches", case, "test.map.json")
        if not os.path.exists(map_path):
            continue
        with open(map_path) as f:
            mapping = json.load(f)
        results = {r["name"]: r for r in jsonl(os.path.join(run, "runs", case, "test", "results.jsonl"))}
        out[case] = {}
        for arm in arms:
            if arm not in mapping:
                continue
            rejected_path = os.path.join(run, "specs", case, arm + ".jsonl.rejected.json")
            with open(rejected_path) as f:
                rejected = json.load(f)
            rows = [results.get(n) for n in mapping[arm].values()]
            if any(r is None for r in rows):
                out[case][arm] = {"pending": sum(r is None for r in rows)}
                continue
            status = collections.Counter(r["status"] for r in rows)
            status.update({"rejected": len(rejected)} if rejected else {})
            unsat = [r for r in rows if r["status"] == "UNSAT"]
            out[case][arm] = {
                "n": len(rows) + len(rejected), "unsat": len(unsat), "status": dict(status),
                "refinements": sum(r["refinements"] for r in rows),
                "coi_bits": sum(r["final_coi_state_bits"] for r in rows),
                "coi_bits_unsat": sum(r["final_coi_state_bits"] for r in unsat),
                "seconds": round(sum(r["total_seconds"] for r in rows)),
                "unproved": {s: results[n]["status"] for s, n in mapping[arm].items()
                             if results[n]["status"] != "UNSAT"},
                "rejected": rejected,
            }
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
