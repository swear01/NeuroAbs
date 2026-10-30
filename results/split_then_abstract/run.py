"""Hand-made split-then-abstract experiments (no LLM). Reuses src/case_study.py unchanged.

usage (from the work dir, which holds bench/, state.json): python3 run.py <exp> <variant> [<i,j> ...]
(SRC = path to NeuroAbs src/; JOBS = parallel rIC3 runs; <i,j> pairs apply to lrg only)
  fifo d|e     split c6 on sr_tail value (16 pieces); d = no abstraction, e = sr_mem slots above the tail freed
               (data only moves up the shift register, so slots above sr_tail cannot reach slot sr_tail)
  fifo f       as b but abstract_value (cut the register output to a free input; adds no state)
  lrg freev    as free but abstract_value
  fifo g|h     as b with a real cut (register deleted, output a free input); h also cuts all sr_mem
  lrg  cut     as free with a real cut
  fifo w       whole c6, no split, no abstraction (baseline)
  fifo a|b|c   split c6 on rb_tail value (16 pieces); a = no abstraction, b = other rb_mem freed,
               c = b + all sr_mem freed (sr is a shift register: no per-slot split)
  lrg  so|free  <i,j pairs>: both arbitrary requesters fixed; so = split only, free = also free other ranks
"""
import concurrent.futures, csv, os, re, sys, time
sys.path.insert(0, os.environ["SRC"])
import case_study as cs

_op_commands = cs.Study.op_commands


def op_commands(self, ops):
    """Add op "cut": delete the register driving the target; setundef -anyseq in build then makes its output a free input."""
    ids, out = self.ident_map(), []
    for op in ops:
        if op["op"] == "cut":
            out.append("delete w:%s %%ci1 c:* %%i" % ids[op["target"]]["name"].replace("[", "\\[").replace("]", "\\]"))
        else:
            out += _op_commands(self, [op])
    return out


cs.Study.op_commands = op_commands

C6 = "!rst & !srEmpty & !rbEmpty & (srFull == rbFull) & (srDataOut != rbDataOut)"
PAIRS = [(0, 1), (1, 0), (3, 4), (7, 8), (0, 15), (15, 0), (2, 11), (12, 5)]
JOBS, TIMEOUT = int(os.environ.get("JOBS", 4)), 300


def free(ids, op="abstract_state"):
    return [{"op": op, "target": t} for t in ids]


def fifo_pieces(variant):
    out = {}
    if variant == "w":
        return {"c6_whole_w": (C6, [])}
    if variant in ("g", "h"):
        for k in range(16):
            ops = free(("rb_mem_%d" % j for j in range(16) if j != k), "cut")
            if variant == "h":
                ops += free(("sr_mem_%d" % j for j in range(16)), "cut")
            out["c6_t%d_%s" % (k, variant)] = ("%s & (rb_tail == 4'd%d)" % (C6, k), ops)
        return out
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
        ops = free(("ranks_%d" % r for r in range(16) if r not in (i, j)), {"freev": "abstract_value", "cut": "cut"}.get(variant, "abstract_state")) if variant.startswith("free") or variant == "cut" else []
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
    if not ok:
        raise RuntimeError(out)

    def one(name):
        cond, ops = pieces[name]
        t0 = time.time()
        model = st.build(name, cond, ops)
        build_s = time.time() - t0
        path = os.path.join(st.dir, model)
        text = open(path).read()
        # a state with no next and no init is already free every cycle (what abstract/cut leave behind): make it an input
        driven = set(re.findall(r"^\d+ (?:next|init) \d+ (\d+)", text, re.M))
        free_states = [m for m in re.findall(r"^(\d+) state ", text, re.M) if m not in driven]
        text = re.sub(r"^(\d+) state ", lambda m: m.group(1) + (" input " if m.group(1) in free_states else " state "), text, flags=re.M)
        open(path, "w").write(text)
        v, secs, _ = st.ric3(model, TIMEOUT, name)
        st.s["pieces"][name] = {"cond": cond, "ops": ops, "tag": name, "status": "sat" if v == "SAT" else v}
        row = dict(exp=exp, variant=variant, piece=name, ops=len(ops), verdict=v, seconds=round(secs, 1),
                   build_s=round(build_s, 1), states=len(re.findall(r"^\d+ state ", text, re.M)), freed_to_input=len(free_states),
                   inputs=len(re.findall(r"^\d+ input ", text, re.M)), lines=text.count("\n"), spurious="", load1=os.getloadavg()[0])
        if v == "SAT":
            real = cs.replay(st, name)[0]
            row["spurious"] = "no" if real else "yes"
        print(row, flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
        rows = list(ex.map(one, pieces))
    with open("results_%s_%s.csv" % (exp, variant), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print("DONE", flush=True)


main()
