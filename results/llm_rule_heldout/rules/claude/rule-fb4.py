def tokens_of(text):
    out = text
    for ch in "/.,:;()[]{}'\"!?=+-*&|<>\n\t":
        out = out.replace(ch, " ")
    return [t for t in out.split(" ") if t != ""]


def ident_tokens(name):
    parts = name.replace("$", "_").split("_")
    return [p.lower() for p in parts if p != ""]


def case_value(sub, field, op):
    for t in sub.get("case_terms", []) or []:
        if t.get("field") == field and t.get("op") == op:
            return t.get("value")
    return None


def state_reg(s):
    if len(s) >= 2 and s[0] == "x" and s[1:].isdigit():
        return int(s[1:])
    return None


def score_operator(c, prefer_addr):
    toks = set(ident_tokens(c.get("rtl_node", "")))
    score = 0
    if prefer_addr:
        if "addr" in toks or "eaddr" in toks:
            score += 10
    else:
        if "rd" in toks:
            score += 10
        if "val" in toks:
            score += 3
        srcs = c.get("rtl_operand_sources", []) or []
        for s in srcs:
            if "imem_instr[6:0]" in s.replace(" ", "").replace("near_mem$", ""):
                score += 5
                break
    score += len(c.get("rtl_operand_sources", []) or []) * 0.1
    return score


def choose(sub, design):
    choices = design.get("choices", [])
    states = sub.get("states", []) or []
    fields = design.get("operand_fields", []) or []
    desc_toks = set(t.upper() for t in tokens_of(design.get("description", "")))

    is_store = any(t in desc_toks for t in ["SB", "SH", "SW"])
    is_load = any(t in desc_toks for t in ["LB", "LH", "LW", "LBU", "LHU"])
    is_jalr = "JALR" in desc_toks

    has_pc = "pc" in states
    gpr_states = [state_reg(s) for s in states if state_reg(s) is not None]
    gpr_states_nz = [r for r in gpr_states if r != 0]
    non_gpr_states = [s for s in states if state_reg(s) is None]

    rd_eq = case_value(sub, "rd", "==")
    rd_ne = case_value(sub, "rd", "!=")
    is_write = rd_eq is not None and len(gpr_states_nz) > 0
    is_frame = rd_ne is not None and rd_eq is None

    src_regs = set()
    for f in fields:
        v = case_value(sub, f, "==")
        if v is not None:
            src_regs.add(int(v))
    no_case = len(sub.get("case_terms", []) or []) == 0

    keep_all_gprs = False
    if no_case and has_pc and len(fields) > 0 and is_jalr:
        keep_all_gprs = True

    # x0 needed if compared, read as a source, or source fields unconstrained
    need_x0 = (0 in gpr_states) or (0 in src_regs) or keep_all_gprs
    if no_case and len(fields) > 0:
        need_x0 = True

    res = {}
    for c in choices:
        cid = c["id"]
        kind = c.get("kind")
        levels = c.get("levels", ["keep"])
        if kind == "unit":
            inst_toks = ident_tokens(c.get("instance", "").replace(".", "_"))
            lvl = "keep"
            if "csr" in inst_toks:
                lvl = "keep" if has_pc else "cut"
            elif "dcache" in inst_toks:
                lvl = "keep" if (is_store or is_load) else "cut"
            elif "icache" in inst_toks:
                lvl = "keep" if has_pc else "cut"
            if lvl not in levels:
                lvl = "keep"
            res[cid] = lvl
        elif kind == "gpr":
            j = int(c.get("register", -1))
            if keep_all_gprs:
                lvl = "keep"
            elif j == 0:
                lvl = "keep" if need_x0 else "havoc"
            elif j in src_regs:
                lvl = "keep"
            elif j in gpr_states_nz:
                if is_write:
                    lvl = "word"
                else:
                    lvl = "keep"
            else:
                lvl = "havoc"
            if lvl not in levels:
                lvl = "keep"
            res[cid] = lvl

    ops = [c for c in choices if c.get("kind") == "operator"]
    for c in ops:
        res[c["id"]] = "keep"
    use_uf = is_write
    prefer_addr = False
    if not use_uf and not is_frame and not no_case and len(non_gpr_states) > 0 \
            and len(gpr_states_nz) == 0 and (is_store or is_load):
        use_uf = True
        prefer_addr = True
    if use_uf:
        by_ila = {}
        order = []
        for c in ops:
            if "uf" not in c.get("levels", []):
                continue
            k = c.get("ila_node")
            if k not in by_ila:
                by_ila[k] = []
                order.append(k)
            by_ila[k].append(c)
        used_rtl = set()
        for k in order:
            cands = sorted(by_ila[k], key=lambda c: -score_operator(c, prefer_addr))
            for c in cands:
                rn = c.get("rtl_node")
                if rn in used_rtl:
                    continue
                res[c["id"]] = "uf"
                used_rtl.add(rn)
                break
    return res
