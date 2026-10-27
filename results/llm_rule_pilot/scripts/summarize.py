"""summarize.py <run dir>: per rule and case, agreement with S, and the rIC3 results of the differing specs next to the
recorded S results of the same sub-properties; plus the S control rerun against the recorded S runs."""
import collections
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.dirname(HERE)
FINE = os.path.join(PILOT, "..", "fine_gpr_choices", "piccolo")
CASES = ("ADDI", "LUI", "AUIPC", "JAL")


def jsonl(paths):
    out = {}
    for p in paths:
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                if r["name"] in out:
                    raise ValueError("duplicate record {:s} in {:s}".format(r["name"], p))
                out[r["name"]] = r
    return out


def recorded_s(case):
    return jsonl(glob.glob(os.path.join(FINE, case, "arm-structural*.jsonl"))
                 + glob.glob(os.path.join(FINE, case, "arm-full-*.jsonl")))


def stats(records):
    status = collections.Counter(r["status"] for r in records)
    times = [r["total_seconds"] for r in records]
    return {"n": len(records), "status": dict(status), "refinements": sum(r["refinements"] for r in records),
            "seconds": round(sum(times)), "median": round(statistics.median(times)) if times else None}


def main(run):
    report = {}
    for case in CASES:
        s = recorded_s(case)
        for rule in ("rule1", "rule2", "rule3"):
            rows = json.load(open(os.path.join(PILOT, "piccolo", "compare-{:s}-{:s}.json".format(rule, case))))
            entry = {"subs": len(rows), "same": sum(r.get("same") is True for r in rows),
                     "different": sum(r.get("same") is False for r in rows),
                     "rejected": sum("errors" in r for r in rows)}
            path = os.path.join(run, "piccolo-" + case, "arm-" + rule, "results.jsonl")
            if os.path.exists(path):
                runs = jsonl([path])
                entry["run"] = stats(list(runs.values()))
                entry["S_same_subs"] = stats([s[n] for n in runs])
                entry["unproved"] = {n: r["status"] for n, r in runs.items() if r["status"] != "UNSAT"}
                if entry["different"] == len(runs):
                    full = [runs.get(r["name"]) or s[r["name"]] for r in rows]
                    entry["whole_case"] = stats(full)
            report["{:s} {:s}".format(rule, case)] = entry
        path = os.path.join(run, "piccolo-" + case, "arm-S-control", "results.jsonl")
        if os.path.exists(path):
            runs = jsonl([path])
            ratios = [runs[n]["total_seconds"] / s[n]["total_seconds"] for n in runs]
            report["S-control " + case] = {"run": stats(list(runs.values())),
                                           "S_recorded": stats([s[n] for n in runs]),
                                           "time_ratio_median": round(statistics.median(ratios), 2),
                                           "time_ratio_range": [round(min(ratios), 2), round(max(ratios), 2)]}
    json.dump(report, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main(sys.argv[1])
