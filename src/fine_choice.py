"""Sub-properties and register-level choices for the Piccolo and Flute ILA wrappers.

The ILA property is the conjunction of variable_map_assert conjuncts, one per
GPR plus pc, load_en, store_en and x0.  A sub-property keeps some conjuncts and
may be restricted to a case, a condition on the instruction that the ILA
executes, latched at __START__.  The original property holds when every
conjunct holds in every case of a split that covers all instructions.

Each sub-property has its own abstraction: the set of GPRs it keeps, and a
level for every unit of choice_abstraction.  A GPR j that is not kept is
abstracted in three sound ways: the register file word arr[j] is a free value
in every cycle, the ILA state xj is a free value in every cycle, and every
assumption that refers only to removed GPRs is dropped.  A word-level GPR
keeps its register file word and ILA state but its assumptions are dropped too.

A sub-property may also abstract a binary operator that the ILA and the RTL
both compute, such as the ADDI adder, by an uninterpreted function: both
results become free values in every cycle.  The operands and results of both
at the latest __START__ are latched, and an assumption requires equal results
when the latched operands are equal (Ackermann's constraint).  The true
results satisfy the assumption, so every concrete trace remains.
"""
import argparse
import itertools
import json
import os
import re
import sys
import time

import btor_witness
import choice_abstraction as ca

ASSIGN = re.compile(r"^assign\s+(\w+)\s*=\s*(.*?)\s*;\s*$")
WIRE_ALL = {"assert": "__all_assert_wire__", "assume": "__all_assume_wire__"}
STATE_NAME = re.compile(r"__ILA_SO_(\w+?)\)")
GPR_REF = re.compile(r"__ILA_SO_x(\d+)\b|regfile__DOT__arr_(\d+)_\b")
RECORDER_OF = re.compile(r"\((__auxvar\d+__recorder)\)==\(RTL__DOT__gpr_regfile__DOT__regfile__DOT__arr_(\d+)_\)")
RECORDER_REF = re.compile(r"__auxvar\d+__recorder\b")
INST_LATCH = "__split_inst__"
FIELDS = {"rd": ("[11:7]", 5), "rs1": ("[19:15]", 5), "rs2": ("[24:20]", 5), "imm": ("[31:20]", 12)}
GPR_WORD = "RTL.gpr_regfile.regfile.arr"
CASE_TERM = re.compile(r"(rd|rs1|rs2|imm)(==|!=)(\d+)")
NUM_GPRS = 32
GPR_UNIT = "gpr_regfile_regfile"


def read_assigns(text):
    assigns = {}
    for line in text.splitlines():
        m = ASSIGN.match(line.strip())
        if m:
            assigns[m.group(1)] = m.group(2)
    return assigns


def conjunct_names(assigns, kind):
    return re.findall(r"\((\w+)\)", assigns[WIRE_ALL[kind]])


def gpr_refs(body, recorders):
    refs = {int(a or b) for a, b in GPR_REF.findall(body)}
    refs.update(recorders[r] for r in RECORDER_REF.findall(body) if r in recorders)
    return refs


def recorder_map(assigns):
    return {m.group(1): int(m.group(2)) for body in assigns.values() for m in RECORDER_OF.finditer(body)}


def property_conjuncts(text):
    """Map each ILA state name (pc, load_en, store_en, x0, x1, ...) to its assert conjunct."""
    assigns = read_assigns(text)
    named = {}
    for c in conjunct_names(assigns, "assert"):
        m = STATE_NAME.search(assigns[c])
        if not m:
            raise ValueError("no ILA state in " + c)
        named.setdefault(m.group(1), []).append(c)
    return named


def case_expr(case):
    """Verilog condition for a case such as 'rd==5&&rs1==3' over the latched instruction."""
    terms = []
    for part in case.split("&&"):
        m = CASE_TERM.fullmatch(part.strip())
        if not m:
            raise ValueError("bad case term " + part)
        bits, width = FIELDS[m.group(1)]
        value = int(m.group(3))
        if value >= 1 << width:
            raise ValueError("value {:d} does not fit {:s}".format(value, m.group(1)))
        terms.append("({:s}{:s} {:s} {:d}'d{:d})".format(INST_LATCH, bits, m.group(2), width, value))
    return " && ".join(terms)


