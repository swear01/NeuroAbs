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


def choose(sub, design):
    states = sub.get("states", [])
    case_terms = sub.get("case_terms", [])

    all_tokens = set()
    for s in states:
        all_tokens.update(tokens_of(s))
    for a in sub.get("assertion", []):
        all_tokens.update(tokens_of(a))

    state_gprs = set()
    for s in states:
        j = gpr_index(s)
        if j >= 0:
            state_gprs.add(j)

    fixed = {}
    write_k = None
    for t in case_terms:
        if t.get("op") == "==":
            fixed[t.get("field")] = t.get("value")
            if t.get("field") == "rd":
                write_k = t.get("value")

    source_regs = set()
    for f in design.get("operand_fields", []):
        if f in fixed:
            source_regs.add(fixed[f])

    is_frame = (len(case_terms) == 1 and
                case_terms[0].get("field") == "rd" and
                case_terms[0].get("op") == "!=")

    desc_toks = set(tokens_of(design.get("description", "")))
    is_load_insn = contains_any(desc_toks, ["lb", "lh", "lw", "lbu", "lhu", "load"])
    is_store_insn = contains_any(desc_toks, ["sb", "sh", "sw", "store"])
    is_mem_insn = is_load_insn or is_store_insn

    res = {}

    for ch in design.get("choices", []):
        cid = ch.get("id")
        kind = ch.get("kind")

        if kind == "gpr":
            j = ch.get("register")
            if write_k is not None:
                # Write sub-property: keep every GPR so that no havoc'd
                # register turns up as an unconstrained value in a spurious
                # counterexample (and gets refined away).
                res[cid] = "keep"
            else:
                if j == 0 or j in state_gprs or j in source_regs:
                    res[cid] = "keep"
                else:
                    res[cid] = "havoc"

        elif kind == "unit":
            inst_toks = set(tokens_of(ch.get("instance", "")))
            inst_toks.update(tokens_of(ch.get("module", "")))

            if "icache" in inst_toks:
                # Instruction source / pc. Needed by mem and write sub-props.
                if is_frame:
                    res[cid] = "cut"
                else:
                    res[cid] = "keep"
            elif "csr" in inst_toks:
                res[cid] = "cut"
            elif "dcache" in inst_toks:
                if is_mem_insn:
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"
            else:
                if inst_toks.intersection(all_tokens):
                    res[cid] = "keep"
                else:
                    res[cid] = "cut"

        else:
            # Keep every operator exact: no uf over-approximation, so
            # no operator-side refinements are needed.
            res[cid] = "keep"

    return res
