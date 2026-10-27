def choose(sub, design):
    op_levels = compute_operator_levels(design)
    result = {}
    for choice in design["choices"]:
        cid = choice["id"]
        kind = choice["kind"]
        if kind == "unit":
            result[cid] = "cut"
        elif kind == "gpr":
            j = choice["register"]
            result[cid] = choose_gpr_level(j, sub, design)
        elif kind == "operator":
            result[cid] = op_levels.get(cid, "keep")
        else:
            result[cid] = choice["levels"][0]
    return result


def compute_operator_levels(design):
    ops = []
    for c in design["choices"]:
        if c["kind"] == "operator":
            ops.append(c)
    if not ops:
        return {}
    groups = {}
    for c in ops:
        node = c["ila_node"]
        if node not in groups:
            groups[node] = []
        groups[node].append(c)

    def score(c):
        s = 0
        sources = c.get("rtl_operand_sources", [])
        for src in sources:
            t = src
            for ch in ["(", ")", "=", "?", ":", ";", ",", "&", "|", "!"]:
                t = t.replace(ch, " ")
            for tok in t.split():
                if tok.endswith("[6:0]"):
                    s += 10
        return s

    group_items = list(groups.items())
    group_items = sorted(group_items, key=lambda item: max([score(c) for c in item[1]]), reverse=True)

    used_rtl = set()
    uf_ids = set()
    for node, choices in group_items:
        sorted_choices = sorted(choices, key=score, reverse=True)
        picked = None
        for c in sorted_choices:
            if c["rtl_node"] not in used_rtl:
                picked = c
                break
        if picked is not None:
            uf_ids.add(picked["id"])
            used_rtl.add(picked["rtl_node"])

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
        for f in design["operand_fields"]:
            if term["field"] == f and term["op"] == "==" and term["value"] == j:
                source = True

    compared_gprs = []
    for s in states:
        if s.startswith("x") and s[1:].isdigit():
            compared_gprs.append(int(s[1:]))

    if not compared:
        if compared_gprs == [0]:
            return "havoc"
        written_compared = False
        for term in sub["case_terms"]:
            if term["field"] == "rd" and term["op"] == "==":
                k = term["value"]
                if ("x" + str(k)) in states:
                    written_compared = True
                    break
        if source and written_compared:
            return "keep"
        return "havoc"
    else:
        if j == 0:
            return "keep"
        if dest and not source:
            return "word"
        else:
            return "keep"