def split_wrapper(text, spec):
    """Return the wrapper text for a sub-property spec."""
    assigns = read_assigns(text)
    named = property_conjuncts(text)
    asserts = []
    for state in spec["states"]:
        for c in named[state]:
            if spec.get("rd_guard") and re.fullmatch(r"x[1-9]\d*", state):
                c = "(!({:s})) || ({:s})".format(case_expr("rd==" + state[1:]), c)
            asserts.append(c)
    recorders = recorder_map(assigns)
    keep = set(range(NUM_GPRS)) if spec.get("keep_gprs", "all") == "all" else set(spec["keep_gprs"])
    assumes = [c for c in conjunct_names(assigns, "assume")
               if not gpr_refs(assigns[c], recorders) or gpr_refs(assigns[c], recorders) & keep]
    prop = " && ".join("(" + c + ")" for c in asserts) or "1'b1"
    if spec.get("case"):
        prop = "(!({:s})) || ({:s})".format(case_expr(spec["case"]), prop)
    out = []
    in_wrapper = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("module wrapper("):
            in_wrapper = True
        m = ASSIGN.match(stripped)
        if m and m.group(1) == WIRE_ALL["assert"]:
            line = "assign {:s} = {:s} ;".format(WIRE_ALL["assert"], prop)
        elif m and m.group(1) == WIRE_ALL["assume"]:
            line = "assign {:s} = {:s} ;".format(WIRE_ALL["assume"], " && ".join("(" + c + ")" for c in assumes) or "1'b1")
        elif in_wrapper and stripped == "endmodule":
            out.extend(["reg [31:0] {:s};".format(INST_LATCH),
                        "always @(posedge clk) if (__START__) {:s} <= __ILA_I_inst;".format(INST_LATCH)])
            in_wrapper = False
        out.append(line)
    return "\n".join(out) + "\n"


def module_span(text, module):
    start = text.index("module " + module + "(")
    return start, text.index("endmodule", start)


def operator_args(text, module, node):
    """Return (left, operator, right) of 'assign node = left op right;' in a module."""
    start, end = module_span(text, module)
    m = re.compile(r"assign\s+" + re.escape(node) + r"\s*=\s*(.*?);", re.S).search(text, start, end)
    if not m:
        raise ValueError("no assignment of {:s} in {:s}".format(node, module))
    parts = re.fullmatch(r"\(?\s*([\w$']+)\s*\)?\s*([-+^&|]|<<|>>)\s*\(?\s*([\w$']+)\s*\)?", m.group(1).strip())
    if not parts:
        raise ValueError("{:s} is not a binary operator on two signals".format(node))
    return parts.groups()


def instance_module(text, instance):
    m = re.search(r"^\s*(\w+)\s+" + re.escape(instance) + r"\s*\(", text, re.M)
    if not m:
        raise ValueError("no instance " + instance)
    return m.group(1)


def add_ports(text, module, instance, ports, assigns, replace):
    """Add ports (direction, width, name, wrapper net) to a module and its instance, and rewrite one assignment."""
    start, end = module_span(text, module)
    body = text[start:end]
    header_end = body.index(");") + 2
    decls = "".join("\n{:s} [{:d}:0] {:s};".format(d, w - 1, n) for d, w, n, _ in ports)
    tail = "".join("assign {:s} = {:s};\n".format(a, b) for a, b in assigns)
    node, value = replace
    body = re.sub(r"assign\s+" + re.escape(node) + r"\s*=\s*.*?;", "assign {:s} = {:s};".format(node, value),
                  body[:header_end].replace(module + "(", module + "(" + ", ".join(p[2] for p in ports) + ", ", 1)
                  + decls + body[header_end:], count=1, flags=re.S) + tail
    text = text[:start] + body + text[end:]
    connect = ", ".join(".{:s}({:s})".format(n, net) for _, _, n, net in ports)
    text, count = re.subn(r"(^\s*" + re.escape(module) + r"\s+" + re.escape(instance) + r"\s*\()",
                          lambda m: m.group(1) + connect + ", ", text, count=1, flags=re.M)
    if not count:
        raise ValueError("no instance {:s} of {:s} without parameters".format(instance, module))
    return text


