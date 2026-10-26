"""summarize.py <results.jsonl>...: per sub-property kind, verdicts, refinements and time."""
import collections
import json
import statistics
import sys


def kind(name):
    return "mem" if name == "mem" else name.split(".", 1)[1].split("=")[0] if "." in name else name


for path in sys.argv[1:]:
    rows = [json.loads(line) for line in open(path) if line.strip()]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[kind(r["name"])].append(r)
        groups["all"].append(r)
    print(path)
    for k, rs in sorted(groups.items()):
        status = collections.Counter(r["status"] for r in rs)
        print("  {:6s} n={:4d} {} refinements={:4d} total={:8.0f} build={:7.0f} ric3={:8.0f} replay={:5.0f} "
              "median={:5.0f} max={:5.0f} coi_median={:5.0f}".format(
                  k, len(rs), dict(status), sum(r.get("refinements", 0) for r in rs),
                  sum(r.get("total_seconds", 0) for r in rs), sum(r.get("build_seconds", 0) for r in rs),
                  sum(r.get("ric3_seconds", 0) for r in rs), sum(r.get("replay_seconds", 0) for r in rs),
                  statistics.median(r.get("total_seconds", 0) for r in rs), max(r.get("total_seconds", 0) for r in rs),
                  statistics.median(r.get("final_coi_state_bits", 0) for r in rs)))
