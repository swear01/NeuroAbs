def to_int(v):
    if isinstance_int(v):
        return v
    s = str(v).strip()
    if len(s) > 0 and s.isdigit():
        return int(s)
    return -1


def isinstance_int(v):
    # restricted: no isinstance; detect ints via str round trip
    s = str(v)
    if len(s) > 0 and s.isdigit() and not (str(s) is v):
        return False
    return False


def instr_name(design):
    desc = design.get("description", "") or ""
    lines = desc.split("\n")
    first = lines[0] if len(lines) > 0 else ""
    toks = [t.strip() for t in first.split()]
    for i, t in enumerate(toks):
        if t == "/" and i + 1 < len(toks):
            return toks[i + 1].strip().strip(".").upper()
    return ""


def gpr_of_state(s):
    s = str(s)
    if len(s) >= 2 and s[0] == "x" and s[1:].isdigit():
        return int(s[1:])
    return None


def choose(sub, design):
    choices = design.get("choices", [])
    states = sub.get("states", []) or []
    terms = sub.get("case_terms", []) or []
    operand_fields = design.get("operand_fields", []) or []

    keep_regs = set()
    keep_all = False

    # registers of compared states
    for s in states:
        r = gpr_of_state(s)
        if r is not None:
            keep_regs.add(r)

    # operand registers fixed by the case
    fixed_fields = set()
    for t in terms:
        f = t.get("field")
        if t.get("op") == "==" and (f in ("rs1", "rs2") or f in operand_fields):
            v = to_int(t.get("value"))
            if v >= 0:
                fixed_fields.add(f)
                keep_regs.add(v)

    # operand fields not fixed by the case: may the compared states depend on them?
    unfixed = [f for f in operand_fields if f not in fixed_fields]
    if len(unfixed) > 0:
        safe_states = set(["pc", "load_en", "store_en", "x0"])
        has_gpr_state = False
        for s in states:
            r = gpr_of_state(s)
            if r is not None and r != 0:
                has_gpr_state = True
        name = instr_name(design)
        only_safe = all(s in safe_states for s in states)
        if has_gpr_state or (not only_safe) or name == "JALR":
            keep_all = True

    result = {}
    for c in choices:
        cid = c["id"]
        kind = c.get("kind")
        levels = c.get("levels", [])
        lvl = "keep"
        if kind == "gpr":
            r = to_int(c.get("register"))
            if keep_all or r in keep_regs:
                lvl = "keep"
            else:
                lvl = "havoc"
        if lvl not in levels:
            lvl = "keep" if "keep" in levels else levels[0]
        result[cid] = lvl
    return result
