"""Per-run LLM cost of adaptive-flow runs: python llm_cost_summary.py RUNS_DIR...  One row per <bench>-<mode>-<n> dir.
Runs without state.json (fifo_ref_64 in results/decide_fix) get LLM columns only.
Prompt KB is the last user message of each first attempt (what prompt_size.py measures); timeouts are counted from run.out (or its saved count, llm_timeouts.txt)."""
import os
import re
import statistics as S
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ablation_summary import jl, row  # noqa: E402


def cost(d, bench):
    wall = d + "/wall_s.txt"
    r = (row(d, bench) if os.path.exists(d + "/state.json") else
         dict(verdict="-", rounds="-", wall=float(open(wall).read()) if os.path.exists(wall) else None))
    calls = jl(d + "/llm_calls.jsonl")
    kb = {k: [len(c["prompt"][-1]["content"]) / 1000 for c in calls if c["step"] == k and c.get("note") == "attempt 1"]
          for k in ("decide", "cegar_refine")}
    out = os.path.join(d, "run.out")
    saved = os.path.join(d, "llm_timeouts.txt")  # the count kept in results/ instead of the whole run.out
    tmo = (open(out).read().count("LLM request timed out") if os.path.exists(out)
           else int(open(saved).read()) if os.path.exists(saved) else None)
    lat = [c["latency_s"] for c in calls]
    return dict(verdict=r["verdict"].split(" ")[0] if r["verdict"] != "UNSOLVED llm_timeout" else "llm_timeout", wall=r["wall"],
                rounds=r["rounds"], decide=len(kb["decide"]), refine=len(kb["cegar_refine"]),
                decide_kb_max=max(kb["decide"], default=0), refine_kb_max=max(kb["cegar_refine"], default=0),
                prompt_kb=sum(len(c["prompt"][-1]["content"]) for c in calls) / 1000,
                out_tok=sum(c["output_tokens"] or 0 for c in calls), lat_mean=S.mean(lat) if lat else 0,
                lat_max=max(lat, default=0), llm_s=sum(lat), timeouts=tmo)


if __name__ == "__main__":
    print("| run | verdict | rounds | wall s | decide | refine | decide KB max | refine KB max | prompt KB total | output tok | latency mean/max s | LLM s | timeouts |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for root in sys.argv[1:]:
        for n in sorted(os.listdir(root)):
            m = re.match(r"(.+)-(hint|nohint|large)-(\d+)$", n)
            if not (m and os.path.exists(f"{root}/{n}/llm_calls.jsonl")):
                continue
            c = cost(f"{root}/{n}", m.group(1))
            v = "**proved**" if c["verdict"] == "PROVED" else c["verdict"].lower()
            print(f"| {n} | {v} | {c['rounds']} | {c['wall'] or 0:.0f} | {c['decide']} | {c['refine']} | {c['decide_kb_max']:.1f} | "
                  f"{c['refine_kb_max']:.1f} | {c['prompt_kb']:.0f} | {c['out_tok']} | {c['lat_mean']:.0f}/{c['lat_max']:.0f} | "
                  f"{c['llm_s']:.0f} | {'-' if c['timeouts'] is None else c['timeouts']} |")