def uf_rewrite(text, index, uf):
    """Abstract an ILA operator node and an RTL operator node by one uninterpreted function."""
    ila_module, rtl_module = instance_module(text, "ILA"), instance_module(text, "RTL")
    a, op, b = operator_args(text, ila_module, uf["ila"])
    ra, rop, rb = operator_args(text, rtl_module, uf["rtl"])
    if op != rop:
        raise ValueError("operators differ: {:s} and {:s}".format(op, rop))
    p = "__uf{:d}_".format(index)
    text = add_ports(text, ila_module, "ILA", [("input", 32, p + "w", p + "w"), ("output", 32, p + "a", p + "ila_a"),
                                              ("output", 32, p + "b", p + "ila_b")],
                     [(p + "a", a), (p + "b", b)], (uf["ila"], p + "w"))
    text = add_ports(text, rtl_module, "RTL", [("input", 32, p + "r", p + "free"), ("output", 32, p + "ra", p + "rtl_a"),
                                              ("output", 32, p + "rb", p + "rtl_b")],
                     [(p + "ra", ra), (p + "rb", rb)], (uf["rtl"], p + "r"))
    logic = [
        "wire [31:0] {0}w = $anyseq;".format(p),
        "wire [31:0] {0}free = $anyseq;".format(p),
        "wire [31:0] {0}ila_a, {0}ila_b, {0}rtl_a, {0}rtl_b;".format(p),
        "reg [31:0] {0}la, {0}lb, {0}lw, {0}lra, {0}lrb, {0}lr;".format(p),
        "reg {0}ok;".format(p),
        "always @(posedge clk) if (__START__) begin {0}la <= {0}ila_a; {0}lb <= {0}ila_b; {0}lw <= {0}w; "
        "{0}lra <= {0}rtl_a; {0}lrb <= {0}rtl_b; {0}lr <= {0}free; end".format(p),
        "always @(posedge clk) if (rst) {0}ok <= 1'b0; else if (__START__) {0}ok <= 1'b1;".format(p),
        "wire {0}assume = !({0}ok && {0}la == {0}lra && {0}lb == {0}lrb) || ({0}lw == {0}lr);".format(p),
    ]
    start, end = module_span(text, "wrapper")
    text = text[:end] + "\n".join(logic) + "\n" + text[end:]
    return re.sub(r"(assign\s+" + WIRE_ALL["assume"] + r"\s*=\s*)(.*?)(\s*;)",
                  lambda m: m.group(1) + m.group(2) + " && (" + p + "assume)" + m.group(3), text, count=1)


def uf_cut_lines(spec, select_dir, renames):
    """Name the free ILA and RTL results of every abstracted operator."""
    lines = []
    for i, _ in enumerate(spec.get("uf", [])):
        listing = os.path.join(select_dir, "uf{:d}.txt".format(i))
        lines.append("select -write {0:s} wrapper/w:__uf{1:d}_free wrapper/w:__uf{1:d}_w %u %ci* t:$anyseq %i"
                     .format(listing, i))
        for module, old, new in renames.get(listing, []):
            lines.extend(["cd " + module, "rename " + old + " " + new, "cd .."])
    return lines


def operand_fields(text):
    """The source register fields (rs1, rs2) that the ILA instruction reads."""
    start, end = module_span(text, instance_module(text, "ILA"))
    return [f for f in ("rs1", "rs2") if "inst" + FIELDS[f][0] in text[start:end]]


def ila_split(states, fields):
    """Sub-properties whose conjunction is the ILA property.

    mem keeps every compared state that is not a GPR x1..x31.  Each GPR xk has
    the case rd != k and, for every value of the source register fields, the
    case rd == k with those values; for each k these cases cover every
    instruction.
    """
    gprs = sorted(int(s[1:]) for s in states if re.fullmatch(r"x[1-9]\d*", s))
    subs = [{"name": "mem", "states": sorted(s for s in states if not re.fullmatch(r"x[1-9]\d*", s))}]
    for k in gprs:
        subs.append({"name": "x{:d}.frame".format(k), "states": ["x{:d}".format(k)], "case": "rd!={:d}".format(k)})
        for values in itertools.product(range(NUM_GPRS), repeat=len(fields)):
            terms = ["{:s}=={:d}".format(f, v) for f, v in zip(fields, values)]
            suffix = ".".join(t.replace("==", "=") for t in terms) if terms else "write"
            subs.append({"name": "x{:d}.{:s}".format(k, suffix), "states": ["x{:d}".format(k)], "case": "&&".join(["rd=={:d}".format(k)] + terms)})
    return subs


