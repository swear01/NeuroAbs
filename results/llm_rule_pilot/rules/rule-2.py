def choose(sub, design):
    # Build a combined lower-case string of the sub-property assertions and states
    parts = []
    for s in sub.get("assertion", []):
        parts.append(s)
    for s in sub.get("states", []):
        parts.append(s)
    combined = " ".join(parts).lower()

    desc = design.get("description", "").upper()

    # Instruction type detection from the design description
    is_branch = False
    for kw in ["BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU", "JAL", "JALR", "BRANCH", "JUMP"]:
        if desc.count(kw) > 0:
            is_branch = True

    is_load = False
    for kw in ["LOAD", "LW", "LH", "LB", "LBU", "LHU"]:
        if desc.count(kw) > 0:
            is_load = True

    is_store = False
    for kw in ["STORE", "SW", "SH", "SB"]:
        if desc.count(kw) > 0:
            is_store = True

    is_csr = False
    if desc.count("CSR") > 0:
        is_csr = True

    # Start with every GPR that appears directly in the compared states
    needed_gprs = set()
    for st in sub.get("states", []):
        st_low = st.lower()
        if st_low.startswith("x"):
            rest = st_low[1:]
            if rest.isdigit():
                needed_gprs.add(int(rest))

    # Is a non-zero GPR in the states a destination that may actually be written?
    computed_gpr = False
    for st in sub.get("states", []):
        st_low = st.lower()
        if st_low.startswith("x"):
            rest = st_low[1:]
            if rest.isdigit():
                j = int(rest)
                if j == 0:
                    continue
                excluded = False
                for term in sub.get("case_terms", []):
                    if term.get("field") == "rd" and term.get("op") == "!=" and term.get("value") == j:
                        excluded = True
                if not excluded:
                    computed_gpr = True

    # Does the property depend on data-flow values (not just frame/control)?
    data_dependent = computed_gpr
    for st in sub.get("states", []):
        st_low = st.lower()
        if (st_low.count("data") > 0 or st_low.count("addr") > 0 or
                st_low.count("val") > 0 or st_low.count("result") > 0 or
                st_low.count("target") > 0):
            data_dependent = True

    pc_in_states = False
    for st in sub.get("states", []):
        if st.lower() == "pc":
            pc_in_states = True
    if pc_in_states and is_branch:
        data_dependent = True

    # If the property depends on data-flow, source operand GPRs are relevant.
    operand_fields = design.get("operand_fields", [])
    if data_dependent:
        for field in operand_fields:
            found_eq = False
            eq_val = None
            for term in sub.get("case_terms", []):
                if term.get("field") == field:
                    if term.get("op") == "==":
                        val = term.get("value")
                        if val is not None:
                            found_eq = True
                            eq_val = val
            if found_eq:
                needed_gprs.add(eq_val)
            else:
                # Operand is unconstrained (or only excluded by !=): keep all
                for j in range(32):
                    needed_gprs.add(j)

    # Keywords used to decide whether an operator is relevant to the property
    op_keywords = []
    for f in operand_fields:
        op_keywords.append(f.lower())
    for kw in ["pc", "imm", "rd", "rs1", "rs2", "target", "next", "addr", "data", "val", "result"]:
        op_keywords.append(kw)

    # Precompute whether any operator expression matches a relevant keyword
    any_op_match = False
    if data_dependent:
        for choice in design.get("choices", []):
            if choice.get("kind") == "operator":
                expr_list = []
                for e in choice.get("ila_expr", []):
                    expr_list.append(str(e))
                for e in choice.get("rtl_expr", []):
                    expr_list.append(str(e))
                expr_str = " ".join(expr_list).lower()
                for kw in op_keywords:
                    if kw and expr_str.count(kw) > 0:
                        any_op_match = True
                        break
            if any_op_match:
                break

    result = {}
    for choice in design.get("choices", []):
        cid = choice.get("id")
        kind = choice.get("kind")
        levels = choice.get("levels", [])
        if not levels:
            levels = ["keep"]

        if kind == "unit":
            keep = False
            instance = choice.get("instance", "")
            parts_inst = instance.split(".")
            inst_last = ""
            if len(parts_inst) > 0:
                inst_last = parts_inst[-1].lower()
            module = choice.get("module", "").lower()

            if inst_last and combined.count(inst_last) > 0:
                keep = True
            if module and combined.count(module) > 0:
                keep = True

            if not keep:
                if is_csr and cid.lower().count("csr") > 0 and data_dependent:
                    keep = True
                if (is_load or is_store) and cid.lower().count("dcache") > 0 and data_dependent:
                    keep = True
                if cid.lower().count("icache") > 0 and (combined.count("icache") > 0 or desc.count("ICACHE") > 0):
                    keep = True

            if keep:
                level = "keep" if "keep" in levels else levels[0]
            else:
                level = "cut" if "cut" in levels else levels[0]
            result[cid] = level

        elif kind == "gpr":
            reg = choice.get("register")
            level = "keep" if reg in needed_gprs else "havoc"
            if level not in levels:
                if level == "havoc" and "word" in levels:
                    level = "word"
                elif "keep" in levels:
                    level = "keep"
                else:
                    level = levels[0]
            result[cid] = level

        elif kind == "operator":
            level = "uf"
            if data_dependent:
                if any_op_match:
                    expr_list = []
                    for e in choice.get("ila_expr", []):
                        expr_list.append(str(e))
                    for e in choice.get("rtl_expr", []):
                        expr_list.append(str(e))
                    expr_str = " ".join(expr_list).lower()
                    matched = False
                    for kw in op_keywords:
                        if kw and expr_str.count(kw) > 0:
                            matched = True
                            break
                    level = "keep" if matched else "uf"
                else:
                    level = "keep"
            if level not in levels:
                if level == "uf" and "keep" in levels:
                    level = "keep"
                else:
                    level = levels[0]
            result[cid] = level

        else:
            result[cid] = levels[0] if levels else "keep"

    return result
