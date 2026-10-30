"""Hand-made split-then-abstract experiments (no LLM). Reuses src/case_study.py unchanged.

usage (from the work dir, which holds bench/, state.json): python3 run.py <exp> <variant> [--only k,k]
  fifo d|e     split c6 on sr_tail value (16 pieces); d = no abstraction, e = sr_mem slots above the tail freed
               (data only moves up the shift register, so slots above sr_tail cannot reach slot sr_tail)
  fifo f       as b but abstract_value (cut the register output to a free input; adds no state)
  lrg freev    as free but abstract_value
  fifo w       whole c6, no split, no abstraction (baseline)
  fifo a|b|c   split c6 on rb_tail value (16 pieces); a = no abstraction, b = other rb_mem freed,
               c = b + all sr_mem freed (sr is a shift register: no per-slot split)
  lrg  so|free  <i,j pairs>: both arbitrary requesters fixed; so = split only, free = also free other ranks
"""
import concurrent.futures, csv, json, os, sys, time
sys.path.insert(0, os.environ["SRC"])
import case_study as cs

C6 = "!rst & !srEmpty & !rbEmpty & (srFull == rbFull) & (srDataOut != rbDataOut)"
PAIRS = [(0, 1), (1, 0), (3, 4), (7, 8), (0, 15), (15, 0), (2, 11), (12, 5)]
JOBS, TIMEOUT = int(os.environ.get("JOBS", 4)), 300


def free(ids, op="abstract_state"):
    return [{"op": op, "target": t} for t in ids]


def fifo_pieces(variant):
    out = {}
    if variant == "w":
        return {"c6_whole_w": (C6, [])}
    if variant in ("d", "e"):
        for s in range(16):
            ops = free("sr_mem_%d" % j for j in range(s + 1, 16)) if variant == "e" else []
            out["c6_s%d_%s" % (s, variant)] = ("%s & (sr_tail == 4'd%d)" % (C6, s), ops)
        return out
    for k in range(16):
        ops = []
        if variant in ("b", "c", "f"):
            ops += free(("rb_mem_%d" % j for j in range(16) if j != k), "abstract_value" if variant == "f" else "abstract_state")
        if variant == "c":
            ops += free("sr_mem_%d" % j for j in range(16))
        out["c6_t%d_%s" % (k, variant)] = ("%s & (rb_tail == 4'd%d)" % (C6, k), ops)
    return out


def lrg_pieces(variant, pairs):
    out = {}
    for i, j in pairs:
        ops = free(("ranks_%d" % r for r in range(16) if r not in (i, j)), "abstract_value" if variant == "freev" else "abstract_state") if variant.startswith("free") else []
        cond = "chosen & (arbitrary_requester == 5'd%d) & (another_arbitrary_requester == 5'd%d)" % (i, j)
        out["p%d_%d_%s" % (i, j, variant)] = (cond, ops)
    return out


def main():
    exp, variant = sys.argv[1], sys.argv[2]
    st = cs.Study(".")
    if exp == "fifo":
        pieces, scope = fifo_pieces(variant), C6
        reg = "sr_tail" if variant in ("d", "e") else "rb_tail"
        cases = ["(%s == 4'd%d)" % (reg, k) for k in range(16)]
        ok, out = (True, "") if variant == "w" else st.coverage(scope, cases)
    else:
        pairs = [tuple(map(int, x.split(","))) for x in sys.argv[3:]] or PAIRS
        pieces = lrg_pieces(variant, pairs)
        ok, out = True, "pairs are samples, not a cover"
    print("coverage", ok, flush=True)
    assert ok, out
    rows = []

    def one(name):
        cond, ops = pieces[name]
        t0 = time.time()
        model = st.build(name, cond, ops)
        build_s = time.time() - t0
        v, secs, _ = st.ric3(model, TIMEOUT, name)
        st.s["pieces"][name] = {"cond": cond, "ops": ops, "tag": name, "status": "sat" if v == "SAT" else v}
        row = dict(exp=exp, variant=variant, piece=name, ops=len(ops), verdict=v, seconds=round(secs, 1),
                   build_s=round(build_s, 1), spurious="", load1=os.getloadavg()[0])
        if v == "SAT":
            try:
                real = cs.replay(st, name)[0]
                row["spurious"] = "no" if real else "yes"
            except Exception as e:  # replay is evidence only; keep the verdict
                row["spurious"] = "replay-error: %s" % e
        print(row, flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
        rows = list(ex.map(one, pieces))
    with open("results_%s_%s.csv" % (exp, variant), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print("DONE", flush=True)


main()
