def tokens_of(text):
    toks = []
    cur = ""
    for ch in text:
        if ch.isdigit() or ch.lower() != ch.upper() or ch == "_":
            cur = cur + ch
        else:
            if cur:
                toks.append(cur)
            cur = ""
    if cur:
        toks.append(cur)
    return toks


def state_reg(s):
    if s.startswith("x") and len(s) > 1 and s[1:].isdigit():
        return int(s[1:])
    return None


def last_inst_token(inst):
    parts = inst.split(".")
    return parts[len(parts) - 1]


def choose(sub, design):
    choices = design.get("choices", [])
    states = sub.get("states", []) or []
    terms = sub.get("case_terms", []) or []
    operand_fields = design.get("operand_fields", []) or []
    desc_toks = set([t.upper() for t in tokens_of(design.get("description", "") or "")])

    rd_eq = None
    rd_ne = None
    field_vals = {}
    for t in terms:
        f = t.get("field")
        op = t.get("op")
        v = t.get("value")
        if f == "rd":
            if op == "==":
                rd_eq = v
            else:
                rd_ne = v
        elif op == "==":
            field_vals[f] = v

    reg_states = [state_reg(s) for s in states if state_reg(s) is not None]
    other_states = [s for s in states if state_reg(s) is None]

    keep_regs = set()
    word_regs = set()
    keep_all = False

    if rd_ne is not None:
        # frame: register must keep its value
        keep_regs.add(rd_ne)
    elif rd_eq is not None:
        for f in operand_fields:
            if f in field_vals:
                keep_regs.add(field_vals[f])
            else:
                keep_all = True
        if rd_eq not in keep_regs:
            word_regs.add(rd_eq)
    else:
        # no rd in case: mem sub or branch/store per-state subs
        for r in reg_states:
            keep_regs.add(r)
        if len(terms) == 0 and len(operand_fields) > 0:
            basic = set(["pc", "load_en", "store_en"])
            extra = [s for s in other_states if s not in basic]
            if len(extra) > 0 or "JALR" in desc_toks:
                keep_all = True
        else:
            for f in operand_fields:
                if f in field_vals:
                    keep_regs.add(field_vals[f])
                else:
                    keep_all = True

    compares_pc = "pc" in states

    out = {}
    for c in choices:
        cid = c["id"]
        kind = c.get("kind")
        levels = c.get("levels", [])
        lvl = levels[0] if levels else "keep"
        if kind == "unit":
            tok = last_inst_token(c.get("instance", ""))
            if tok == "icache" and compares_pc:
                lvl = "keep"
            elif "cut" in levels:
                lvl = "cut"
            else:
                lvl = "keep"
        elif kind == "gpr":
            r = c.get("register")
            if keep_all or r in keep_regs:
                lvl = "keep"
            elif r in word_regs:
                lvl = "word" if "word" in levels else "keep"
            else:
                lvl = "havoc" if "havoc" in levels else ("word" if "word" in levels else "keep")
        elif kind == "operator":
            lvl = "keep"
        if lvl not in levels and len(levels) > 0:
            lvl = levels[0]
        out[cid] = lvl
    return out
