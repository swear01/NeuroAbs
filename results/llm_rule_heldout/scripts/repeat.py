"""repeat.py <run dir> <case>...: the repeated timing of PREREG.md section 7.

For each case, each LLM arm and each non-LLM arm: the sub-properties that both prove (UNSAT), in sample order; the
first 3 of them, with the spec of each of the two arms, are run 3 more times.  Writes <run>/batches/<case>/rep.jsonl
(run names <test run name>.r<k>) and rep.map.json (pairs, sub-properties and the test run names).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBLEMS = os.path.join(HERE, "..", "problems")
LLM = ["deepseek-fb4", "claude-fb2"]
BASE = ["split", "S", "auto"]
REPS = 3


def jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    run = sys.argv[1]
    for case in sys.argv[2:]:
        with open(os.path.join(run, "batches", case, "test.map.json")) as f:
            mapping = json.load(f)
        specs = {r["name"]: r["spec"] for r in jsonl(os.path.join(run, "batches", case, "test.jsonl"))}
        results = {r["name"]: r for r in jsonl(os.path.join(run, "runs", case, "test", "results.jsonl"))}
        with open(os.path.join(PROBLEMS, case, "subs-sample.json")) as f:
            order = [s["name"] for s in json.load(f)]
        pairs, runs = [], {}
        for llm in LLM:
            for base in BASE:
                common = [s for s in order if results[mapping[llm][s]]["status"] == "UNSAT"
                          and results[mapping[base][s]]["status"] == "UNSAT"][:REPS]
                pairs.append({"llm": llm, "base": base, "subs": common,
                              "runs": {s: [mapping[llm][s], mapping[base][s]] for s in common}})
                for s in common:
                    for name in (mapping[llm][s], mapping[base][s]):
                        for k in range(1, REPS + 1):
                            runs["{:s}.r{:d}".format(name, k)] = {"name": "{:s}.r{:d}".format(name, k),
                                                                  "spec": specs[name]}
        with open(os.path.join(run, "batches", case, "rep.jsonl"), "w") as f:
            for r in runs.values():
                f.write(json.dumps(r) + "\n")
        with open(os.path.join(run, "batches", case, "rep.map.json"), "w") as f:
            json.dump(pairs, f, indent=1)
        print(json.dumps({"case": case, "runs": len(runs), "pairs": [(p["llm"], p["base"], len(p["subs"]))
                                                                      for p in pairs]}))


if __name__ == "__main__":
    main()
