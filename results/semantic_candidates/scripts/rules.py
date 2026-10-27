"""rules.py <case> <wrapper.v> <units.json> <split-only model.btor2> <out.jsonl>: pre-registered non-LLM arms.

Fixed before any LLM answer for SB or BEQ exists (see README, "Pre-registered rules").  For every sub-property
of the case it writes three specs:

- coi:  keep every unit and GPR word with a state in the cone of influence of the split-only model; no UF.
- S:    fine_choice.structural (keep the GPRs that the sub-property compares or its case names as rs1/rs2,
        cut every unit) with the UF pairs of match_pairs.
- auto: fine_choice.coarsest (every GPR removed, every unit cut) with the UF pairs of match_pairs; refined by
        fine_choice.refine (CEGAR).

match_pairs is the structural operator matcher: an ILA node is a binary operator (fine_choice.operator_args)
with an operand that reads the GPR file (its assignment is a mux that selects x31); its RTL partner is a node of
the RTL module with the same operator and an operand named rs1_val* or rs2_val*.  Among several partners the
matcher takes one whose other operand is named like an immediate (SEXT or imm), else the first in source order.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src"))
import choice_abstraction as ca  # noqa: E402
import fine_choice as fc  # noqa: E402

PAIRS = [(5, 6), (12, 3), (31, 1), (20, 9), (7, 26)]
FIELD_STATE = {"BEQ": "pc", "SB": "store_en"}
GPR_WORD = re.compile(r"RTL\.gpr_regfile\.regfile\.arr\[(\d+)\]")


def binary_nodes(text, module):
    start, end = fc.module_span(text, module)
    out = []
    for name in re.findall(r"assign\s+(\w+)\s*=", text[start:end]):
        try:
            out.append((name,) + fc.operator_args(text, module, name))
        except ValueError:
            continue
    return out


def match_pairs(text):
    ila, rtl = fc.instance_module(text, "ILA"), fc.instance_module(text, "RTL")
    start, end = fc.module_span(text, ila)
    assigns = fc.read_assigns(text[start:end])
    reads_gpr = {n for n, body in assigns.items() if re.search(r"\(\s*x31\s*\)", body)}
    rtl_nodes = binary_nodes(text, rtl)
    pairs = []
    for name, a, op, b in binary_nodes(text, ila):
        if a not in reads_gpr and b not in reads_gpr:
            continue
        partners = [(n, x, y) for n, x, o, y in rtl_nodes
                    if o == op and any(re.match(r"rs[12]_val", v) for v in (x, y))]
        if not partners:
            continue
        imm = [p for p in partners if re.search(r"SEXT|imm", p[1] + p[2])]
        pairs.append({"ila": name, "rtl": (imm or partners)[0][0]})
    return pairs


def subproperties(case, states):
    """The standard split (mem) and the rs1 x rs2 field split of the conjunct that split-only cannot prove."""
    subs = [{"name": "mem", "states": sorted(states)}]
    s = FIELD_STATE[case]
    for a, b in PAIRS:
        subs.append({"name": "{:s}.rs1={:d}.rs2={:d}".format(s, a, b), "states": [s],
                     "case": "rs1=={:d}&&rs2=={:d}".format(a, b)})
    return subs


def coi_spec(sub, units, model):
    bits = ca.coi_state_bits(model)
    spec = {"states": sub["states"], "case": sub.get("case"), "rd_guard": False}
    gprs = sorted({int(m.group(1)) for n in bits for m in [GPR_WORD.match(n)] if m})
    spec["keep_gprs"] = "all" if gprs == list(range(fc.NUM_GPRS)) else gprs
    spec["units"] = {u["id"]: ("keep" if any(ca.under(n, u["path"]) for n in bits) else u["levels"][-1])
                     for u in units if u["id"] != fc.GPR_UNIT}
    return spec


def main():
    case, wrapper, units_path, model, out = sys.argv[1:6]
    with open(wrapper) as f:
        text = f.read()
    with open(units_path) as f:
        units = json.load(f)
    ufs = match_pairs(text)
    states = [s for s in fc.property_conjuncts(text) if not re.fullmatch(r"x[1-9]\d*", s)]
    with open(out, "w") as f:
        for sub in subproperties(case, states):
            for arm, spec in (("coi", coi_spec(sub, units, model)), ("S", fc.structural(sub, units, ufs)),
                              ("auto", fc.coarsest(sub, units, ufs))):
                f.write(json.dumps({"name": "{:s}.{:s}".format(sub["name"], arm), "spec": spec}) + "\n")
    print(json.dumps({"case": case, "uf_pairs": ufs}))


if __name__ == "__main__":
    main()
