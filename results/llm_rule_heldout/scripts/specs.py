"""specs.py <run dir> <case> <arm> <out.jsonl>: the specs of one arm on the sampled sub-properties of a case.

<arm> is split, S, auto, or the path of an LLM rule (rule-*.py).  The non-LLM arms are those of the pre-registered
semantic_candidates/scripts/rules.py: split is its COI rule with nothing removed (every unit kept, every GPR kept, no
operator pair), S is fine_choice.structural and auto is fine_choice.coarsest, both with the matcher pairs
(s_pairs.json).  An LLM rule gets the design of the case (named wrapper, every pair candidate) and is applied without
repair; the sub-properties that it rejects are written to <out>.rejected.json and get no spec.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
import fine_choice as fc  # noqa: E402
import fine_choice_llm  # noqa: E402
import llm_rule  # noqa: E402
import llm_rule_exec  # noqa: E402
from choice_llm import unit_ports  # noqa: E402

PROBLEMS = os.path.join(REPO, "results", "llm_rule_heldout", "problems")


def load(case, name):
    with open(os.path.join(PROBLEMS, case, name)) as f:
        return json.load(f)


def design(run, case):
    wrapper = os.path.join(run, "problems", case, "wrapper.v")
    with open(wrapper) as f:
        text = f.read()
    units = load(case, "units.json")
    ufs = fine_choice_llm.uf_details(text, load(case, "candidates.json"))
    with open(os.path.join(REPO, "Piccolo_verification_done", case, "description.txt")) as f:
        description = f.read()
    workdir = os.path.join(run, "problems", case, "hier")
    os.makedirs(workdir, exist_ok=True)
    ports = unit_ports([c for c in fine_choice_llm.menu(units, ufs) if "path" in c], wrapper, workdir)
    return text, ufs, llm_rule.design_input(text, units, ufs, ports, description)


def arm_specs(run, case, arm, subs):
    units = load(case, "units.json")
    pairs = load(case, "s_pairs.json")
    if arm == "split":
        return {s["name"]: {"states": s["states"], "case": s.get("case"), "rd_guard": False, "keep_gprs": "all",
                            "units": {}, "uf": []} for s in subs}, {}
    if arm == "S":
        return {s["name"]: fc.structural(s, units, pairs) for s in subs}, {}
    if arm == "auto":
        return {s["name"]: fc.coarsest(s, units, pairs) for s in subs}, {}
    with open(arm) as f:
        source = f.read()
    errors = llm_rule_exec.validate(source)
    if errors:
        return {}, {s["name"]: errors for s in subs}
    text, ufs, d = design(run, case)
    return llm_rule.apply_rule(source, d, [llm_rule.sub_input(s, text) for s in subs], subs, ufs)


def main():
    run, case, arm, out = sys.argv[1:5]
    subs = load(case, "subs-sample.json")
    specs, rejected = arm_specs(os.path.abspath(run), case, arm, subs)
    with open(out, "w") as f:
        for s in subs:
            if s["name"] in specs:
                f.write(json.dumps({"name": s["name"], "spec": specs[s["name"]]}) + "\n")
    with open(out + ".rejected.json", "w") as f:
        json.dump(rejected, f, indent=1)
    print(json.dumps({"case": case, "arm": arm, "specs": len(specs), "rejected": len(rejected)}))


if __name__ == "__main__":
    main()
