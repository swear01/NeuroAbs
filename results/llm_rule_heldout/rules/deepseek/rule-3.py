def tokens_of(s):
    t = str(s).lower()
    for ch in "_.$[]:+-*/()<>=!&|'":
        t = t.replace(ch, " ")
    return t.split()


def gpr_index(state):
    s = str(state)
    if len(s) > 1 and s[0] == "x" and s[1:].isdigit():
        return int(s[1:])
    return -1


def contains_any(tokens, words):
    for w in words:
        if w in tokens:
            return True
    return False


def choice_score(ch, has_gpr, has_pc, has_mem):
    toks = set()
    toks.update(tokens_of(ch.get("rtl_node", "")))
    for x in ch.get("rtl_expr", []):
        toks.update(tokens_of(x))
    for src in ch.get("rtl_operand_sources", []):
        toks.update(tokens_of(src))

    score = 0

    if has_gpr:
        if contains_any(toks, ["rd", "result", "write", "wb", "wdata"]):
            score += 20
        if "val" in toks:
            score += 10
        if contains_any(toks, ["data", "rdata", "load"]):
            score += 8
        if contains_any(toks, ["addr", "eaddr", "address"]):
            score += 5

    if has_pc:
        if "pc" in toks:
            score += 20
        if contains_any(toks, ["target", "next", "npc"]):
            score += 15
        if contains_any(toks, ["br", "branch", "jump"]):
            score += 15
        if contains_any(toks, ["cond", "cmp", "compare"]):
            score += 15
        if contains_any(toks, ["eq", "ne", "lt", "ge", "le", "gt"]):
            score += 10
        if contains_any(toks, ["addr", "eaddr", "address"]):
            score += 5

    if has_mem:
        if contains_any(toks, ["addr", "eaddr", "address"]):
            score += 15
        if contains_any(toks, ["mem", "store", "load"]):
            score += 10
        if contains_any(toks, ["valid", "word", "data", "rdata"]):
            score += 5

    if "31" in toks and "20" in toks:
        score += 5
    if "25" in toks and "7" in toks:
        score += 1

    return score


def choose(sub, design):
    states = sub.get("states", [])
    assertion = sub.get("assertion", [])

    all_sub_tokens = set()
    for s in states:
        all_sub_tokens.update(tokens_of(s))
    for a in assertion:
        all_sub_tokens.update(tokens_of(a))

    state_gprs = set()
    for s in states:
        j = gpr_index(s)
        if j >= 0:
            state_gprs.add(j)

    fixed = {}
    for term in sub.get("case_terms", []):
        if term.get("op") == "==":
            fixed[term.get("field")] = term.get("value")

    source_regs = set()
    for f in design.get("operand_fields", []):
        if f in fixed:
            source_regs.add(fixed[f])

    is_write_sub = False
    for term in sub.get("case_terms", []):
        if term.get("field") == "rd" and term.get("op") == "==":
            is_write_sub = True

    desc_tokens = set(tokens_of(design.get("description", "")))
    is_load = contains_any(desc_tokens, ["lb", "lh", "lw", "lbu", "lhu", "load"])
    need_dcache = ("dcache" in all_sub_tokens) or (is_load and is_write_sub)

    res = {}

    for ch in design.get("choices", []):
        cid = ch.get("id")
        kind = ch.get("kind")

        if kind == "gpr":
            j = ch.get("register")
            if j in state_gprs or j in source_regs:
                res[cid] = "keep"
            else:
                res[cid] = "havoc"

        elif kind == "unit":
            inst_toks = set(tokens_of(ch.get("instance", "")))
            mod_toks = set(tokens_of(ch.get("module", "")))
            unit_toks = set()
            unit_toks.update(inst_toks)
            unit_toks.update(mod_toks)

            if "csr" in unit_toks:
                if "csr" in all_sub_tokens:
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"
            elif "icache" in unit_toks:
                if "icache" in all_sub_tokens:
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"
            elif "dcache" in unit_toks:
                if need_dcache:
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"
            else:
                if len(unit_toks.intersection(all_sub_tokens)) > 0:
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"

        else:
            res[cid] = "keep"

    has_gpr = len(state_gprs) > 0
    has_pc = "pc" in all_sub_tokens
    has_mem = contains_any(all_sub_tokens, ["load", "store", "mem", "mem_req"])

    groups = {}
    for ch in design.get("choices", []):
        if ch.get("kind") == "operator":
            node = ch.get("ila_node")
            if node not in groups:
                groups[node] = []
            groups[node].append(ch)

    used_rtl = set()

    for node in groups:
        group = groups[node]
        cands = []
        for ch in group:
            sc = choice_score(ch, has_gpr, has_pc, has_mem)
            cands.append((sc, ch))

        cands = sorted(cands, key=lambda c: c[0], reverse=True)

        chosen = None
        chosen_score = 0
        for sc, ch in cands:
            if ch.get("rtl_node") not in used_rtl:
                chosen = ch
                chosen_score = sc
                break

        if chosen is None:
            for ch in group:
                res[ch.get("id")] = "keep"
        elif len(group) == 1 or chosen_score > 0:
            res[chosen.get("id")] = "uf"
            used_rtl.add(chosen.get("rtl_node"))
            for ch in group:
                if ch.get("id") != chosen.get("id"):
                    res[ch.get("id")] = "keep"
        else:
            for ch in group:
                res[ch.get("id")] = "keep"

    return res