def coarsest(sub, units, ufs):
    """Every unit at its coarsest level, every GPR removed and every operator pair abstracted."""
    return {"states": sub["states"], "case": sub.get("case"), "rd_guard": sub.get("rd_guard", False), "keep_gprs": [],
            "units": {u["id"]: u["levels"][-1] for u in units if u["id"] != GPR_UNIT},
            "uf": [{"ila": uf["ila"], "rtl": uf["rtl"]} for uf in ufs]}


def structural(sub, units, ufs):
    """Keep the GPRs that the sub-property compares or that its case names as rs1 or rs2, with the compared rd at
    word level; cut every unit and abstract every operator pair."""
    named = {int(s[1:]) for s in sub["states"] if re.fullmatch(r"x\d+", s)}
    sources = {int(v) for f, op, v in CASE_TERM.findall(sub.get("case") or "") if f in ("rs1", "rs2") and op == "=="}
    rd = {int(v) for f, op, v in CASE_TERM.findall(sub.get("case") or "") if f == "rd" and op == "=="}
    spec = coarsest(sub, units, ufs)
    spec["keep_gprs"] = sorted((named - rd) | sources)
    spec["word_gprs"] = sorted((named & rd) - sources)
    return spec


def removed_gprs(spec):
    keep = set(range(NUM_GPRS)) if spec.get("keep_gprs", "all") == "all" else set(spec["keep_gprs"])
    return sorted(set(range(NUM_GPRS)) - keep - set(spec.get("word_gprs", [])))


def word_cut_lines(spec, select_dir, renames):
    """Cut the removed register file words and ILA registers after the memories are mapped."""
    lines = ["select *", "memory"]
    for j in removed_gprs(spec):
        for choice_id, wire in (("gpr_w{:d}".format(j), "w:{:s}?{:d}?".format(GPR_WORD, j)),
                                ("ila_x{:d}".format(j), "w:ILA.x{:d}".format(j))):
            listing = os.path.join(select_dir, choice_id + ".txt")
            lines.extend(["select -set before t:$anyseq", "cutpoint wrapper/" + wire,
                          "select -write " + listing + " t:$anyseq @before %d"])
            for module, old, new in renames.get(listing, []):
                lines.extend(["cd " + module, "rename " + old + " " + new, "cd .."])
    return lines


def build(wrapper, spec, units, out, workdir):
    """Build the BTOR2 model of a sub-property; return the choice ids that have free values."""
    os.makedirs(workdir, exist_ok=True)
    with open(wrapper) as f:
        text = f.read()
    derived = os.path.join(workdir, "wrapper.v")
    text = split_wrapper(text, spec)
    for i, uf in enumerate(spec.get("uf", [])):
        text = uf_rewrite(text, i, uf)
    with open(derived, "w") as f:
        f.write(text)
    choices = ca.assignment_choices(units, spec.get("units", {}))
    table = ca.instance_table(ca.hierarchy_json(derived, workdir)) if any(c["kind"] == "module" for c in choices) else {}
    select_dir = os.path.join(workdir, "cut_cells")
    os.makedirs(select_dir, exist_ok=True)
    for name in os.listdir(select_dir):
        os.unlink(os.path.join(select_dir, name))

    def script(renames):
        return (ca.header(derived, "ila") + ca.cut_lines(choices, table, select_dir, renames)
                + word_cut_lines(spec, select_dir, renames) + uf_cut_lines(spec, select_dir, renames) + ca.footer(out))

    ca.run_yosys(script({}), out + ".pass1.log")
    renames = {}
    for name in sorted(os.listdir(select_dir)):
        listing = os.path.join(select_dir, name)
        with open(listing) as f:
            cells = [line.strip() for line in f if line.strip()]
        renames[listing] = [(cell.split("/", 1)[0], cell.split("/", 1)[1],
                             "choice__{:s}__{:d}".format(name[:-4], i)) for i, cell in enumerate(cells)]
    ca.run_yosys(script(renames), out + ".yosys.log")
    names = ca.read_btor(out)[0]
    return sorted({m.group(1) for name in names.values() for m in [ca.CHOICE_NAME.search(name)] if m})


def unit_of(choice_id, units):
    """Map a choice id from the free value names back to a unit id or 'gpr<j>'."""
    m = re.fullmatch(r"(?:gpr_w|ila_x)(\d+)", choice_id)
    if m:
        return "gpr" + m.group(1)
    if re.fullmatch(r"uf\d+", choice_id):
        return choice_id
    for u in units:
        if choice_id == u["id"] or choice_id.startswith(u["id"] + "_m"):
            return u["id"]
    return None


