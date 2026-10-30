"""Case study: DeepSeek drives an adaptive tree of splits (and class-A abstractions) on one design (issues #23, #25).

`run` is the whole flow: an initial split, then rounds of (parallel rIC3 check with a short cap -> replay of SAT
pieces -> LLM decision for the pieces that timed out: resplit / abstract / both).  State lives in
<workdir>/state.json and every LLM call is one record of <workdir>/llm_calls.jsonl.  The tools (Yosys, SAT
coverage check, rIC3, replay) judge every answer; the LLM only splits and picks class-A operators.
"""
import argparse
import concurrent.futures
import json
import os
import re
import signal
import subprocess
import sys
import time
import types

# deepseek_chat -> luna_api imports the Pyverilog based checker, which this study does not use.
sys.modules.setdefault("check", types.SimpleNamespace(check_implies=None))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import btor_witness  # noqa: E402
import deepseek_chat  # noqa: E402
from deepseek_prices import usage_cost  # noqa: E402

RIC3 = "/var/tmp/agentic-ic3-tools/ric3-master-4d63899/target/release/ric3"
MAX_CALLS, MAX_ROUNDS = 40, 8
PARALLEL = 8       # pieces checked at once (rIC3 portfolio each; they share cores)
CAPS = (3, 20, 120)  # rIC3 cap per piece in seconds: rounds 1-2, 3-4, 5+
MAX_NEW = 32       # new pieces per round
SUMMARY_S = 5      # single-engine IC3 run that feeds the lemma summary
# class A operators; operator 8 of #24 ("k symbolic memory slots") is added here, in validate_op and in op_commands
OPS = {"abstract_value": "-value", "abstract_state": "-state", "abstract_init": "-init"}
EXPR_OK = re.compile(r"[A-Za-z0-9_\s()!~&|^=<>+\-?:\[\]{}',]*")

SYSTEM = """You are an expert in hardware formal verification. You run a property-directed simplification flow on a \
Yosys-flattened design, step by step. Tools check every step: you only (1) split the property into cases and \
(2) choose abstraction operators. You never rewrite the RTL.

## Design (SystemVerilog, top module main)
{rtl}

## Property
{property}
The model is the flattened netlist; there is one assumption: rst is high in the first cycle. The assertion is also \
available as two 1-bit signals: prop_en (the assertion is enforced while it is high) and prop_a (the asserted value).

## Signals
Signals are named by the identifiers listed in each request (the flattened Yosys wire name with every non-alphanumeric \
character replaced by '_', for example sr.tail is sr_tail and sr.mem[3] is sr_mem_3). Use only these identifiers.

## Split
A split is a list of cases, each a Verilog boolean expression over signal identifiers (evaluated in every cycle, on the \
current values of states, inputs and wires). Piece i checks: case_i -> (~prop_en | prop_a) in every cycle. The split is accepted \
only if a SAT check shows that the OR of the cases is true for ALL values of the signals (it covers every situation, \
reachable or not). When a piece is split again, its new cases are intersected with the piece's own case and must cover it.
Split on the source of hardness, not on output conditions: a proof over all indices or all slots stays whole under a split on \
outputs (full, empty, flags), but fixing the index register or pointer it quantifies over instantiates it. Two ways to \
give a split:
- {{"cases":[{{"id":"c0","condition":"<verilog expression>"}}, ...]}}: explicit cases (at most 16 per piece).
- {{"index":ID,"bits":n,"auto":true|false}}: the tool splits register ID on its n highest bits not yet fixed in this piece \
(2^n cases, top bit first). With "auto":true, children that time out are split on the next bit by the tool, without \
asking you again. Use this for an index or pointer register.
Pieces already proved are never touched again.

## Abstraction operators (class A: every one only adds behaviours, so UNSAT on the abstract model is a real proof)
- {{"op":"abstract_value","target":ID,"enable":ID|null,"enablen":ID|null,"slice":"hi:lo"|"i"|null}}: replace the driver of wire ID by a free value (same as cutpoint). enable/enablen: free only while the 1-bit signal is high/low.
- {{"op":"abstract_state","target":ID,"enable":...,"enablen":...,"slice":...,"initstates":N|null}}: register ID loads a free value every clock edge (while enable holds / in the first N cycles). {mem_havoc}
- {{"op":"abstract_init","target":ID,"slice":...}}: register ID gets a free initial value.
- {{"op":"drop_assume"}}: remove the assumption (rst is high in the first cycle).
Not available (reject if you use them): any other operator, rewriting expressions, new assumptions or lemmas, cutpoint -blackbox (the design is flat), UF pairing. {unavailable}

## Verdicts
rIC3 (portfolio of IC3/BMC/k-induction) returns UNSAT (piece proved), SAT (counterexample; replayed on the concrete \
model: real if it reproduces, spurious otherwise) or TIMEOUT. The cap per piece is short (3 s at first, longer in later \
rounds), so a timeout means "not easy yet", not "impossible". Prefer fewer free values: when refining, prefer enable or \
slice over restoring a whole signal.

## Answer format
Answer with one JSON object and nothing else (no markdown fence). The shape is given in each request.
"""


def now():
    return time.time()


def load_cfg(workdir):
    """Per-bench settings: rtl (prompt), sv (read by Yosys), property, mem_havoc, unavailable; mem_re, alias_re optional."""
    with open(os.path.join(workdir, "bench", "case.json")) as f:
        return json.load(f)


