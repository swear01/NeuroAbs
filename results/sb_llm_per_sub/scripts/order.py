"""order.py <heldout run dir> <arm> <out.jsonl>: llm_rule_heldout/scripts/specs.py for SB with the operator candidates
of problems/SB/candidates.json in reverse order (eaddr first, h5583 last).  <arm> is S or a rule path."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "results", "llm_rule_heldout", "scripts"))
import specs  # noqa: E402

load = specs.load


def reversed_load(case, name):
    data = load(case, name)
    return data[::-1] if name == "candidates.json" else data


def main():
    run, arm, out = sys.argv[1:4]
    specs.load = reversed_load
    subs = load("SB", "subs-sample.json")
    result, rejected = specs.arm_specs(os.path.abspath(run), "SB", arm, subs)
    if rejected:
        raise RuntimeError("rejected: {}".format(rejected))
    with open(out, "w") as f:
        for s in subs:
            f.write(json.dumps({"name": s["name"], "spec": result[s["name"]]}) + "\n")


if __name__ == "__main__":
    main()