def check(wrapper, spec, units, workdir, time_limit):
    started = time.time()
    model = os.path.join(workdir, "model.btor2")
    present = build(wrapper, spec, units, model, model + ".work")
    build_seconds = time.time() - started
    verdict, depth, ric3_seconds = ca.ric3_check(model, time_limit, model + ".ric3.log")
    record = {"spec": spec, "model": model, "choices_with_free_values": present,
              "coi_state_bits": sum(ca.coi_state_bits(model).values()), "ric3": verdict,
              "ric3_seconds": ric3_seconds, "cex_depth": depth, "build_seconds": build_seconds}
    if verdict == "SAT":
        replay_started = time.time()
        counts = {}
        for name in btor_witness.free_names(model, model + ".ric3.log"):
            m = ca.CHOICE_NAME.search(name)
            unit = unit_of(m.group(1), units) if m else None
            if unit:
                counts[unit] = counts.get(unit, 0) + 1
        record.update({"replay_seconds": time.time() - replay_started, "counterexample_units": counts})
    return record


def kept_with(spec, gprs):
    keep = spec.get("keep_gprs", "all")
    return "all" if keep == "all" else sorted(set(keep) | set(gprs))


def refine(spec, units, counts):
    """Move the unit or GPR with the most free values in the counterexample one level towards keep.

    A removed GPR is restored to keep.  A counterexample without free values of any choice may be due to the
    assumptions dropped for word-level GPRs, which are then restored to keep; with none, it is real.
    """
    spec = json.loads(json.dumps(spec))
    if not counts:
        if not spec.get("word_gprs"):
            return None
        spec["keep_gprs"] = kept_with(spec, spec.pop("word_gprs"))
        return spec
    target = min(counts, key=lambda k: (-counts[k], k))
    if re.fullmatch(r"gpr\d+", target):
        j = int(target[3:])
        spec["keep_gprs"] = kept_with(spec, [j])
        spec["word_gprs"] = [w for w in spec.get("word_gprs", []) if w != j]
    elif re.fullmatch(r"uf\d+", target):
        del spec["uf"][int(target[2:])]
    else:
        levels = next(u["levels"] for u in units if u["id"] == target)
        level = spec.setdefault("units", {}).get(target, "keep")
        spec["units"][target] = levels[levels.index(level) - 1]
    return spec


def cegar(wrapper, spec, units, workdir, time_limit, max_iterations):
    history = []
    status = None
    for iteration in range(max_iterations + 1):
        record = check(wrapper, spec, units, os.path.join(workdir, "iter{:d}".format(iteration)), time_limit)
        record["iteration"] = iteration
        history.append(record)
        status = record["ric3"]
        if status != "SAT":
            break
        nxt = refine(spec, units, record["counterexample_units"])
        if nxt is None:
            status = "real"
            break
        if iteration == max_iterations:
            status = "max_iterations"
            break
        record["refined_to"] = nxt
        spec = nxt
    total = sum(r["build_seconds"] + r["ric3_seconds"] + r.get("replay_seconds", 0) for r in history)
    return {"status": status, "final_spec": spec, "refinements": len(history) - 1, "total_seconds": total,
            "history": history}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("split", help="list the sub-properties of the ILA property")
    s.add_argument("--wrapper", required=True)
    r = sub.add_parser("cegar", help="check one sub-property spec with refinement")
    r.add_argument("--wrapper", required=True)
    r.add_argument("--units", required=True)
    r.add_argument("--spec", required=True, help="JSON sub-property spec")
    r.add_argument("--workdir", required=True)
    r.add_argument("--time-limit", type=int, default=3600)
    r.add_argument("--max-iterations", type=int, default=0)
    args = parser.parse_args(argv)
    wrapper = os.path.abspath(args.wrapper)
    if args.command == "split":
        with open(wrapper) as f:
            text = f.read()
        print(json.dumps(ila_split(sorted(property_conjuncts(text)), operand_fields(text)), indent=1))
        return 0
    with open(args.units) as f:
        units = json.load(f)
    with open(args.spec) as f:
        spec = json.load(f)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    result = cegar(wrapper, spec, units, workdir, args.time_limit, args.max_iterations)
    with open(os.path.join(workdir, "cegar.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "refinements", "total_seconds", "final_spec")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
