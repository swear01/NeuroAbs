def op_score(op):
    name = op["rtl_node"].lower()
    for ch in "._$[]0123456789":
        name = name.replace(ch, " ")
    tokset = set(name.split())
    s = 0
    if ("rd" in tokset) and ("val" in tokset):
        s += 10
    if "result" in tokset:
        s += 10
    if "alu" in tokset:
        s += 5
    if "addr" in tokset:
        s -= 10
    if "eaddr" in tokset:
        s -= 10
    if op["rtl_expr"][1] == op["ila_expr"][1]:
        s += 5
    for src in op["rtl_operand_sources"]:
        if "SEXT" in src:
            s += 5
            break
    for src in op["rtl_operand_sources"]:
        if "0010011" in src:
            s += 3
            break
    return s


def choose(sub, design):
    desc = design["description"].upper()
    for ch in [':', '/', '.', ',', '\n', '\t', '(', ')', '[', ']', '{', '}', ';', '\\', '"', "'"]:
        desc = desc.replace(ch, ' ')
    tokset = set(desc.split())

    load_tokens = set(["LOAD", "LW", "LH", "LB", "LHU", "LBU"])
    store_tokens = set(["STORE", "SW", "SH", "SB"])
    branch_tokens = set(["BRANCH", "BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU", "JAL", "JALR"])

    is_load = False
    is_store = False
    is_branch = False
    is_csr = False
    for t in tokset:
        if t in load_tokens:
            is_load = True
        if t in store_tokens:
            is_store = True
        if t in branch_tokens:
            is_branch = True
        if t.startswith("CSR"):
            is_csr = True

    # Registers that must stay concrete: the compared register and any
    # source register field pinned by the case.
    needed_gprs = set()
    is_write_sub = False
    for state in sub["states"]:
        if state.startswith("x") and state[1:].isdigit():
            num = int(state[1:])
            needed_gprs.add(num)
            for term in sub["case_terms"]:
                if term["field"] == "rd" and term["op"] == "==" and term["value"] == num:
                    is_write_sub = True
        elif state == "pc" and is_branch:
            for term in sub["case_terms"]:
                if term["field"] in design["operand_fields"] and term["op"] == "==":
                    needed_gprs.add(term["value"])

    for term in sub["case_terms"]:
        if term["field"] in design["operand_fields"] and term["op"] == "==":
            needed_gprs.add(term["value"])

    # Pick at most one operator to abstract with "uf".  For an arithmetic
    # write sub-property this should be the result/ALU node, not an address
    # computation.  If no convincing result node exists, keep operators exact.
    best_op = None
    best_score = -1000
    for choice in design["choices"]:
        if choice["kind"] == "operator":
            sc = op_score(choice)
            if sc > best_score:
                best_score = sc
                best_op = choice["id"]

    use_uf = False
    if is_write_sub and best_op is not None and best_score > 0:
        use_uf = True

    result = {}
    for choice in design["choices"]:
        cid = choice["id"]
        kind = choice["kind"]
        if kind == "gpr":
            reg = choice["register"]
            if reg in needed_gprs:
                result[cid] = "keep"
            else:
                result[cid] = "havoc"
        elif kind == "unit":
            keep = False
            parts = choice["instance"].split('.')
            if is_load and is_write_sub and "dcache" in parts:
                keep = True
            elif is_store and "dcache" in parts:
                keep = True
            elif is_csr and "csr_regfile" in parts:
                keep = True
            if keep:
                result[cid] = "keep"
            else:
                result[cid] = "cut"
        elif kind == "operator":
            if use_uf and cid == best_op:
                result[cid] = "uf"
            else:
                result[cid] = "keep"
        else:
            result[cid] = choice["levels"][0]
    return result
