"""Offline prompt sizes: rebuild the decide and refine prompts of finished runs with the current src/case_study.py and
compare them with the logged ones.  No LLM calls; refine rebuilds the abstract model (Yosys) to get the cone, so run it
on a COPY of the workdir that keeps bench/, state.json, tool_events.jsonl, llm_calls.jsonl and logs/<piece>_k*.log.
usage: python scripts/prompt_size.py WORKDIR...   (prints one JSON line per logged call)"""
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import case_study as cs  # noqa: E402


def short(text):
    """Old lemma summary text -> the current format."""
    if text.startswith("IC3 alone") or text.startswith("IC3 "):
        return text
    d = re.search(r"reached depth (\d+)", text)
    f = re.search(r"lemmas per frame at the end \[([^\]]*)\]", text)
    m = re.search(r"have ([\d.]+) literals on average out of (\S+) state bits", text)
    s = "IC3 {:d} s: depth {:s}".format(cs.SUMMARY_S, d.group(1) if d else "0")
    if f:
        s += ", lemmas in last frames [{:s}]".format(", ".join(f.group(1).split(", ")[-4:]))
    if m:
        s += ", lemmas {:s}/{:s} state bits".format(m.group(1), m.group(2))
    return s


def one(wd):
    st = cs.Study(wd)
    final = copy.deepcopy(st.s["pieces"])
    ev = [json.loads(x) for x in open(os.path.join(st.dir, "tool_events.jsonl"))]
    calls = [json.loads(x) for x in open(os.path.join(st.dir, "llm_calls.jsonl"))]
    for c in calls:
        if c.get("note") != "attempt 1" or c["step"] not in ("decide", "cegar_refine"):
            continue
        old = c["prompt"][-1]["content"]
        rnd = c["round"]
        before = [e for e in ev if e["time"] < c["timestamp"]]
        pieces = copy.deepcopy(final)
        for e in before:  # operators and model tag as they were when the call was made
            if e["kind"] == "check":
                pieces[e["piece"]].update(ops=e["ops"], tag=e["tag"])
        st.s.update(round=rnd, pieces=pieces)
        out = dict(run=os.path.basename(wd.rstrip("/")), call=c["call"], step=c["step"], round=rnd, old_bytes=len(old),
                   output_tokens=c["output_tokens"], latency_s=c["latency_s"])
        if c["step"] == "decide":
            todo = re.findall(r"^- (r\d+_c\d+): case ", old, flags=re.M)
            sums = {e["piece"]: (e["verdict"], short(e["text"])) for e in before if e["kind"] == "summary" and e["round"] == rnd}
            rows = [(p, v, float(x)) for p, v, x in re.findall(r"^- (r\d+_c\d+): (\w+) ([\d.]+) s", old, flags=re.M)]
            auto = re.findall(r"^- (r\d+_c\d+): \w+ [\d.]+ s \(already split", old, flags=re.M)
            groups = cs.decide_groups(st, todo)
            sizes = []
            for k in range(0, len(groups), cs.DECIDE_GROUPS):
                gids = {"g{:d}".format(k + i + 1): g for i, g in enumerate(groups[k:k + cs.DECIDE_GROUPS])}
                sizes.append(len(cs.decide_prompt(st, gids, rows, sums, auto, 0, 0, 20)))
            out.update(pieces=len(todo), groups=len(groups), new_calls=len(sizes), new_bytes=sum(sizes), new_max_bytes=max(sizes))
        else:
            p = re.search(r"Piece (\S+) \(case", old).group(1)
            real, depth, table, bad, coi = cs.replay(st, p)
            pieces[p]["cex"] = {"depth": depth, "table": table, "coi": coi}
            out.update(piece=p, coi_cells=None if coi is None else len(coi), new_bytes=len(cs.refine_prompt(st, p)))
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    for wd in sys.argv[1:]:
        one(os.path.abspath(wd))
