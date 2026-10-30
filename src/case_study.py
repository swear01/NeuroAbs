"""Manual case study: DeepSeek runs the split / abstract / check / CEGAR flow on one design (issue #25).

Each subcommand is one step of the flow; state lives in <workdir>/state.json and every LLM call is one
record of <workdir>/llm_calls.jsonl.  The tools (Yosys, SAT coverage check, rIC3, replay) judge every
answer; the LLM only splits and picks class-A operators.
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
MAX_CALLS, MAX_ROUNDS = 30, 5
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
reachable or not).

## Abstraction operators (class A: every one only adds behaviours, so UNSAT on the abstract model is a real proof)
- {{"op":"abstract_value","target":ID,"enable":ID|null,"enablen":ID|null,"slice":"hi:lo"|"i"|null}}: replace the driver of wire ID by a free value (same as cutpoint). enable/enablen: free only while the 1-bit signal is high/low.
- {{"op":"abstract_state","target":ID,"enable":...,"enablen":...,"slice":...,"initstates":N|null}}: register ID loads a free value every clock edge (while enable holds / in the first N cycles). {mem_havoc}
- {{"op":"abstract_init","target":ID,"slice":...}}: register ID gets a free initial value.
- {{"op":"drop_assume"}}: remove the assumption (rst is high in the first cycle).
Not available (reject if you use them): any other operator, rewriting expressions, new assumptions or lemmas, cutpoint -blackbox (the design is flat), UF pairing. {unavailable}

## Verdicts
rIC3 (portfolio of IC3/BMC/k-induction) returns UNSAT (piece proved), SAT (counterexample; replayed on the concrete \
model: real if it reproduces, spurious otherwise) or TIMEOUT. Prefer fewer free values: when refining, prefer enable or \
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
                result, verdict = validate(data)
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                verdict = "rejected: " + str(e)
                result = None
            self.finish_call(rec, verdict, failure=None if result is not None else "pending-classification")
            if result is not None:
                return result, rec
            history = history + [{"role": "user", "content": user}, {"role": "assistant", "content": out}]
            user = "The tool rejected your answer: {:s}\nAnswer again with the corrected JSON object only.".format(
                verdict[len("rejected: "):])
        raise SystemExit("no valid answer to {:s} after {:d} attempts".format(step, retries + 1))

    # ---- Yosys -----------------------------------------------------------------------------------------------
    def yosys(self, script, log):
        path = os.path.join(self.dir, log)
        r = subprocess.run(["yosys", "-q", "-l", path, "-p", script], capture_output=True, text=True, cwd=self.dir)
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
        if rc and "proof did fail" not in out:
            raise RuntimeError("coverage check could not run:\n" + out[-800:])
        return rc == 0, out

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
        if m is None or len(re.findall(r"  cell \$assert ", il[top:end])) != 1:
            raise RuntimeError("expected exactly one assertion in module main")
        a = re.search(r"connect \\A (.*)", m.group(0)).group(1)
        en = re.search(r"connect \\EN (.*)", m.group(0)).group(1)
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
        if op.get("slice"):
            m = re.fullmatch(r"(\d+)(:(\d+))?", str(op["slice"]))
            if not m or int(m.group(1)) >= ids[t]["width"] or (m.group(3) and int(m.group(3)) > int(m.group(1))):
                raise ValueError("bad slice {!r} for width {:d}".format(op["slice"], ids[t]["width"]))
            out["slice"] = str(op["slice"])
        if op.get("initstates"):
            if op["op"] != "abstract_state" or not isinstance(op["initstates"], int) or op["initstates"] < 1:
                raise ValueError("initstates is only for abstract_state, a positive integer")
            out["initstates"] = op["initstates"]
        if op["op"] == "abstract_init" and (out.get("enable") or out.get("enablen")):
            raise ValueError("abstract_init does not support enable")
        return out

    # ---- rIC3 ------------------------------------------------------------------------------------------------
    def ric3(self, model, timeout, tag, engine=("portfolio",)):
        log = os.path.join(self.dir, "logs", tag + ".log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        t0 = now()
        with open(log, "w") as f:
            p = subprocess.Popen([RIC3, "check", "--ui", "false", "--cex", os.path.join(self.dir, model), *engine],
                                 stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
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


def cmd_split(st, args):
    scope = None
    if args.pieces:
        scope = " | ".join("({:s})".format(st.s["pieces"][p]["cond"]) for p in args.pieces)
    user = ["Step: PLAN SPLIT (round {:d}).".format(st.s["round"])]
    if args.pieces:
        user.append("Re-split only these pieces, which timed out ({:s}); the new cases must cover exactly their union:\n{:s}".format(
            ", ".join(args.pieces), "\n".join("- {:s}: {:s}".format(p, st.s["pieces"][p]["cond"]) for p in args.pieces)))
        if args.context:
            user.append(open(args.context).read())
    else:
        user.append("Propose a split of the property into cases.")
    user.append("Signals:\n" + signal_table(st))
    user.append('Answer: {"cases":[{"id":"c0","condition":"<verilog expression>"}, ...],"reason":"..."}')
    user = "\n\n".join(user)

    def validate(data):
        cases = data["cases"]
        if not isinstance(cases, list) or not 1 <= len(cases) <= 12:
            raise ValueError("cases must be a list of 1 to 12 entries")
        conds = [st.check_expr(c["condition"]) for c in cases]
        ids = [c["id"] for c in cases]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate case ids")
        ok, out = st.coverage(scope, conds)
        st.event("coverage", scope=scope, cases=conds, ok=ok, detail=out[-800:])
        if not ok:
            raise ValueError("SAT coverage check failed: the cases do not cover every situation. Counterexample "
                             "(signal values where no case holds):\n" + out[-800:])
        return list(zip(ids, conds)), "accepted: coverage SAT-checked, {:d} cases".format(len(cases))

    cases, rec = st.ask("plan_split", user, validate)
    if args.pieces:
        for p in args.pieces:
            st.s["pieces"][p]["status"] = "split"
    pre = "r{:d}".format(st.s["round"])
    for cid, cond in cases:
        st.s["pieces"]["{:s}_{:s}".format(pre, cid)] = {"cond": cond, "ops": [], "status": "new", "round": st.s["round"]}
    st.save()
    print(json.dumps(cases, indent=1))


def cmd_abstract(st, args):
    todo = [p for p, v in st.s["pieces"].items() if v["status"] == "new"]
    user = ["Step: PLAN ABSTRACTION (round {:d}). Choose class-A operators for each piece. An empty list means no "
            "abstraction (the concrete piece).".format(st.s["round"]), "Pieces:"]
    user += ["- {:s}: {:s}".format(p, st.s["pieces"][p]["cond"]) for p in todo]
    if args.context:
        user.append(open(args.context).read())
    user.append("Signals:\n" + signal_table(st))
    user.append('Answer: {"pieces":{"<piece id>":[<operator>, ...], ...},"reason":"..."}')
    user = "\n\n".join(user)
    rejected = {}

    def validate(data):
        plan = data["pieces"]
        if set(plan) != set(todo):
            raise ValueError("pieces must be exactly {}".format(todo))
        accepted = {}
        for p in todo:
            accepted[p] = []
            for op in plan[p]:
                try:
                    accepted[p].append(st.validate_op(op))
                except (ValueError, KeyError, TypeError) as e:
                    rejected.setdefault(p, []).append((op, str(e)))
        return accepted, "accepted {:d} ops, rejected {:d}".format(
            sum(map(len, accepted.values())), sum(map(len, rejected.values())))

    plan, rec = st.ask("plan_abstraction", user, validate)
    for p, ops in plan.items():
        st.s["pieces"][p]["ops"] = ops
        st.s["pieces"][p]["status"] = "planned"
    st.event("abstraction", plan=plan, rejected={p: [[o, e] for o, e in v] for p, v in rejected.items()})
    st.save()
    print(json.dumps({"accepted": plan, "rejected": rejected}, indent=1))


def run_check(st, p, timeout):
    v = st.s["pieces"][p]
    tag = "{:s}_k{:d}".format(p, v.get("attempt", 0))
    try:
        model = st.build(tag, v["cond"], v["ops"])
    except RuntimeError as e:
        return p, "BUILD_ERROR", 0.0, str(e), tag
    verdict, secs, log = st.ric3(model, timeout, tag)
    return p, verdict, secs, log, tag


def cmd_check(st, args):
    todo = args.pieces or [p for p, v in st.s["pieces"].items() if v["status"] in ("planned", "timeout", "refined")]
    for p in todo:
        st.s["pieces"][p]["attempt"] = st.s["pieces"][p].get("attempt", -1) + 1
    t0 = now()
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        futs = [ex.submit(run_check, st, p, args.timeout) for p in todo]
        for f in concurrent.futures.as_completed(futs):
            p, verdict, secs, log, tag = f.result()
            v = st.s["pieces"][p]
            v["status"] = {"UNSAT": "proved", "SAT": "sat", "TIMEOUT": "timeout"}.get(verdict, "error")
            v["tag"], v["last"] = tag, {"verdict": verdict, "seconds": round(secs, 1), "timeout": args.timeout}
            st.event("check", piece=p, tag=tag, verdict=verdict, seconds=secs, timeout=args.timeout, ops=v["ops"],
                     cond=v["cond"])
            print(p, verdict, round(secs, 1), flush=True)
            st.save()
    st.event("check_pass", pieces=todo, timeout=args.timeout, wall_s=now() - t0)


def cmd_split_only(st, args):
    """Control: the same leaf pieces with no operators."""
    todo = args.pieces or [p for p, v in st.s["pieces"].items() if v["status"] != "split"]

    def one(p):
        tag = p + "_so"
        try:
            model = st.build(tag, st.s["pieces"][p]["cond"], [])
        except RuntimeError:
            return p, "BUILD_ERROR", 0.0
        verdict, secs, _ = st.ric3(model, args.timeout, tag)
        return p, verdict, secs

    t0 = now()
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
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
    for kind in ("check_pass", "split_only_pass"):
        for e in (e for e in ev if e["kind"] == kind):
            print("rIC3 {:s} round {:d}: {:d} pieces, cap {:d} s, wall {:.1f} s".format(
                kind, e["round"], len(e["pieces"]), e["timeout"], e["wall_s"]))


def witness_file(log, dest):
    lines = open(log, errors="replace").read().splitlines()
    i = next((k for k, line in enumerate(lines) if line.strip().lower() == "sat" and k + 1 < len(lines)
              and lines[k + 1].strip()[:1] in ("b", "#", "@")), None)
    if i is None:
        raise RuntimeError("no SAT witness marker in " + log)
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
            return ops, "accepted refined list"

        ops, rec = st.ask("cegar_refine", user, validate)
        v["ops"], v["status"] = ops, "refined"
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
    body, _ = self.piece_module({"c": v["cond"]}, ["ok"], "__nv")
    body += ["assign ok = ~c | ~prop_en | prop_a;", "endmodule"]
    open(os.path.join(self.dir, p + "_nv.v"), "w").write("\n".join(body))
    rc, out = self.yosys("read_verilog -sv {:s}_nv.v; prep -top __nv; sat -prove ok 1 -verify".format(p), p + "_nv.log")
    if rc and "proof did fail" not in out:
        raise RuntimeError("non-vacuity check could not run:\n" + out[-800:])
    return rc != 0


Study.nonvacuous = nonvacuous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "split", "abstract", "check", "cegar", "refine", "vacuity", "next-round", "split-only", "report"])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--pieces", nargs="*")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--context", help="file with extra input appended to the prompt")
    args = ap.parse_args()
    if args.cmd == "init":
        return init(args)
    st = Study(args.workdir)
    if args.cmd == "next-round":
        if st.s["round"] >= MAX_ROUNDS:
            raise SystemExit("round limit reached")
        st.s["round"] += 1
        st.save()
        return
    {"split": cmd_split, "abstract": cmd_abstract, "check": cmd_check, "cegar": cmd_cegar,
     "refine": cmd_refine, "vacuity": cmd_vacuity, "split-only": cmd_split_only, "report": cmd_report}[args.cmd](st, args)


if __name__ == "__main__":
    main()
