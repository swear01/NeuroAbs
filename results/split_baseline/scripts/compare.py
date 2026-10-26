"""compare.py <split results.jsonl> <arm results.jsonl>...: pair each arm with the split-only baseline by sub-property.

Per kind (frame, mem, write): proved counts, total seconds over all rows, and the speed-up on rows both prove.
"""
import json
import math
import statistics
import sys


def load(path):
    with open(path) as f:
        return {r["name"]: r for r in map(json.loads, f)}


def kind(name):
    if name == "mem":
        return "mem"
    return "frame" if name.endswith(".frame") else "write"


base = load(sys.argv[1])
for path in sys.argv[2:]:
    arm = load(path)
    names = sorted(base.keys() & arm.keys())
    print(f"== {path} ({len(names)} paired)")
    for k in ("frame", "mem", "write", "all"):
        rows = [n for n in names if k == "all" or kind(n) == k]
        if not rows:
            continue
        both = [n for n in rows if base[n]["status"] == arm[n]["status"] == "UNSAT"]
        ratios = [base[n]["total_seconds"] / arm[n]["total_seconds"] for n in both]
        line = (f"{k:5} n={len(rows):3} split UNSAT={sum(base[n]['status'] == 'UNSAT' for n in rows):3} "
                f"arm UNSAT={sum(arm[n]['status'] == 'UNSAT' for n in rows):3} "
                f"split s={sum(base[n]['total_seconds'] for n in rows):8.0f} "
                f"arm s={sum(arm[n]['total_seconds'] for n in rows):8.0f}")
        if ratios:
            line += (f" both={len(both):3} median x{statistics.median(ratios):5.1f}"
                     f" geomean x{math.exp(statistics.mean(map(math.log, ratios))):5.1f}"
                     f" min x{min(ratios):4.1f}")
        print(line)
    split_bits = statistics.median(base[n]["final_coi_state_bits"] for n in names)
    arm_bits = statistics.median(arm[n]["final_coi_state_bits"] for n in names)
    print(f"median COI state bits: split {split_bits:.0f}, arm {arm_bits:.0f}")
