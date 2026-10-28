"""prepare.py <run dir> <out dir>: the problems of the held-out rule comparison, fixed before any LLM call.

For ADDI (training) and every test instruction it writes to <out dir>/<case>/:

- wrapper.v.sha256: the wrapper with named operands (name_operands); the wrapper itself goes to <run dir>/<case>/.
- units.json: choice_abstraction.discover_units on the concrete model B0 of flute-piccolo-20261025.
- candidates.json: every operator pair that the menu offers (uf_candidates).
- s_pairs.json: the pairs of the pre-registered matcher (semantic_candidates/scripts/rules.py match_pairs), used by
  the S and auto arms.
- subs-sample.json: the sampled sub-properties (sample) of the split (split).

A case whose wrapper, units or split cannot be produced is listed in <out dir>/failed.json and excluded.
"""
import hashlib
import json
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "results", "semantic_candidates", "scripts"))
import choice_abstraction as ca  # noqa: E402
import fine_choice as fc  # noqa: E402
import rules  # noqa: E402

B0 = "/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025/piccolo/{:s}/b0_ila.btor2"
TRAIN = "ADDI"
TESTS = ["ADD_Flatten", "SUB", "OR", "XOR", "ANDI", "SLTI", "LUI", "AUIPC", "JAL", "BEQ", "BNE_new", "SB", "SH"]
SEED = 20261027
TRAIN_SIZE = 16
TEST_SIZE = 20
GPR_STATE = re.compile(r"x[1-9]\d*")
RTL_OPERAND = re.compile(r"(assign\s+(\w+)\s*=\s*)(rs[12]_val\w*)(\s*([-+^&|])\s*)(\{.*?\})(\s*;)", re.S)


def name_operands(text):
    """Name a concatenation operand of an RTL operator node whose other operand is rs1_val* or rs2_val*.

    assign n = rs1_val_x + {...}; becomes wire [w-1:0] n__rhs = {...}; assign n = rs1_val_x + n__rhs;  The model is
    unchanged; the node becomes a pair candidate that fine_choice.operator_args can parse.
    """
    module = fc.instance_module(text, "RTL")
    start, end = fc.module_span(text, module)
    body = text[start:end]

    def width(node):
        for m in re.finditer(r"wire\s*\[\s*(\d+)\s*:\s*0\s*\]([^;]*);", body):
            if node in re.split(r"[\s,]+", m.group(2).strip()):
                return int(m.group(1)) + 1
        raise ValueError("no declaration of " + node)

    def rewrite(m):
        node = m.group(2)
        if m.group(6).count("{") != m.group(6).count("}"):
            return m.group(0)
        name = node + "__rhs"
        return "wire [{:d}:0] {:s} = {:s} ;\n  {:s}{:s}{:s}{:s}{:s}".format(
            width(node) - 1, name, m.group(6), m.group(1), m.group(3), m.group(4), name, m.group(7))

    return text[:start] + RTL_OPERAND.sub(rewrite, body) + text[end:]


def uf_candidates(text):
    """Every pair (ILA binary operator node with an operand that reads the GPR file, RTL node of the same module
    operator with an operand named rs1_val* or rs2_val*), in source order: the pairs of rules.match_pairs before
    its tie-break."""
    ila, rtl = fc.instance_module(text, "ILA"), fc.instance_module(text, "RTL")
    start, end = fc.module_span(text, ila)
    assigns = fc.read_assigns(text[start:end])
    reads_gpr = {n for n, body in assigns.items() if re.search(r"\(\s*x31\s*\)", body)}
    rtl_nodes = rules.binary_nodes(text, rtl)
    out = []
    for name, a, op, b in rules.binary_nodes(text, ila):
        if a not in reads_gpr and b not in reads_gpr:
            continue
        for n, x, o, y in rtl_nodes:
            if o == op and any(re.match(r"rs[12]_val", v) for v in (x, y)):
                out.append({"ila": name, "rtl": n})
    return out


def split(text):
    """fine_choice.ila_split when the property compares GPRs x1..x31.  Otherwise (branches and stores) every compared
    state gets, for every value of the operand fields, the case with those values; for each state these cases cover
    every instruction."""
    states = sorted(fc.property_conjuncts(text))
    fields = fc.operand_fields(text)
    if any(GPR_STATE.fullmatch(s) for s in states):
        return fc.ila_split(states, fields)
    if fields != ["rs1", "rs2"]:
        raise ValueError("no field split for operand fields {}".format(fields))
    return [{"name": "{:s}.rs1={:d}.rs2={:d}".format(s, a, b), "states": [s], "case": "rs1=={:d}&&rs2=={:d}".format(a, b)}
            for s in states for a in range(fc.NUM_GPRS) for b in range(fc.NUM_GPRS)]


def terms(sub):
    return {f: int(v) for f, op, v in fc.CASE_TERM.findall(sub.get("case") or "") if op == "=="}


