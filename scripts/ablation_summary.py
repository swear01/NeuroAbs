"""Summarise adaptive-flow run dirs: python ablation_summary.py RUNS_DIR [--mean]. One row per <bench>-<mode>-<n> dir."""
import json, os, re, statistics as S, sys
QIDX = {"lrg_arb": {"arbitrary_requester", "another_arbitrary_requester"}, "fifo_vis": {"rb_tail", "rb_head", "sr_tail", "sr_head"},
        "simple_cam_8": {"chosen_push_id", "lookup_id"}, "fifo_ref_16": {"fv_env_ref_fifo_head", "dut_head"},
        "simple_cam_16": {"chosen_push_id", "lookup_id"}, "fifo_ref_64": {"fv_env_ref_fifo_head", "dut_head"}}


def jl(p):
    return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


def row(d, bench):
    st = json.load(open(d + "/state.json"))
    ev, calls = jl(d + "/tool_events.jsonl"), jl(d + "/llm_calls.jsonl")
    ps = st["pieces"]
    r1 = [v["cond"] for k, v in ps.items() if k.startswith("r1_")]
    first = sorted({i for c in r1 for i in re.findall(r"[A-Za-z_]\w*", c) if not re.fullmatch(r"d\d+", i)})
    leaves = {k: v for k, v in ps.items() if v["status"] != "split"}
    ok = all(v["status"] == "proved" for v in leaves.values())
    st_ = {v["status"] for v in leaves.values()} - {"proved"}
    ops = sum(1 for v in ps.values() if v["ops"])
    ric3 = sum(e["wall_s"] for e in ev if e["kind"] in ("check_pass", "summary_pass"))
    ld = [e["load"][0] for e in ev if e["kind"] == "load" and e["cmd"] == "run"]
    decs = [(c["step"], c["round"], c["verdict"][:20]) for c in calls]
    wall = float(open(d + "/wall_s.txt").read()) if os.path.exists(d + "/wall_s.txt") else None
    return dict(bench=bench, wall=wall, llm=sum(c["latency_s"] for c in calls), ric3=ric3, first=first,
                idx=bool(set(first) & QIDX[bench]), leaves=len(leaves), rounds=max(v["round"] for v in ps.values()),
                abs=ops, verdict="UNSOLVED llm_timeout" if st.get("unsolved") else "PROVED" if ok else "UNRESOLVED " + ",".join(sorted(st_)), calls=len(calls),
                rejected=sum(1 for c in calls if str(c["verdict"]).startswith("rejected")), decs=decs,
                load=(ld[0] if ld else None, ld[-1] if ld else None))


if __name__ == "__main__":
    root = sys.argv[1]
    rows = {}
    for n in sorted(os.listdir(root)):
        m = re.match(r"(.+)-(hint|nohint|large)-(\d+)$", n)
        if m and os.path.exists(f"{root}/{n}/state.json"):
            rows[n] = row(f"{root}/{n}", m.group(1))
    for n, r in rows.items():
        f = lambda x: "-" if x is None else f"{x:.0f}"
        print(f"{n:24s} wall {f(r['wall']):>5s} llm {r['llm']:5.1f} ric3 {r['ric3']:6.1f} first={','.join(r['first'])[:40]:40s} idx={r['idx']!s:5} "
              f"leaves={r['leaves']:2d} rounds={r['rounds']} abs={r['abs']} calls={r['calls']}(rej {r['rejected']}) {r['verdict']} load {r['load'][0] and round(r['load'][0][0] if False else r['load'][0],1)}->{r['load'][1] and round(r['load'][1],1)}")
    if "--mean" in sys.argv:
        g = {}
        for n, r in rows.items():
            g.setdefault(re.sub(r"-\d+$", "", n), []).append(r)
        for k, rs in g.items():
            w = [r["wall"] for r in rs if r["wall"]]
            if not w:
                continue
            print(f"{k:22s} n={len(rs)} wall mean {S.mean(w):6.1f} sd {S.pstdev(w):5.1f} min {min(w):.0f} max {max(w):.0f} | idx first {sum(r['idx'] for r in rs)}/{len(rs)} | proved {sum(r['verdict']=='PROVED' for r in rs)}/{len(rs)}")
