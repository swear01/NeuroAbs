def choose(sub, design):
    states = sub["states"]

    is_write = False
    for term in sub["case_terms"]:
        if term["field"] == "rd" and term["op"] == "==":
            is_write = True

    is_pc = "pc" in states
    need_icache = is_write or is_pc

    ops = []
    for c in design["choices"]:
        if c["kind"] == "operator":
            ops.append(c)

    if is_write:
        op_levels = {}
        for c in ops:
            op_levels[c["id"]] = "keep"
    else:
        op_levels = uf_one_per_node(ops)

    result = {}
    for c in design["choices"]:
        cid = c["id"]
        kind = c["kind"]
        if kind == "unit":
            inst = c.get("instance", "")
            parts = inst.split(".")
            last = parts[len(parts) - 1]
            if last == "icache":
                if need_icache:
                    result[cid] = "keep"
                else:
                    result[cid] = "cut"
            else:
                result[cid] = "cut"
        elif kind == "gpr":
            result[cid] = choose_gpr_level(c["register"], sub, design)
        elif kind == "operator":
            result[cid] = op_levels.get(cid, "keep")
        else:
            result[cid] = c["levels"][0]
    return result


def operator_score(c):
    s = 0
    for src in c.get("rtl_operand_sources", []):
        t = src
        for ch in ["(", ")", "=", "?", ":", ";", ",", "&", "|", "!"]:
            t = t.replace(ch, " ")
        for tok in t.split():
            if tok.endswith("[6:0]"):
                s = s + 1
    return s


def uf_one_per_node(ops):
    groups = {}
    order = []
    for c in ops:
        node = c["ila_node"]
        if node not in groups:
            groups[node] = []
            order.append(node)
        groups[node].append(c)

    gi = []
    for node in order:
        gi.append((node, groups[node]))
    gi = sorted(gi, key=lambda item: max([operator_score(x) for x in item[1]]), reverse=True)

    used = set()
    uf_ids = set()
    for node, choices in gi:
        sc = sorted(choices, key=operator_score, reverse=True)
        picked = None
        for c in sc:
            if c["rtl_node"] not in used:
                picked = c
                break
        if picked is not None:
            uf_ids.add(picked["id"])
            used.add(picked["rtl_node"])

    res = {}
    for c in ops:
        if c["id"] in uf_ids:
            res[c["id"]] = "uf"
        else:
            res[c["id"]] = "keep"
    return res


def choose_gpr_level(j, sub, design):
    states = sub["states"]
    xname = "x" + str(j)
    compared = xname in states

    dest = False
    source = False
    for term in sub["case_terms"]:
        if term["field"] == "rd" and term["op"] == "==" and term["value"] == j:
            dest = True
        is_operand_field = False
        for of in design["operand_fields"]:
            if of == term["field"]:
                is_operand_field = True
        if is_operand_field and term["op"] == "==" and term["value"] == j:
            source = True

    if j == 0:
        return "keep"

    if compared:
        # pure destination: old value never read, so start-equality is useless
        if dest and not source:
            return "word"
        return "keep"

    # not compared
    if source:
        return "keep"
    return "havoc"
