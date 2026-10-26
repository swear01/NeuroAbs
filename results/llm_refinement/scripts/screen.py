"""screen.py <case> <bound> <time-limit>: BMC ground truth for a Piccolo ILA case (P-cores, untimed).

Each unit is coarsened alone to each of its levels; a unit is needed at the finest level whose coarsening
has a counterexample up to the bound.  Then every unit at its coarsest level without one is checked together.  A BMC run that reaches the time
limit before the bound found no counterexample; it is listed as inconclusive.
"""
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/.agent-worktrees/NeuroAbs-llm-refine/src"))
import choice_abstraction as ca
RUN = "/var/tmp/neuroabs-runtime/runs/llm-refine-20261026"
case, bound, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
wrapper = os.path.expanduser("~/.agent-worktrees/NeuroAbs-llm-refine/Piccolo_verification_done/{}/wrapper.v".format(case))
d = os.path.join(RUN, "piccolo", case)
units = json.load(open(os.path.join(d, "units.json")))
models = os.path.join(d, "screen-models")
out = open(os.path.join(d, "screen.jsonl"), "w")

def check(assignment, label):
    info = ca.abstract_model(wrapper, "ila", units, assignment, models)
    r = ca.bmc_verdict(info, bound, limit)
    rec = {"label": label, "assignment": assignment, "bmc": r["bmc"], "cex_depth": r["cex_depth"],
           "bmc_seconds": round(r["bmc_seconds"], 1), "coi_state_bits": info["coi_state_bits"], "bound": bound}
    out.write(json.dumps(rec) + "\n"); out.flush(); print(json.dumps(rec), flush=True)
    return r["bmc"]

safe, inconclusive = {}, []
for u in units:
    safe[u["id"]] = "keep"
    for level in u["levels"][1:]:
        verdict = check({u["id"]: level}, "single")
        if verdict in ("NONE", "TIMEOUT"):
            safe[u["id"]] = level
            if verdict == "TIMEOUT":
                inconclusive.append(u["id"] + "=" + level)
        else:
            break
if check(safe, "combined") == "TIMEOUT":
    inconclusive.append("combined")
json.dump({"needed": sorted(k for k, v in safe.items() if v == "keep"), "safe_levels": safe,
           "inconclusive": inconclusive},
          open(os.path.join(d, "ground_truth.json"), "w"), indent=2)