def category(sub):
    """The stratum of a sub-property (see sample)."""
    if sub["name"] == "mem":
        return "mem"
    if sub["name"].endswith(".frame"):
        return "frame"
    t = terms(sub)
    rd = t.get("rd")
    srcs = [t[f] for f in ("rs1", "rs2") if f in t]
    if not srcs:
        return "write"
    if len(srcs) == 1:
        s = srcs[0]
        return "zero" if s == 0 else "rd" if s == rd else "distinct"
    a, b = srcs
    if a == 0 and b == 0:
        return "zero2"
    if a == 0 or b == 0:
        return "zero1"
    if a == b:
        return "equal"
    if rd is not None and rd in (a, b):
        return "rd"
    return "distinct"


QUOTAS = {
    # writes with no operand field (LUI, AUIPC, JAL)
    0: {"mem": 1, "frame": 6, "write": 13},
    # writes with rs1 (ADDI, ANDI, SLTI)
    1: {"mem": 1, "frame": 3, "zero": 2, "rd": 2, "distinct": 12},
    # writes with rs1 and rs2 (ADD, SUB, OR, XOR)
    2: {"mem": 1, "frame": 3, "zero2": 1, "zero1": 2, "equal": 2, "rd": 3, "distinct": 8},
}
TRAIN_QUOTA = {"mem": 1, "frame": 3, "zero": 2, "rd": 2, "distinct": 8}


def quotas(subs, size, train):
    """Strata and their sizes for a case.  Without GPR states (branches, stores) the size is shared evenly among the
    compared states (the first states in sorted order get one more), and within a state of n sub-properties there is
    one with rs1 = rs2 = 0, one with exactly one zero field, one with rs1 = rs2 != 0 and n - 3 with distinct nonzero
    fields."""
    if subs[0]["name"] == "mem":
        n = len([f for f in ("rs1", "rs2") if f in terms(subs[-1])])
        return {(None, c): k for c, k in (TRAIN_QUOTA if train else QUOTAS[n]).items()}
    states = sorted({s["states"][0] for s in subs})
    out = {}
    for i, s in enumerate(states):
        n = size // len(states) + (1 if i < size % len(states) else 0)
        out.update({(s, "zero2"): 1, (s, "zero1"): 1, (s, "equal"): 1, (s, "distinct"): n - 3})
    return out


def sample(subs, size, seed, train):
    """Stratified sample without replacement, in split order; random.Random(seed).sample within each stratum."""
    rng = random.Random(seed)
    field_split = subs[0]["name"] != "mem"
    picked = set()
    for (state, cat), k in sorted(quotas(subs, size, train).items(), key=lambda x: (x[0][0] or "", x[0][1])):
        pool = [s["name"] for s in subs if category(s) == cat and (not field_split or s["states"][0] == state)]
        if len(pool) < k:
            raise ValueError("stratum {} {} has {:d} < {:d} sub-properties".format(state, cat, len(pool), k))
        picked.update(rng.sample(pool, k))
    return [s for s in subs if s["name"] in picked]


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def prepare(case, run, out, size, seed, train):
    src = os.path.join(REPO, "Piccolo_verification_done", case, "wrapper.v")
    with open(src) as f:
        text = name_operands(f.read())
    os.makedirs(os.path.join(run, case), exist_ok=True)
    os.makedirs(os.path.join(out, case), exist_ok=True)
    wrapper = os.path.join(run, case, "wrapper.v")
    with open(wrapper, "w") as f:
        f.write(text)
    units = ca.discover_units(wrapper, "ila", B0.format(case), os.path.join(run, case, "units"))
    subs = split(text)
    files = {"units.json": units, "candidates.json": uf_candidates(text), "s_pairs.json": rules.match_pairs(text),
             "subs-sample.json": sample(subs, size, seed, train)}
    for name, data in files.items():
        with open(os.path.join(out, case, name), "w") as f:
            json.dump(data, f, indent=1)
    with open(os.path.join(out, case, "wrapper.v.sha256"), "w") as f:
        f.write("{:s}  wrapper.v\n{:s}  Piccolo_verification_done/{:s}/wrapper.v\n".format(sha256(wrapper), sha256(src),
                                                                                         case))
    renamed = sorted(set(re.findall(r"(\w+)__rhs\b", text)))
    return {"case": case, "split": len(subs), "sample": len(files["subs-sample.json"]), "named_operands": renamed,
            "candidates": len(files["candidates.json"]), "s_pairs": files["s_pairs.json"]}


def main():
    run, out = (os.path.abspath(p) for p in sys.argv[1:3])
    failed = {}
    os.makedirs(out, exist_ok=True)
    for case in [TRAIN] + TESTS:
        size = TRAIN_SIZE if case == TRAIN else TEST_SIZE
        try:
            print(json.dumps(prepare(case, run, out, size, SEED, case == TRAIN)), flush=True)
        except (ValueError, RuntimeError, OSError, KeyError, subprocess.SubprocessError) as e:
            failed[case] = repr(e)
            print(json.dumps({"case": case, "failed": repr(e)}), flush=True)
    with open(os.path.join(out, "failed.json"), "w") as f:
        json.dump(failed, f, indent=1)


if __name__ == "__main__":
    main()
