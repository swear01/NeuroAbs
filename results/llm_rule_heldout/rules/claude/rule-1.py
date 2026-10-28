def instr_name(design):
    desc = design.get("description", "") or ""
    lines = desc.split("\n")
    first = lines[0] if lines else ""
    toks = [t.strip() for t in first.split()]
    for i, t in enumerate(toks):
        if t == "/" and i + 1 < len(toks):
            return toks[i + 1].strip().strip(".").upper()
    return ""


def gpr_of_state(s):
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
        if f in ("rs1", "rs2") and t.get("op") == "==":
            fixed_fields.add(f)
            try:
                keep_regs.add(int(t.get("value")))
            except Exception:
                pass
        elif f in operand_fields and t.get("op") == "==":
            fixed_fields.add(f)
            try:
                keep_regs.add(int(t.get("value")))
            except Exception:
                pass

    # operand fields not fixed by the case: may the compared states depend on them?
    unfixed = [f for f in operand_fields if f not in fixed_fields]
    if len(unfixed) > 0:
        safe_states = set(["pc", "load_en", "store_en", "x0"])
        has_gpr_state = any(
            gpr_of_state(s) is not None and gpr_of_state(s) != 0 for s in states
        )
        name = instr_name(design)
        only_safe = all(s in safe_states for s in states)
        if has_gpr_state or (not only_safe) or name in ("JALR",):
            keep_all = True

    # x0 needed whenever a read register is x0 (ILA x0 == 0 assumption)
    if 0 in keep_regs:
        keep_regs.add(0)

    result = {}
    for c in choices:
        cid = c["id"]
        kind = c.get("kind")
        levels = c.get("levels", [])
        if kind == "unit":
            lvl = "keep"
        elif kind == "operator":
            lvl = "keep"
        elif kind == "gpr":
            r = c.get("register")
            try:
                r = int(r)
            except Exception:
                r = -1
            if keep_all or r in keep_regs:
                lvl = "keep"
            else:
                lvl = "havoc"
        else:
            lvl = "keep"
        if lvl not in levels:
            lvl = "keep" if "keep" in levels else levels[0]
        result[cid] = lvl
    return result
