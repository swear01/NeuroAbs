"""reptime.py <case>...: the repeated timing of PREREG.md section 7 (sections 9: on mazu), as Markdown.

Reads runs/<case>/batches/rep.map.json and runs/<case>/rep.jsonl of this directory.  For every LLM x non-LLM pair and
sub-property: the 3 total times of each arm and the ratio of the medians (LLM / non-LLM).
"""
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "runs")
LABEL = {"split": "split (COI)", "auto": "auto", "S": "S", "deepseek-fb4": "DeepSeek fb4", "claude-fb2": "Claude fb2"}


def main():
    for case in sys.argv[1:]:
        with open(os.path.join(RUNS, case, "batches", "rep.map.json")) as f:
            pairs = json.load(f)
        with open(os.path.join(RUNS, case, "rep.jsonl")) as f:
            results = {r["name"]: r for r in map(json.loads, f) if r}
        print("\n#### {:s}\n".format(case))
        print("| LLM | 對照 | sub-property | LLM 時間 s | 對照時間 s | 中位數比 |")
        print("| --- | --- | --- | --- | --- | ---: |")
        for p in pairs:
            for s in p["subs"]:
                times = []
                for name in p["runs"][s]:
                    rows = [results["{:s}.r{:d}".format(name, k)] for k in (1, 2, 3)]
                    if any(r["status"] != "UNSAT" for r in rows):
                        raise SystemExit("{:s} {:s}: a repeat is not UNSAT".format(case, name))
                    times.append([r["total_seconds"] for r in rows])
                same = " (同一 spec)" if p["runs"][s][0] == p["runs"][s][1] else ""
                print("| {:s} | {:s} | `{:s}`{:s} | {:s} | {:s} | {:.2f} |".format(
                    LABEL[p["llm"]], LABEL[p["base"]], s, same, "、".join("{:.0f}".format(t) for t in times[0]),
                    "、".join("{:.0f}".format(t) for t in times[1]),
                    statistics.median(times[0]) / statistics.median(times[1])))


if __name__ == "__main__":
    main()
