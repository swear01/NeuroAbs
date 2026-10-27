"""training.py <run dir> <batch> <arm>...: training results of LLM rules on the ADDI sample, selection and feedback.

For every arm (a rule file name without .py, specs in <run>/specs/ADDI/<arm>.jsonl) and every training sub-property:
the rIC3 status (or "rejected"), the refinements, the refined choice ids in order, the final COI state bits and the
time.  Writes <run>/training/<batch>.json with the per-arm totals and the ranking of the pre-registered selection
(more UNSAT, then fewer rejected, then fewer final COI state bits over the non-rejected sub-properties, then less total
time, then the order of the arguments), and <run>/training/<batch>-feedback-<model>.json with the feedback message of
every arm of a model (arm <model>-<i>: sample i).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
import fine_choice as fc  # noqa: E402

PROBLEMS = os.path.join(REPO, "results", "llm_rule_heldout", "problems", "ADDI")
FEEDBACK = """Your rule was applied to {n:d} training sub-properties of this design. Each abstract model was checked \
with rIC3 (300 seconds per proof attempt, at most 10 refinements). The results, one line per sub-property: name, \
case, result, number of refinements, and the choices that refinement moved towards "keep", in order:

{lines}

Results: UNSAT means proved. TIMEOUT means a proof attempt ran out of time; it gives no counterexample, so it cannot \
be refined. max_iterations means the model still had a counterexample after 10 refinements. real means a \
counterexample without unconstrained values of any choice. rejected means that the rule failed on the sub-property \
(the error is given) and nothing was checked.

You may revise the rule. Answer as before, with exactly one Python code block that contains the whole module."""


def jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def refined_choices(spec, iterations, units, candidates):
    """Replay fine_choice.refine to name the choice that each refinement moved (in the ids of the rule's menu)."""
    ids = {(c["ila"], c["rtl"]): "uf{:d}".format(i) for i, c in enumerate(candidates)}
    out = []
    for it in iterations[:-1]:
        counts = it["counterexample_units"] or {}
        if counts:
            target = min(counts, key=lambda k: (-counts[k], k))
            if target.startswith("uf"):
                u = spec["uf"][int(target[2:])]
                out.append(ids[(u["ila"], u["rtl"])])
            else:
                out.append(target)
        else:
            out.append("word GPRs " + ",".join("gpr{:d}".format(j) for j in spec.get("word_gprs", [])))
        spec = fc.refine(spec, units, counts)
    return out


def main():
    run, batch = sys.argv[1:3]
    arms = sys.argv[3:]
    with open(os.path.join(PROBLEMS, "subs-sample.json")) as f:
        subs = json.load(f)
    with open(os.path.join(PROBLEMS, "units.json")) as f:
        units = json.load(f)
    with open(os.path.join(PROBLEMS, "candidates.json")) as f:
        candidates = json.load(f)
    with open(os.path.join(run, "batches", "ADDI", "train.map.json")) as f:
        mapping = json.load(f)
    results = {r["name"]: r for r in jsonl(os.path.join(run, "runs", "ADDI", "train", "results.jsonl"))}
    table, feedback = {}, {}
    for arm in arms:
        specs = {r["name"]: r["spec"] for r in jsonl(os.path.join(run, "specs", "ADDI", arm + ".jsonl"))}
        with open(os.path.join(run, "specs", "ADDI", arm + ".jsonl.rejected.json")) as f:
            rejected = json.load(f)
        rows, lines = [], []
        for s in subs:
            name = s["name"]
            if name in rejected:
                row = {"sub": name, "status": "rejected", "errors": rejected[name]}
                lines.append("- {:s} (case {}): rejected: {:s}".format(name, s.get("case"), "; ".join(rejected[name])))
            else:
                r = results[mapping[arm][name]]
                if r["status"] == "ERROR":
                    raise SystemExit("run {:s} of {:s} has status ERROR".format(r["name"], arm))
                row = {"sub": name, "run": r["name"], "status": r["status"], "refinements": r["refinements"],
                       "refined": refined_choices(specs[name], r["iterations"], units, candidates),
                       "final_coi_state_bits": r["final_coi_state_bits"], "seconds": r["total_seconds"]}
                lines.append("- {:s} (case {}): {:s}, {:d} refinements{:s}".format(
                    name, s.get("case"), row["status"], row["refinements"],
                    ": " + ", ".join(row["refined"]) if row["refined"] else ""))
            rows.append(row)
        checked = [r for r in rows if r["status"] != "rejected"]
        table[arm] = {"unsat": sum(r["status"] == "UNSAT" for r in rows),
                      "rejected": len(rows) - len(checked),
                      "final_coi_state_bits": sum(r["final_coi_state_bits"] for r in checked),
                      "seconds": round(sum(r["seconds"] for r in checked), 1),
                      "refinements": sum(r["refinements"] for r in checked), "subs": rows}
        model, sample = arm.rsplit("-", 1)
        feedback.setdefault(model, {})[sample] = FEEDBACK.format(n=len(subs), lines="\n".join(lines))
    ranking = sorted(arms, key=lambda a: (-table[a]["unsat"], table[a]["rejected"], table[a]["final_coi_state_bits"],
                                          table[a]["seconds"], arms.index(a)))
    os.makedirs(os.path.join(run, "training"), exist_ok=True)
    with open(os.path.join(run, "training", batch + ".json"), "w") as f:
        json.dump({"ranking": ranking, "arms": table}, f, indent=1)
    for model, messages in feedback.items():
        with open(os.path.join(run, "training", "{:s}-feedback-{:s}.json".format(batch, model)), "w") as f:
            json.dump(messages, f, indent=1)
    for a in ranking:
        t = table[a]
        print(a, t["unsat"], t["rejected"], t["final_coi_state_bits"], t["seconds"], t["refinements"])


if __name__ == "__main__":
    main()
