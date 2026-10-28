def choose(sub, design):
    # Tokenize the description into whole words.
    desc = design["description"].upper()
    for ch in [':', '/', '.', ',', '\n', '\t', '(', ')', '[', ']', '{', '}', ';', '\\', '"', "'"]:
        desc = desc.replace(ch, ' ')
    tokens = desc.split()
    token_set = set(tokens)

    # Classify the instruction from whole tokens.
    is_load = False
    is_store = False
    is_branch = False
    is_csr = False
    load_tokens = set(["LOAD", "LW", "LH", "LB", "LHU", "LBU", "LR"])
    store_tokens = set(["STORE", "SW", "SH", "SB", "SC"])
    branch_tokens = set(["BRANCH", "BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU", "JAL", "JALR"])
    csr_tokens = set(["CSRRW", "CSRRS", "CSRRC", "CSRRWI", "CSRRSI", "CSRRCI"])
    for t in token_set:
        if t in load_tokens:
            is_load = True
        if t in store_tokens:
            is_store = True
        if t in branch_tokens:
            is_branch = True
        if t in csr_tokens or t.startswith("CSR"):
            is_csr = True

    # Determine which GPRs must be kept.
    needed_gprs = set()
    is_write_sub = False
    for state in sub["states"]:
        if state.startswith("x") and state[1:].isdigit():
            num = int(state[1:])
            needed_gprs.add(num)
            if num > 0:
                for term in sub["case_terms"]:
                    if term["field"] == "rd" and term["op"] == "==" and term["value"] == num:
                        is_write_sub = True
                        break
        elif state == "pc":
            if is_branch:
                for term in sub["case_terms"]:
                    if term["field"] in design["operand_fields"] and term["op"] == "==":
                        needed_gprs.add(term["value"])
        elif state in ("load_en", "store_en"):
            pass
        else:
            for term in sub["case_terms"]:
                if term["field"] in design["operand_fields"] and term["op"] == "==":
                    needed_gprs.add(term["value"])

    if is_write_sub:
        for term in sub["case_terms"]:
            if term["field"] in design["operand_fields"] and term["op"] == "==":
                needed_gprs.add(term["value"])

    # Build the level mapping.
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
            instance = choice["instance"]
            parts = instance.split('.')
            if is_load and is_write_sub and "dcache" in parts:
                keep = True
            elif is_csr and is_write_sub and "csr_regfile" in parts:
                keep = True
            if keep:
                result[cid] = "keep"
            else:
                result[cid] = "cut"
        elif kind == "operator":
            result[cid] = "keep"
        else:
            result[cid] = choice["levels"][0]
    return result
