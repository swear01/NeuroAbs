"""collect.py: tables for the README from the evaluation, arm and final-model artifacts."""
import json, os, re, statistics
RUN = "/var/tmp/neuroabs-runtime/runs/llm-refine-20261026"
CASES = open(os.path.join(RUN, "cases.txt")).read().split()
SHORT = {"csr_regfile": "csr", "gpr_regfile_regfile": "gpr", "near_mem_dcache": "dcache", "near_mem_icache": "icache",
         "stageF_branch_predictor": "bp"}
ARMS = ["one", "all", "bmc", "llm"]
rows = {c: json.load(open(os.path.join(RUN, "piccolo", c, "evaluation.json"))) for c in CASES}

def arm_rows(arm):
    return [r for c in CASES for r in rows[c] if r["arm"] == arm or (arm == "llm" and r["arm"].startswith("llm"))]

def steps_text(r):
    out = []
    for it in sorted({s["iteration"] for s in r["steps"]}):
        ss = [s for s in r["steps"] if s["iteration"] == it]
        out.append("+".join("{}{}{}".format(SHORT[s["unit"]], "" if s["needed"] else "✗",
                                            "*" if s["removing"] == "NONE" else "") for s in ss))
    return " → ".join(out)

print("## Per arm, all 12 cases (LLM: 3 repeats each)\n")
print("| Arm | Runs | Final = optimal | Refinements | Steps on needed units | Steps removing the cex | Final COI bits | Refinement s (median) | of which LLM s | DeepSeek USD |")
print("| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |")
for arm in ARMS:
    rs = arm_rows(arm)
    steps = [s for r in rs for s in r["steps"]]
    print("| {} | {} | {} | {} | {}/{} | {}/{} | {} | {:.0f} | {:.0f} | {:.3f} |".format(
        arm, len(rs), sum(r["optimal"] for r in rs),
        "/".join(str(x) for x in sorted({r["refinements"] for r in rs})),
        sum(s["needed"] for s in steps), len(steps), sum(s["removing"] == "NONE" for s in steps), len(steps),
        "/".join("{:,}".format(x) for x in sorted({r["final_coi_state_bits"] for r in rs})),
        statistics.median(r["refinement_seconds"] for r in rs),
        statistics.median(r["llm_seconds"] for r in rs), sum(r["llm_cost_usd"] for r in rs)))
print("\n## Per case: refinement seconds (time before the final model) and steps\n")
print("| Case | one | all | bmc | llm (3 runs) | Steps one | Steps bmc | Steps llm |")
print("| --- | ---: | ---: | ---: | --- | --- | --- | --- |")
for c in CASES:
    by = {r["arm"]: r for r in rows[c]}
    llm = [by["llm-{}".format(i)] for i in (1, 2, 3)]
    llm_steps = {steps_text(r) for r in llm}
    print("| {} | {:.0f} | {:.0f} | {:.0f} | {} | {} | {} | {} |".format(
        c, by["one"]["refinement_seconds"], by["all"]["refinement_seconds"], by["bmc"]["refinement_seconds"],
        ", ".join("{:.0f} ({:.0f})".format(r["refinement_seconds"], r["llm_seconds"]) for r in llm),
        steps_text(by["one"]), steps_text(by["bmc"]), " / ".join(sorted(llm_steps))))
print("\nall steps:", {c: steps_text(next(r for r in rows[c] if r["arm"] == "all")) for c in CASES[:1]})
