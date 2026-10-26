"""evaluate.py <case>...: judge every refinement step of every arm (P-cores, untimed).

A step that refines unit u at assignment A, whose counterexample has depth k, is
- needed: A[u] is coarser than the coarsest level of u without a counterexample in the ground truth;
- removing: the model with only u refined has no counterexample up to depth k (rIC3 BMC).
The BMC checks use their own models directory, so the timed models directory is not touched.
"""
import json, os, re, sys
sys.path.insert(0, os.path.expanduser("~/.agent-worktrees/NeuroAbs-llm-refine/src"))
import choice_abstraction as ca
RUN = "/var/tmp/neuroabs-runtime/runs/llm-refine-20261026"
ARMS = ["one", "all", "bmc", "llm-1", "llm-2", "llm-3"]

def deepest_bmc(log):
    depths = []
    for line in open(log):
        m = re.search(r"\] (bmc\S*) proved at depth (\d+)", line)
        if m:
            depths.append(int(m.group(2)))
    return max(depths) if depths else None

for case in sys.argv[1:]:
    d = os.path.join(RUN, "piccolo", case)
    wrapper = os.path.expanduser("~/.agent-worktrees/NeuroAbs-llm-refine/Piccolo_verification_done/{}/wrapper.v".format(case))
    units = json.load(open(os.path.join(d, "units.json")))
    truth = json.load(open(os.path.join(d, "ground_truth.json")))["safe_levels"]
    rows = []
    for arm in ARMS:
        path = os.path.join(d, "arms", arm, "cegar.json")
        if not os.path.exists(path):
            continue
        result = json.load(open(path))
        steps = []
        for r in result["history"]:
            for u in r.get("refined_units") or []:
                levels = next(x["levels"] for x in units if x["id"] == u)
                needed = levels.index(r["assignment"][u]) > levels.index(truth[u])
                info = ca.abstract_model(wrapper, "ila", units, ca.finer(units, r["assignment"], u),
                                         os.path.join(d, "eval-models"))
                removing = ca.bmc_verdict(info, r["cex_depth"], 900)["bmc"]
                steps.append({"iteration": r["iteration"], "unit": u, "from": r["assignment"][u], "needed": needed,
                              "removing": removing, "cex_depth": r["cex_depth"],
                              "probabilities": (r.get("selection") or {}).get("probabilities")})
        h = result["history"]
        last = h[-1]
        sel = [r.get("selection") or {} for r in h]
        llm_seconds = sum(s.get("llm_seconds", 0) for s in sel)
        log = "{}.ric3-300.log".format(last["model"])
        rows.append({
            "case": case, "arm": arm, "status": result["status"], "refinements": result["refinements"],
            "steps": steps, "final_assignment": result["final_assignment"], "final_coi_state_bits": last["coi_state_bits"],
            "final_deepest_bmc": deepest_bmc(log) if last["ric3"] == "TIMEOUT" else None,
            "optimal": result["final_assignment"] == truth,
            "total_seconds": result["total_seconds"],
            "refinement_seconds": sum(r["build_seconds"] + r["ric3_seconds"] + r.get("replay_seconds", 0)
                                      + r.get("selection_seconds", 0) for r in h[:-1]),
            "ric3_build_seconds": sum(r["build_seconds"] + r["ric3_seconds"] for r in h),
            "selection_seconds": sum(r.get("selection_seconds", 0) for r in h),
            "llm_seconds": llm_seconds,
            "llm_cost_usd": sum(s.get("cost_usd", 0) for s in sel),
        })
    with open(os.path.join(d, "evaluation.json"), "w") as f:
        json.dump(rows, f, indent=2)
    for row in rows:
        print(case, row["arm"], row["status"], row["refinements"],
              " ".join("{}{}{}".format(s["unit"][:4], "+" if s["needed"] else "-", "r" if s["removing"] == "NONE" else "")
                       for s in row["steps"]),
              row["final_coi_state_bits"], row["final_deepest_bmc"], round(row["refinement_seconds"], 1),
              round(row["llm_seconds"], 1))
