def gpr_state_num(s):
    if len(s) >= 2 and s[0] == "x" and s[1:].isdigit():
        return int(s[1:])
    return -1


def to_reg(v):
    sv = str(v).strip()
    if sv.isdigit():
        n = int(sv)
        if 0 <= n <= 31:
            return n
    return -1


def choose(sub, design):
    states = sub.get("states", []) or []
    terms = sub.get("case_terms", []) or []
    op_fields = design.get("operand_fields", []) or []

    gpr_states = set()
    other_states = []
    for s in states:
        n = gpr_state_num(s)
        if n >= 1:
            gpr_states.add(n)
        else:
            other_states.append(s)

    # registers that must stay exact
    needed = set(gpr_states)
    for t in terms:
        f = t.get("field")
        if t.get("op") == "==" and (f in op_fields or f in ["rs1", "rs2"]):
            r = to_reg(t.get("value"))
            if r >= 0:
                needed.add(r)
    if "x0" in states:
        needed.add(0)

    gpr_only = len(gpr_states) > 0 and len(other_states) == 0
    simple_states = set(["pc", "x0", "load_en", "store_en"])
    only_simple = all(s in simple_states for s in other_states)

    out = {}
    for c in design.get("choices", []):
        cid = c["id"]
        kind = c.get("kind")
        levels = c.get("levels", [])
        lvl = levels[0] if len(levels) > 0 else "keep"
        if kind == "gpr":
            r = to_reg(c.get("register"))
            if r in needed:
                lvl = "keep"
            elif "havoc" in levels:
                lvl = "havoc"
            elif "word" in levels:
                lvl = "word"
            else:
                lvl = "keep"
        elif kind == "unit":
            inst = str(c.get("instance", ""))
            parts = inst.replace(".", " ").split()
            last = parts[-1] if len(parts) > 0 else ""
            if gpr_only:
                lvl = "cut" if "cut" in levels else "keep"
            else:
                if last == "dcache" and only_simple and "cut" in levels:
                    lvl = "cut"
                else:
                    lvl = "keep"
        else:
            lvl = "keep" if "keep" in levels else lvl
        if lvl not in levels and len(levels) > 0:
            lvl = levels[0]
        out[cid] = lvl
    return out
