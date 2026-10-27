def choose(sub, design):
    # Extract basic information from the sub-property and the design.
    desc = design.get("description", "")
    desc_up = desc.upper()
    states = sub.get("states", [])
    case_terms = sub.get("case_terms", [])
    operand_fields = design.get("operand_fields", [])

    # Parse the case terms to find constraints on rd and on source operands.
    rd_eq = None
    rd_neq = set()
    fixed_ops = {}
    for term in case_terms:
        f = term.get("field")
        op = term.get("op")
        v = term.get("value")
        if f == "rd":
            if op == "==":
                rd_eq = v
            elif op == "!=":
                rd_neq.add(v)
        if f in operand_fields and op == "==":
            fixed_ops[f] = v

    # Determine whether any compared GPR may be written by the instruction.
    # x0 is hardwired zero and is never actually written.
    target_possible = False
    for s in states:
        if s.startswith("x") and s[1:].isdigit():
            j = int(s[1:])
            if j == 0:
                continue
            if rd_eq == j:
                target_possible = True
            elif rd_eq is None and j not in rd_neq:
                target_possible = True

    # If a written GPR is compared, we need the source operands that feed it.
    # If an operand field is not fixed by the case, keep all GPRs to be safe.
    needed_sources = set()
    if target_possible:
        all_needed = False
        for f in operand_fields:
            if f in fixed_ops:
                needed_sources.add(fixed_ops[f])
            else:
                all_needed = True
        if all_needed:
            for c in design.get("choices", []):
                if c.get("kind") == "gpr":
                    needed_sources.add(c.get("register"))

    # Build the abstraction choice for every choice id.
    result = {}
    for c in design.get("choices", []):
        cid = c.get("id")
        kind = c.get("kind")

        if kind == "unit":
            inst = c.get("instance", "").lower()
            module = c.get("module", "").lower()
            text = " ".join(sub.get("assertion", [])) + " " + " ".join(states)
            low = text.lower()

            if "csr_regfile" in inst or "csr_regfile" in module:
                # CSR is needed only for CSR/system/trap instructions or
                # when CSR signals appear in the compared/asserted text.
                if ("CSR" in desc_up or "SYSTEM" in desc_up or "TRAP" in desc_up or
                    "csr" in low or "mstatus" in low or "mepc" in low):
                    result[cid] = "keep"
                else:
                    result[cid] = "cut"

            elif "dcache" in inst or "dcache" in module:
                # Data cache matters only for loads/stores/atomics or when
                # data-cache signals appear in the compared/asserted text.
                if ("LOAD" in desc_up or "STORE" in desc_up or "AMO" in desc_up or
                    "LR" in desc_up or "SC" in desc_up or "dcache" in low or
                    "load_data" in low or "store_data" in low or "mem_master" in low):
                    result[cid] = "keep"
                else:
                    result[cid] = "cut"

            elif "icache" in inst or "icache" in module:
                # Instruction cache matters for pc comparison and for
                # pc-relative/control-flow instructions.
                if ("pc" in low or "imem" in low or "JAL" in desc_up or
                    "JALR" in desc_up or "BRANCH" in desc_up or "AUIPC" in desc_up):
                    result[cid] = "keep"
                else:
                    result[cid] = "cut"
            else:
                # Unknown unit: keep it to be safe.
                result[cid] = "keep"

        elif kind == "gpr":
            j = c.get("register")
            state_name = "x" + str(j)
            if state_name in states or j in needed_sources:
                # A compared register, or a source that feeds a compared
                # written register, must keep its full state and assumptions.
                result[cid] = "keep"
            else:
                # Not compared and not needed as a source: make it havoc.
                result[cid] = "havoc"

        elif kind == "operator":
            # For pure arithmetic instructions, uf is enough because all
            # assertions are equalities and the source GPRs are kept.
            arith = False
            for m in ["ADDI", "ADD", "SUB", "AND", "OR", "XOR", "SLT", "SLTU",
                      "SLL", "SRL", "SRA", "SLLI", "SRLI", "SRAI"]:
                if m in desc_up:
                    arith = True
                    break
            if arith and "uf" in c.get("levels", []):
                result[cid] = "uf"
            else:
                # Conservative choice for non-arithmetic instructions.
                result[cid] = "keep"

        else:
            # Fallback: pick the first available level.
            levels = c.get("levels", ["keep"])
            result[cid] = levels[0]

    return result