class Study:
    def __init__(self, workdir):
        self.dir = os.path.abspath(workdir)
        self.state_path = os.path.join(self.dir, "state.json")
        with open(self.state_path) as f:
            self.s = json.load(f)
        self.cfg = load_cfg(self.dir)
        os.chdir(self.dir)

    def save(self):
        with open(self.state_path, "w") as f:
            json.dump(self.s, f, indent=1)

    def event(self, kind, **kw):
        with open(os.path.join(self.dir, "tool_events.jsonl"), "a") as f:
            f.write(json.dumps(dict(kind=kind, round=self.s["round"], time=now(), **kw)) + "\n")

    # ---- LLM -------------------------------------------------------------------------------------------------
    def llm(self, step, user, history=None, note=None):
        s = self.s
        if s["calls"] >= MAX_CALLS:
            raise SystemExit("LLM call limit of {:d} reached".format(MAX_CALLS))
        c = self.cfg
        system = SYSTEM.format(rtl=open(os.path.join(self.dir, c["rtl"])).read(), property=c["property"],
                               mem_havoc=c["mem_havoc"], unavailable=c["unavailable"])
        messages = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": user}]
        os.chdir(self.dir)
        s["calls"] += 1
        t0 = now()
        response, latency = deepseek_chat.call_deepseek_messages(messages, s["calls"])
        usage = response.get("usage") or {}
        out = deepseek_chat.chat_text(response)
        cost = usage_cost(usage)
        cum = s["cum"]
        cum["input_tokens"] += usage.get("prompt_tokens", 0)
        cum["output_tokens"] += usage.get("completion_tokens", 0)
        cum["cache_hit"] += usage.get("prompt_cache_hit_tokens", 0)
        cum["cache_miss"] += usage.get("prompt_cache_miss_tokens", 0)
        cum["cost_usd"] += cost
        cum["latency_s"] += latency
        record = dict(call=s["calls"], step=step, round=s["round"], prompt=messages, raw_response=out, verdict=None,
                      wall_s=now() - t0, model=response.get("model"), input_tokens=usage.get("prompt_tokens"),
                      output_tokens=usage.get("completion_tokens"),
                      prompt_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
                      prompt_cache_miss_tokens=usage.get("prompt_cache_miss_tokens"), latency_s=latency,
                      cost_usd=cost, cumulative=dict(cum), usage=usage, timestamp=t0, note=note)
        self.save()
        return out, record

    def finish_call(self, record, verdict, failure=None, extra=None):
        record["verdict"] = verdict
        record["failure"] = failure
        record["extra_input"] = extra
        with open(os.path.join(self.dir, "llm_calls.jsonl"), "a") as f:
            f.write(json.dumps(record) + "\n")

    def ask(self, step, user, validate, retries=2):
        """Call the model; on an invalid answer send the tool's error back (each retry is one more call)."""
        history = []
        for attempt in range(retries + 1):
            out, rec = self.llm(step, user, history, note="attempt {:d}".format(attempt + 1))
            try:
                data = json.loads(out)
                result, verdict, extra = validate(data)
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                verdict = "rejected: " + str(e)
                result = extra = None
            self.finish_call(rec, verdict, failure=None if result is not None else "pending-classification", extra=extra)
            if result is not None:
                return result, rec
            history = history + [{"role": "user", "content": user}, {"role": "assistant", "content": out}]
            user = "The tool rejected your answer: {:s}\nAnswer again with the corrected JSON object only.".format(
                verdict[len("rejected: "):])
        raise SystemExit("no valid answer to {:s} after {:d} attempts".format(step, retries + 1))

    # ---- Yosys -----------------------------------------------------------------------------------------------
    def yosys(self, script, log):
        path = os.path.join(self.dir, log)
        r = subprocess.run(["yosys", "-q", "-l", path, "-p", script], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def signals(self):
        return self.s["signals"]

    def ident_map(self):
        return {x["id"]: x for x in self.signals()}

    def check_expr(self, expr):
        if not isinstance(expr, str) or not expr.strip() or not EXPR_OK.fullmatch(expr):
            raise ValueError("expression has characters outside Verilog boolean/arith operators: {!r}".format(expr))
        known = self.ident_map()
        for ident in re.findall(r"(?<![\d'])\b[A-Za-z_]\w*", expr):
            if ident not in known:
                raise ValueError("unknown signal identifier {:s}".format(ident))
        return expr.strip()

    def piece_module(self, expr_by_name, outputs, name="__piece"):
        known = self.ident_map()
        used = sorted({i for e in expr_by_name.values() for i in re.findall(r"(?<![\d'])\b[A-Za-z_]\w*", e)} |
                      {"prop_a", "prop_en"})
        ports = ["input [{:d}:0] {:s}".format(known[i]["width"] - 1, i) for i in used] + \
                ["output {:s}".format(o) for o in outputs]
        body = ["module {:s}({:s});".format(name, ", ".join(ports))]
        for k, e in expr_by_name.items():
            body.append("wire {:s} = {:s};".format(k, e))
        return body, used

    def coverage(self, scope, cases):
        """SAT check that scope -> OR(cases) holds for all signal values; return (ok, detail)."""
        exprs = {"s": scope} if scope else {"s": "1'b1"}
        exprs.update({"c{:d}".format(i): c for i, c in enumerate(cases)})
        body, used = self.piece_module(exprs, ["covered"], "__cover")
        body.append("assign covered = ~s | ({:s});".format(" | ".join("c{:d}".format(i) for i in range(len(cases)))))
        body.append("endmodule")
        path = os.path.join(self.dir, "coverage.v")
        open(path, "w").write("\n".join(body))
        rc, out = self.yosys("read_verilog -sv coverage.v; prep -top __cover; sat -show-inputs -prove covered 1 -verify",
                             "coverage.log")
        return rc == 0, out

    def empty(self, expr):
        """SAT check: expr is false for all signal values."""
        body, used = self.piece_module({"e": expr}, ["none"], "__empty")
        body += ["assign none = ~e;", "endmodule"]
        open(os.path.join(self.dir, "empty.v"), "w").write("\n".join(body))
        rc, _ = self.yosys("read_verilog -sv empty.v; prep -top __empty; sat -prove none 1 -verify", "empty.log")
        return rc == 0

    # ---- models ----------------------------------------------------------------------------------------------
    def build(self, tag, cond, ops, reach=False):
        """Build <tag>.btor2: the concrete flow of build.ys with piece property and class-A ops applied."""
        d = self.dir
        flat = "flat_{:s}.il".format(tag)
        rc, out = self.yosys(
            "read_verilog -sv -formal {:s}; prep -top main; flatten; hierarchy -check; "
            "delete t:$print; chformal -lower; memory -nomap; memory_map; opt_clean; write_rtlil {:s}".format(
                self.cfg["sv"], flat), "build_flat_{:s}.log".format(tag))
        os.chdir(d)
        if rc:
            raise RuntimeError("yosys flat build failed: " + out[-500:])
        il = open(flat).read()
        top = il.index("module \\main")
        end = il.index("\nend\n", top) + 1
        m = re.search(r"  cell \$assert [^\n]*\n(?:(?!  end\n).*\n)*?  end\n", il[top:end])
        a = re.search(r"connect \\A (.*)", m.group(0)).group(1)
        en = re.search(r"connect \\EN (.*)", m.group(0)).group(1)
        assert len(re.findall(r"  cell \$assert ", il[top:end])) == 1, "expected exactly one assertion"
        main = il[top:end]
        if cond:
            main = main.replace(m.group(0), "")
        patch = "  wire \\__one\n  connect \\__one 1'1\n  wire \\prop_a\n  connect \\prop_a {:s}\n  wire \\prop_en\n  connect \\prop_en {:s}\n".format(a, en)
        script = []
        if cond:
            script.append("read_verilog -sv {:s}.v".format(tag))
            body, used = self.piece_module({"c": cond}, ["ok"])
            body.append("assign ok = ~(c & prop_en);" if reach else "assign ok = ~c | ~prop_en | prop_a;")
            body.append("endmodule")
            open("{:s}.v".format(tag), "w").write("\n".join(body))
            ids = self.ident_map()
            conns = "".join("    connect \\{:s} \\{:s}\n".format(i, ids[i]["name"] if i in ids else i) for i in used)
            patch += ("  wire \\__ok\n  cell \\__piece \\__piece_i\n{:s}    connect \\ok \\__ok\n  end\n"
                      "  cell $assert \\__piece_assert\n    connect \\A \\__ok\n    connect \\EN 1'1\n  end\n").format(conns)
        open("{:s}.il".format(tag), "w").write(il[:top] + main + patch + il[end:])
        script += ["read_rtlil {:s}.il".format(tag)]
        if cond:
            script += ["hierarchy -top main", "flatten"]
        script += self.op_commands(ops)
        script += ["opt_clean", "async2sync", "dffunmap", "setundef -undriven -anyseq", "setundef -anyseq",
                   "opt_clean", "check -assert", "write_btor -s {:s}.btor2".format(tag)]
        rc, out = self.yosys("; ".join(script), "{:s}.log".format(tag))
        if rc:
            raise RuntimeError("yosys build of {:s} failed: {:s}".format(tag, out[-500:]))
        path = "{:s}.btor2".format(tag)
        text = open(os.path.join(self.dir, path)).read()
        width = dict(re.findall(r"^(\d+) sort bitvec (\d+)$", text, flags=re.M))
        text, n_uext = re.subn(r"^(\d+) uext (\d+) -1 \d+$",
                      lambda m: "{:s} const {:s} {:s}".format(m.group(1), m.group(2), "0" * int(width[m.group(2)])),
                      text, flags=re.M)
        if n_uext:
            self.event("uext_rewrite", tag=tag, count=n_uext)
        open(os.path.join(self.dir, path), "w").write(text)
        return path

    def op_commands(self, ops):
        ids = self.ident_map()
        cmds = []
        for op in ops:
            if op["op"] == "drop_assume":
                cmds.append("chformal -assume -remove")
                continue
            flags = [OPS[op["op"]]]
            if op["op"] != "abstract_init" and not (op.get("enable") or op.get("enablen")):
                flags.append("-enable __one")  # unconditional abstract -state/-value leaves conflicting drivers in Yosys 0.69
            if op.get("enable"):
                flags.append("-enable " + ids[op["enable"]]["name"])
            if op.get("enablen"):
                flags.append("-enablen " + ids[op["enablen"]]["name"])
            if op.get("slice"):
                flags.append("-slice " + op["slice"])
            if op.get("initstates"):
                flags.append("-initstates {:d}".format(op["initstates"]))
            name = ids[op["target"]]["name"].replace("[", "\\[").replace("]", "\\]")
            cmds.append("abstract {:s} w:{:s}".format(" ".join(flags), name))
        return cmds

    def validate_op(self, op):
        ids = self.ident_map()
        if not isinstance(op, dict) or op.get("op") not in list(OPS) + ["drop_assume"]:
            raise ValueError("operator outside class A or not available here: {!r}".format(op.get("op") if isinstance(op, dict) else op))
        if op["op"] == "drop_assume":
            return {"op": "drop_assume"}
        t = op.get("target")
        if t not in ids:
            raise ValueError("target {!r} is not a signal identifier".format(t))
        if op["op"] == "abstract_state" and not ids[t]["state"]:
            raise ValueError("{:s} is not a register; use abstract_value".format(t))
        if op["op"] == "abstract_init" and not ids[t]["state"]:
            raise ValueError("{:s} is not a register".format(t))
        out = {"op": op["op"], "target": t}
        for k in ("enable", "enablen"):
            if op.get(k):
                if op[k] not in ids or ids[op[k]]["width"] != 1:
                    raise ValueError("{:s} must be a 1-bit signal identifier".format(k))
                out[k] = op[k]
        if out.get("enable") and out.get("enablen"):
            raise ValueError("enable and enablen cannot both be set on one operator (yosys abstract supports one enable condition)")
        if op.get("slice"):
            m = re.fullmatch(r"(\d+)(:(\d+))?", str(op["slice"]))
            if not m or int(m.group(1)) >= ids[t]["width"] or (m.group(3) and int(m.group(3)) > int(m.group(1))):
                raise ValueError("bad slice {!r} for width {:d}".format(op["slice"], ids[t]["width"]))
            out["slice"] = str(op["slice"])
        if op.get("initstates"):
            if op["op"] != "abstract_state" or not isinstance(op["initstates"], int) or op["initstates"] < 1:
                raise ValueError("initstates is only for abstract_state, a positive integer")
            out["initstates"] = op["initstates"]
        # hook: operator 8 of #24 ("k symbolic memory slots") is validated here once implemented
        if op["op"] == "abstract_init" and (out.get("enable") or out.get("enablen")):
            raise ValueError("abstract_init does not support enable")
        return out

    # ---- rIC3 ------------------------------------------------------------------------------------------------
    def ric3(self, model, timeout, tag, engine=("portfolio",), env=None):
        log = os.path.join(self.dir, "logs", tag + ".log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        t0 = now()
        with open(log, "w") as f:
            p = subprocess.Popen([RIC3, "check", "--ui", "false", "--cex", os.path.join(self.dir, model), *engine],
                                 stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
                                 env={**os.environ, **(env or {})})
            try:
                p.wait(timeout=timeout)
                to = False
            except subprocess.TimeoutExpired:
                to = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
        lines = [x.strip() for x in open(log, errors="replace")]
        v = "TIMEOUT" if to else "UNSAT" if "UNSAT" in lines else "SAT" if "SAT" in lines else "UNKNOWN" if "UNKNOWN" in lines else "ERROR"
        return v, now() - t0, log


def sanitize(name):
    return re.sub(r"\W+", "_", name).strip("_")


def init(args):
    os.makedirs(args.workdir, exist_ok=True)
    wd = os.path.abspath(args.workdir)
    st = Study.__new__(Study)
    st.dir = wd
    st.state_path = os.path.join(wd, "state.json")
    cfg = load_cfg(wd)
    r = subprocess.run(["yosys", "-q", "-p",
                        "read_verilog -sv -formal " + cfg["sv"] + "; prep -top main; flatten; "
                        "hierarchy -check; delete t:$print; chformal -lower; memory -nomap; memory_map; opt_clean; "
                        "write_rtlil flat.il"], cwd=wd, capture_output=True, text=True)
    rc, out = r.returncode, r.stdout + r.stderr
    if rc:
        raise SystemExit(out)
    il = open(os.path.join(wd, "flat.il")).read()
    main = il[il.index("module \\main"):]
    main = main[:main.index("\nend\n")]
    ffq = set()
    for cell in re.finditer(r"cell \$(?:a|s)?dff\w* [^\n]*\n(.*?)\n  end", main, re.S):
        m = re.search(r"connect \\Q (\\\S+|\S+)", cell.group(1))
        if m:
            ffq.add(m.group(1).lstrip("\\"))
    ports = {}
    for m in re.finditer(r"wire (?:(?:width (\d+)) )?(?:(?:upto|offset \d+|signed) )*?(input|output|)\s*(?:\d+ )?(\\\S+)", main):
        pass
    sigs = []
    for line in main.splitlines():
        m = re.match(r"\s*wire (.*?)(\\\S+)\s*$", line)
        if not m or m.group(2).startswith("\\$"):
            continue
        attrs, name = m.group(1), m.group(2)[1:]
        w = re.search(r"width (\d+)", attrs)
        sigs.append({"name": name, "id": sanitize(name), "width": int(w.group(1)) if w else 1,
                     "input": "input" in attrs.split(), "state": name in ffq})
    alias = re.compile(cfg["alias_re"] if cfg.get("alias_re") else r"(?!)")
    sigs = [x for x in sigs if x["name"] != "clk" and "$" not in x["name"] and ":" not in x["name"] and "\\" not in x["name"]
            and not alias.fullmatch(x["name"])]
    sigs += [{"name": n, "id": n, "width": 1, "input": False, "state": False} for n in ("prop_a", "prop_en")]
    ids = [x["id"] for x in sigs]
    assert len(ids) == len(set(ids)), "identifier collision: {}".format(sorted({i for i in ids if ids.count(i) > 1}))
    state = {"round": 1, "calls": 0, "signals": sigs, "pieces": {},
             "cum": {"input_tokens": 0, "output_tokens": 0, "cache_hit": 0, "cache_miss": 0, "cost_usd": 0.0,
                     "latency_s": 0.0}}
    json.dump(state, open(st.state_path, "w"), indent=1)
    print(len(sigs), "signals;", sum(x["state"] for x in sigs), "registers")


def signal_table(st):
    mem = re.compile(st.cfg["mem_re"] if st.cfg.get("mem_re") else r"(?!)")
    rows = ["{:s}  width {:d}  {:s}".format(x["id"], x["width"], "input" if x["input"] else "register" if x["state"] else "wire")
            for x in st.signals() if x["state"] is False or not mem.fullmatch(x["id"])]
    return "\n".join(rows) + ("\n" + st.cfg["mem_note"] if st.cfg.get("mem_note") else "")


def sig_list(st):
    return "Signals:\n" + signal_table(st)


def new_piece(st, cond, parent, ops, fixed, direction, rnd):
    return {"cond": cond, "ops": list(ops), "status": "open", "round": rnd, "parent": parent, "fixed": fixed,
            "direction": direction}


def expand(st, spec, parent):
    """Turn a split spec into [(case, fixed, direction)] for the piece `parent` (None = whole property) and SAT-check
    that the cases cover the parent's case."""
    ids = st.ident_map()
    scope = st.s["pieces"][parent]["cond"] if parent else None
    fixed0 = dict(st.s["pieces"][parent]["fixed"]) if parent else {}
    if not isinstance(spec, dict):
        raise ValueError("split must be a JSON object")
    if "index" in spec:
        t = spec["index"]
        if t not in ids:
            raise ValueError("index {!r} is not a signal identifier".format(t))
        low = fixed0.get(t, ids[t]["width"])
        n = min(int(spec.get("bits", 1)), low)
        if n < 1:
            raise ValueError("every bit of {:s} is already fixed in this piece".format(t))
        cases = []
        for v in range(2 ** n):
            hi, lo = low - 1, low - n
            cases.append("{:s}[{:d}:{:d}] == {:d}'d{:d}".format(t, hi, lo, n, v))
        fixed = {**fixed0, t: low - n}
        direction = {"index": t, "auto": bool(spec.get("auto"))}
    else:
        raw = spec.get("cases")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
            raise ValueError("cases must be a list of 1 to 16 entries")
        cases = [st.check_expr(c["condition"]) for c in raw]
        if len({c["id"] for c in raw}) != len(raw):
            raise ValueError("duplicate case ids")
        fixed, direction = fixed0, None
    ok, out = st.coverage(scope, cases)
    st.event("coverage", scope=scope, cases=cases, ok=ok, detail=out[-800:])
    if not ok:
        raise ValueError("SAT coverage check failed: the cases do not cover the piece's case. Counterexample "
                         "(signal values where no case holds):\n" + out[-800:])
    if scope and "index" in spec:  # a bit that the piece's case already fixes yields contradictory cases: drop them
        keep = [c for c in cases if not st.empty("({:s}) & ({:s})".format(scope, c))]
        st.event("pruned_empty", scope=scope, dropped=[c for c in cases if c not in keep])
        cases = keep
    return [("({:s}) & ({:s})".format(scope, c) if scope else c, fixed, direction) for c in cases]


def add_children(st, parent, kids, ops, rnd, counter):
    out = []
    for cond, fixed, direction in kids:
        pid = "r{:d}_c{:d}".format(rnd, counter[0])
        counter[0] += 1
        st.s["pieces"][pid] = new_piece(st, cond, parent, ops, fixed, direction, rnd)
        out.append(pid)
    if parent:
        st.s["pieces"][parent]["status"] = "split"
        st.s["pieces"][parent]["children"] = out
    return out


def plan_first_split(st):
    user = ("Step: PLAN SPLIT (round 1). Propose the first split of the property: where does the hardness come from "
            "(which index, pointer or slot does the proof quantify over)? Each piece is first checked with a {:d} s "
            "cap, 8 pieces at a time; pieces that time out come back to you with timings.\n\n{:s}\n\n"
            'Answer: {{"split":<explicit cases or index direction>,"reason":"..."}}').format(CAPS[0], sig_list(st))

    def validate(data):
        kids = expand(st, data["split"], None)
        return kids, "accepted: coverage SAT-checked, {:d} cases".format(len(kids)), \
            {"split": data["split"], "reason": data.get("reason")}

    kids, rec = st.ask("plan_split", user, validate)
    ids = add_children(st, None, kids, [], 1, [0])
    print(json.dumps({i: st.s["pieces"][i]["cond"] for i in ids}, indent=1))


def lemma_summary(st, p):
    """Single-engine IC3 run on the piece's model for SUMMARY_S seconds: rIC3 does not print lemma contents on a run that
    does not finish (--cert only on UNSAT, and its latches are anonymous), so this reports depth, lemmas per frame and
    generalised-lemma length from the trace log."""
    v = st.s["pieces"][p]
    tag = v["tag"] + "_ic3"
    verdict, secs, log = st.ric3(v["tag"] + ".btor2", SUMMARY_S, tag, engine=("ic3",), env={"RUST_LOG": "trace"})
    text = open(log, errors="replace").read()
    depth = re.findall(r"no counterexample up to depth (\d+)", text)
    frames = re.findall(r"frames \[\d+\]: ([\d ]+)", text)
    mic = [int(x) for x in re.findall(r"mic from \d+ to (\d+) len", text)][-200:]
    latches = re.findall(r"preprocessed ts has \d+ vars, \d+ inputs, (\d+) latches", text)
    s = "single-engine IC3, {:d} s: ".format(SUMMARY_S)
    if verdict == "UNSAT":
        return verdict, "IC3 alone proved it in {:.1f} s".format(secs)
    s += "reached depth {:s}".format(depth[-1] if depth else "0")
    if frames:
        s += "; lemmas per frame at the end [{:s}]".format(frames[-1].strip().replace(" ", ", "))
    if mic:
        s += "; recent lemmas have {:.1f} literals on average out of {:s} state bits (rIC3 does not name them)".format(
            sum(mic) / len(mic), latches[-1] if latches else "?")
    return verdict, s


def cmd_decide(st, timeouts, rows, counter, cap):
    """One LLM call for all pieces that timed out this round: resplit / abstract / both, each with a reason."""
    rnd = st.s["round"]
    with concurrent.futures.ThreadPoolExecutor(PARALLEL) as ex:
        t0 = now()
        sums = dict(zip(timeouts, ex.map(lambda p: lemma_summary(st, p), timeouts)))
    st.event("summary_pass", pieces=timeouts, timeout=SUMMARY_S, wall_s=now() - t0)
    for p, (verdict, text) in list(sums.items()):
        if verdict == "UNSAT":
            st.s["pieces"][p]["status"] = "proved"
            st.s["pieces"][p]["last"] = {"verdict": "UNSAT", "seconds": SUMMARY_S, "timeout": SUMMARY_S, "by": "ic3 summary run"}
            del sums[p]
        st.event("summary", piece=p, verdict=verdict, text=text)
    todo = list(sums)
    if not todo:
        return
    user = ["Step: DECIDE (round {:d}). rIC3 portfolio, cap {:d} s per piece. Results of this round:".format(rnd, cap)]
    user += ["- {:s}: {:s} {:.1f} s".format(*r) for r in rows]
    user.append("Pieces that timed out (decide for each: \"resplit\", \"abstract\" or \"both\", with a reason):")
    for p in todo:
        v = st.s["pieces"][p]
        user.append("- {:s}: case {:s}\n  operators now: {:s}\n  already fixed bits: {:s}\n  {:s}".format(
            p, v["cond"], json.dumps(v["ops"]), json.dumps(v["fixed"]), sums[p][1]))
    user.append("Proved pieces are never touched again. Budget: at most {:d} new pieces this round, {:d} rounds in "
                "total ({:d} left); the cap grows to {:d} s in later rounds.".format(
                    MAX_NEW, MAX_ROUNDS, MAX_ROUNDS - rnd, CAPS[min(rnd // 2, len(CAPS) - 1)]))
    user.append(sig_list(st))
    user.append('Answer: {"pieces":{"<piece id>":{"action":"resplit|abstract|both","reason":"...",'
                '"split":<explicit cases or index direction, for resplit/both>,"ops":[<operator>, ...] (for abstract/both)}, ...}}')

    def validate(data):
        plan, total = {}, 0
        if set(data["pieces"]) != set(todo):
            raise ValueError("pieces must be exactly {}".format(todo))
        for p in todo:
            d = data["pieces"][p]
            if d["action"] not in ("resplit", "abstract", "both") or not str(d.get("reason", "")).strip():
                raise ValueError("{:s}: action must be resplit, abstract or both, and a reason is required".format(p))
            ops = st.s["pieces"][p]["ops"]
            if d["action"] != "resplit":
                ops = [st.validate_op(op) for op in d["ops"]]
                if d["action"] == "abstract" and ops == st.s["pieces"][p]["ops"]:
                    raise ValueError("{:s}: the operator list is unchanged".format(p))
            kids = expand(st, d["split"], p) if d["action"] != "abstract" else []
            total += len(kids)
            plan[p] = dict(action=d["action"], reason=d["reason"], ops=ops, kids=kids, split=d.get("split"))
        if total + counter[0] > MAX_NEW:
            raise ValueError("{:d} new pieces ({:d} already made by the tool's auto splits), at most {:d} per round".format(
                total, counter[0], MAX_NEW))
        return plan, "accepted: " + ", ".join("{:s} {:s}".format(p, x["action"]) for p, x in plan.items()), \
            {p: {"action": x["action"], "reason": x["reason"], "split": x["split"], "ops": x["ops"]} for p, x in plan.items()}

    plan, rec = st.ask("decide", "\n".join(user), validate)
    for p, x in plan.items():
        if x["action"] == "abstract":
            st.s["pieces"][p]["ops"], st.s["pieces"][p]["status"] = x["ops"], "open"
        else:
            add_children(st, p, x["kids"], x["ops"], rnd + 1, counter)
        print(p, x["action"], "-", x["reason"])


def run_check(st, p, timeout):
    v = st.s["pieces"][p]
    v["attempt"] = v.get("attempt", -1) + 1
    tag = "{:s}_k{:d}".format(p, v["attempt"])
    try:
        model = st.build(tag, v["cond"], v["ops"])
    except RuntimeError as e:
        st.event("build_error", piece=p, error=str(e)[:500])
        return p, "BUILD_ERROR", 0.0, str(e), tag
    verdict, secs, log = st.ric3(model, timeout, tag)
    return p, verdict, secs, log, tag


def check_pass(st, todo, cap):
    t0 = now()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(PARALLEL) as ex:
        futs = [ex.submit(run_check, st, p, cap) for p in todo]
        for f in concurrent.futures.as_completed(futs):
            p, verdict, secs, log, tag = f.result()
            v = st.s["pieces"][p]
            v["status"] = {"UNSAT": "proved", "SAT": "sat", "TIMEOUT": "timeout"}.get(verdict, "error")
            v["tag"], v["last"] = tag, {"verdict": verdict, "seconds": round(secs, 1), "timeout": cap}
            st.event("check", piece=p, tag=tag, verdict=verdict, seconds=secs, timeout=cap, ops=v["ops"], cond=v["cond"])
            rows.append((p, verdict, secs))
            print(p, verdict, round(secs, 1), flush=True)
    st.event("check_pass", pieces=todo, timeout=cap, wall_s=now() - t0)
    st.save()
    return sorted(rows)


def cmd_run(st, args):
    global CAPS
    CAPS = tuple(int(x) for x in args.caps.split(","))
    caps = CAPS
    s = st.s
    for rnd in range(s["round"], MAX_ROUNDS + 1):
        s["round"] = rnd
        if rnd == 1 and not s["pieces"]:
            plan_first_split(st)
            st.save()
        todo = [p for p, v in s["pieces"].items() if v["status"] == "open"]
        if not todo:
            break
        cap = caps[min((rnd - 1) // 2, len(caps) - 1)]
        rows = check_pass(st, todo, cap)
        if any(v["status"] == "sat" for v in s["pieces"].values()):
            cmd_cegar(st, args)
            cmd_refine(st, args)
        timeouts = [p for p in todo if s["pieces"][p]["status"] == "timeout"]
        counter = [0]
        for p in list(timeouts):  # "auto" index directions: the tool takes the next bit, no LLM call
            v = s["pieces"][p]
            d = v["direction"]
            if d and d["auto"] and v["fixed"].get(d["index"], 1) > 0 and counter[0] + 2 <= MAX_NEW // 2:  # the other half of the budget stays for the LLM's own splits
                kids = expand(st, {"index": d["index"], "bits": 1, "auto": True}, p)
                st.event("auto_expand", piece=p, index=d["index"], fixed=v["fixed"])
                add_children(st, p, kids, v["ops"], rnd + 1, counter)
                timeouts.remove(p)
        st.save()
        if rnd < MAX_ROUNDS and timeouts:
            cmd_decide(st, timeouts, rows, counter, cap)
        st.save()
    left = {p: v["status"] for p, v in s["pieces"].items() if v["status"] not in ("proved", "split")}
    print("done after round", s["round"], "unresolved:", left or "none")


def cmd_split_only(st, args):
    """Control: the same leaf pieces with no operators."""
    todo = args.pieces or [p for p, v in st.s["pieces"].items() if v["status"] != "split"]

    def one(p):
        tag = p + "_so"
        try:
            model = st.build(tag, st.s["pieces"][p]["cond"], [])
        except RuntimeError as e:
            return p, "BUILD_ERROR", 0.0
        verdict, secs, _ = st.ric3(model, args.timeout, tag)
        return p, verdict, secs

    t0 = now()
    with concurrent.futures.ThreadPoolExecutor(PARALLEL) as ex:
        for p, verdict, secs in ex.map(one, todo):
            st.s["pieces"][p]["split_only"] = {"verdict": verdict, "seconds": round(secs, 1), "timeout": args.timeout}
            st.event("split_only", piece=p, verdict=verdict, seconds=secs, timeout=args.timeout)
            print(p, verdict, round(secs, 1), flush=True)
    st.event("split_only_pass", pieces=todo, timeout=args.timeout, wall_s=now() - t0)
    st.save()


def cmd_report(st, args):
    """LLM time and rIC3 time, reported separately."""
    ev = [json.loads(x) for x in open(os.path.join(st.dir, "tool_events.jsonl"))]
    calls = [json.loads(x) for x in open(os.path.join(st.dir, "llm_calls.jsonl"))]
    print("LLM: {:d} calls, {:.1f} s latency, {:d} in / {:d} out tokens, {:.4f} USD".format(
        len(calls), sum(c["latency_s"] for c in calls), sum(c["input_tokens"] or 0 for c in calls),
        sum(c["output_tokens"] or 0 for c in calls), sum(c["cost_usd"] for c in calls)))
    for kind in ("check_pass", "summary_pass", "split_only_pass"):
        for e in (e for e in ev if e["kind"] == kind):
            print("rIC3 {:s} round {:d}: {:d} pieces, cap {:d} s, wall {:.1f} s".format(
                kind, e["round"], len(e["pieces"]), e["timeout"], e["wall_s"]))


def witness_file(log, dest):
    lines = open(log, errors="replace").read().splitlines()
    i = next(k for k, line in enumerate(lines) if line.strip().lower() == "sat" and k + 1 < len(lines) and lines[k + 1].startswith("b"))
    open(dest, "w").write("sat\n" + "\n".join(lines[i + 1:]) + "\n")


def replay(st, p):
    """Replay the abstract counterexample on the concrete piece; return (real, depth, table)."""
    v = st.s["pieces"][p]
    tag = v["tag"]
    wit = os.path.join(st.dir, "logs", tag + ".wit")
    witness_file(os.path.join(st.dir, "logs", tag + ".log"), wit)
    conc = st.build(p + "_concrete", v["cond"], [])
    am, cm = btor_witness.Model(os.path.join(st.dir, tag + ".btor2")), btor_witness.Model(os.path.join(st.dir, conc))
    frames = btor_witness.parse_witness(wit)
    aname = {n: am.names[n] for n in am.names}
    cin = {cm.names[n]: i for i, n in enumerate(cm.inputs) if n in cm.names}
    cst = {cm.names[n]: i for i, n in enumerate(cm.states) if n in cm.names}
    ain = {i: aname[n] for i, n in enumerate(am.inputs) if n in aname}
    ast = {i: aname[n] for i, n in enumerate(am.states) if n in aname}
    cf = []
    for k, fr in enumerate(frames):
        cf.append({"input": {cin[ain[i]]: val for i, val in fr["input"].items() if ain.get(i) in cin},
                   "state": {cst[ast[i]]: val for i, val in fr["state"].items() if k == 0 and ast.get(i) in cst}})
    av, cv = btor_witness.simulate(am, frames), btor_witness.simulate(cm, cf)
    bad_c = [any(btor_witness.value_of(c, int(cm.nodes[b][1][2])) == 1 for b in cm.bad) for c in cv]
    names = [n for n in cm.states if n in cm.names and cm.names[n] in set(aname.values())]
    table = []
    for k in range(len(frames)):
        row = {"cycle": k}
        for n in cm.states:
            nm = cm.names.get(n)
            if not nm or nm.endswith("first") or (st.cfg.get("mem_re") and re.fullmatch(st.cfg["mem_re"], sanitize(nm))):
                continue
            an = next((x for x in am.states if aname.get(x) == nm), None)
            row[nm] = (av[k][an] if an else None, cv[k][n])
        for n in cm.inputs:
            if cm.names.get(n) and cm.names[n] != "clk":
                row[cm.names[n]] = cv[k][n]
        table.append(row)
    return any(bad_c), len(frames) - 1, table, bad_c


def cmd_cegar(st, args):
    for p in [p for p, v in st.s["pieces"].items() if v["status"] == "sat"]:
        real, depth, table, bad_c = replay(st, p)
        st.event("replay", piece=p, real=real, depth=depth, concrete_bad=bad_c, table=table)
        v = st.s["pieces"][p]
        if real:
            v["status"] = "real_cex"
            print(p, "REAL counterexample at depth", depth)
            continue
        v["status"] = "spurious"
        v["cex"] = {"depth": depth, "table": table}
        print(p, "spurious at depth", depth)
    st.save()


def cmd_refine(st, args):
    for p in [p for p, v in st.s["pieces"].items() if v["status"] == "spurious"]:
        v = st.s["pieces"][p]
        rows = []
        for r in v["cex"]["table"]:
            rows.append("cycle {:d}: ".format(r["cycle"]) + ", ".join(
                "{:s}={}".format(k, x if not isinstance(x, list) else "abs {}/conc {}".format(*x))
                for k, x in r.items() if k != "cycle"))
        user = ("Step: CEGAR REFINE (round {:d}). Piece {:s} (case: {:s}) has the operators below. rIC3 found a "
                "counterexample on the abstract model; replay on the concrete model does NOT reproduce it (spurious). "
                "Per cycle, registers are shown as (abstract value, concrete value); the property fails in the last "
                "cycle on the abstract model only.\n\nOperators now: {:s}\n\n{:s}\n\nSignals:\n{:s}\n\n"
                'Give a refined full operator list for this piece (restore as little as possible; prefer enable or slice '
                'over restoring a whole signal). Answer: {{"ops":[<operator>, ...],"reason":"..."}}').format(
            st.s["round"], p, v["cond"], json.dumps(v["ops"]), "\n".join(rows), signal_table(st))

        def validate(data, v=v):
            ops = [st.validate_op(op) for op in data["ops"]]
            if ops == v["ops"]:
                raise ValueError("the operator list is unchanged")
            return ops, "accepted refined list", {"ops": ops, "reason": data.get("reason")}

        ops, rec = st.ask("cegar_refine", user, validate)
        v["ops"], v["status"] = ops, "open"
        print(p, json.dumps(ops))
    st.save()


def cmd_vacuity(st, args):
    for p in [p for p, v in st.s["pieces"].items() if v["status"] == "proved" and "vacuity" not in v]:
        v = st.s["pieces"][p]
        # 1. case reachable on the concrete model: BMC for (case & !rst) must be SAT.
        reach = st.build(p + "_reach", v["cond"], [], reach=True)
        rv, rs, _ = st.ric3(reach, 300, p + "_reach", engine=("bmc", "--end", "40"))
        # 2. non-vacuous: with every register free (combinational check) the piece assertion can be violated.
        sat_ok = st.nonvacuous(p, v)
        v["vacuity"] = {"case_reachable_bmc": rv, "assertion_violable_when_registers_free": sat_ok}
        st.event("vacuity", piece=p, **v["vacuity"])
        print(p, v["vacuity"])
    st.save()


def nonvacuous(self, p, v):
    ids = self.ident_map()
    body, used = self.piece_module({"c": v["cond"]}, ["ok"], "__nv")
    body += ["assign ok = ~c | ~prop_en | prop_a;", "endmodule"]
    open(os.path.join(self.dir, p + "_nv.v"), "w").write("\n".join(body))
    rc, _ = self.yosys("read_verilog -sv {:s}_nv.v; prep -top __nv; sat -prove ok 1 -verify".format(p), p + "_nv.log")
    return rc != 0


Study.nonvacuous = nonvacuous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "run", "vacuity", "split-only", "report"])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--pieces", nargs="*")
    ap.add_argument("--timeout", type=int, default=60, help="split-only cap in seconds")
    ap.add_argument("--caps", default=",".join(map(str, CAPS)), help="run: rIC3 cap per piece for rounds 1-2, 3-4, 5+")
    args = ap.parse_args()
    if args.cmd == "init":
        return init(args)
    st = Study(args.workdir)
    st.event("load", cmd=args.cmd, phase="start", load=os.getloadavg())
    try:
        {"run": cmd_run, "split-only": cmd_split_only, "vacuity": cmd_vacuity, "report": cmd_report}[args.cmd](st, args)
    finally:
        st.event("load", cmd=args.cmd, phase="end", load=os.getloadavg())


if __name__ == "__main__":
    main()
