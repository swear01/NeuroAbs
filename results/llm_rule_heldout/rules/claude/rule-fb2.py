def tokens_of(text):
    toks = []
    cur = ""
    for ch in text:
        if ch.isdigit() or ch.lower() != ch.upper():
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


def name_tokens(name):
    return set([t.lower() for t in tokens_of(name.replace("$", "_").replace(".", "_"))])


def op_score(c, writes_rd):
    toks = name_tokens(c.get("rtl_node", ""))
    s = 0
    is_addr = ("addr" in toks) or ("eaddr" in toks)
    if writes_rd:
        if "rd" in toks and "val" in toks:
            s = s + 10
        if "result" in toks:
            s = s + 3
        if is_addr:
            s = s - 5
    else:
        if is_addr:
            s = s + 5
    return s


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

    # operator selection: only for operand-specific subs with a nonzero operand
    nonzero_operand = any([field_vals.get(f, 0) != 0 for f in operand_fields if f in field_vals])
    use_uf = (rd_ne is None) and nonzero_operand and (not keep_all)
    writes_rd = rd_eq is not None
    uf_ids = set()
    if use_uf:
        ops = [c for c in choices if c.get("kind") == "operator" and "uf" in c.get("levels", [])]
        scored = []
        for i, c in enumerate(ops):
            scored.append((-op_score(c, writes_rd), i, c))
        scored = sorted(scored, key=lambda x: (x[0], x[1]))
        used_ila = set()
        used_rtl = set()
        for item in scored:
            c = item[2]
            if item[0] > 0:
                continue  # negative score: do not use
            a = c.get("ila_node")
            b = c.get("rtl_node")
            if a in used_ila or b in used_rtl:
                continue
            used_ila.add(a)
            used_rtl.add(b)
            uf_ids.add(c["id"])

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
            lvl = "uf" if cid in uf_ids else "keep"
        if lvl not in levels and len(levels) > 0:
            lvl = levels[0]
        out[cid] = lvl
    return out
