def tokens_desc(text):
    s = text.lower()
    for ch in [":", "/", ".", ",", "\n", "\t", "(", ")", "[", "]", ";", "\"", "'"]:
        s = s.replace(ch, " ")
    return s.split()


def tokens_ident(text):
    s = text.lower()
    for ch in [".", "_", "$", "[", "]", "(", ")", ":", "/", "\\", "-", ">", "<", "=", "+", "*", "{", "}", " ", "\t", "\n", ",", ";"]:
        s = s.replace(ch, " ")
    return s.split()


def instr_mnemonic(design):
    toks = tokens_desc(design.get("description", ""))
    mnems = [
        "addi", "add", "sub", "and", "or", "xor", "sll", "srl", "sra",
        "slt", "sltu", "lui", "auipc", "jal", "jalr",
        "beq", "bne", "blt", "bge", "bltu", "bgeu",
        "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw",
        "fence", "ecall", "ebreak"
    ]
    for t in toks:
        for m in mnems:
            if t == m:
                return m
    return ""


def instr_kind(design):
    m = instr_mnemonic(design)
    if m in ["lb", "lh", "lw", "lbu", "lhu"]:
        return "load"
    if m in ["sb", "sh", "sw"]:
        return "store"
    if m in ["beq", "bne", "blt", "bge", "bltu", "bgeu"]:
        return "branch"
    if m in ["jal", "jalr"]:
        return "jump"
    if m in ["ecall", "ebreak"]:
        return "system"
    if m == "fence":
        return "misc"
    if m != "":
        return "alu"
    return "unknown"


def has_state(sub, name):
    for s in sub.get("states", []):
        if s == name:
            return True
    return False


def effective_write_reg(sub):
    rd_eq = None
    for term in sub.get("case_terms", []):
        if term.get("field") == "rd" and term.get("op") == "==":
            rd_eq = term.get("value")
    if rd_eq is None:
        return None
    if rd_eq == 0:
        return None
    for s in sub.get("states", []):
        if s.startswith("x") and s[1:].isdigit():
            if int(s[1:]) == rd_eq:
                return rd_eq
    return None


def needs_sources(kind, sub, write_reg):
    if kind == "store":
        return False
    if kind == "load":
        return write_reg is not None and write_reg != 0
    if kind == "branch":
        return has_state(sub, "pc")
    if kind == "jump":
        return has_state(sub, "pc")
    if kind in ["system", "misc"]:
        return False
    if write_reg is not None and write_reg != 0:
        return True
    return False


def unit_level(choice, kind, need_dcache):
    toks = tokens_ident(choice.get("id", "") + " " + choice.get("instance", ""))
    if "csr" in toks:
        if kind == "system":
            return "keep"
        return "cut"
    if "icache" in toks:
        return "cut"
    if "dcache" in toks:
        if need_dcache:
            return "keep"
        return "cut"
    return "keep"


def operator_score(choice, rel):
    toks = tokens_ident(choice.get("rtl_node", ""))
    score = -1000
    if rel == "result":
        ok = ("rd" in toks) or ("val" in toks) or ("result" in toks) or ("alu" in toks)
        if ok:
            score = 0
            if "rd" in toks:
                score = score + 5
            if "val" in toks:
                score = score + 5
            if "result" in toks:
                score = score + 4
            if "alu" in toks:
                score = score + 1
            if "addr" in toks:
                score = score - 8
            if "eaddr" in toks:
                score = score - 8
            if "pc" in toks:
                score = score - 5
            if "target" in toks:
                score = score - 5
    elif rel == "address":
        ok = ("addr" in toks) or ("eaddr" in toks) or ("address" in toks)
        if ok:
            score = 0
            if "eaddr" in toks:
                score = score + 7
            if "address" in toks:
                score = score + 6
            if "addr" in toks:
                score = score + 5
            if "mem" in toks:
                score = score + 2
            if "load" in toks:
                score = score + 2
            if "store" in toks:
                score = score + 2
            if "rd" in toks:
                score = score - 3
            if "val" in toks:
                score = score - 3
    elif rel == "target":
        ok = ("pc" in toks) or ("target" in toks) or ("next" in toks) or ("jump" in toks) or ("branch" in toks)
        if ok:
            score = 0
            if "pc" in toks:
                score = score + 7
            if "target" in toks:
                score = score + 6
            if "next" in toks:
                score = score + 4
            if "jump" in toks:
                score = score + 3
            if "branch" in toks:
                score = score + 3
            if "addr" in toks:
                score = score + 2
            if "eaddr" in toks:
                score = score + 2
            if "rd" in toks:
                score = score - 2
            if "val" in toks:
                score = score - 2
    return score


def choose_operator(design, sub, kind, write_reg):
    if kind == "load" and write_reg is not None and write_reg != 0:
        rel = "address"
    elif kind == "store":
        rel = ""
    elif kind == "jump":
        m = instr_mnemonic(design)
        if has_state(sub, "pc"):
            if m == "jalr":
                rel = "address"
            else:
                rel = "target"
        elif write_reg is not None and write_reg != 0:
            rel = "result"
        else:
            rel = ""
    elif kind == "branch":
        if has_state(sub, "pc"):
            rel = "target"
        else:
            rel = ""
    elif kind in ["system", "misc"]:
        rel = ""
    else:
        if write_reg is not None and write_reg != 0:
            rel = "result"
        else:
            rel = ""

    if rel == "":
        return ""

    best_id = ""
    best_score = -1000
    for ch in design.get("choices", []):
        if ch.get("kind") != "operator":
            continue
        if "uf" not in ch.get("levels", []):
            continue
        score = operator_score(ch, rel)
        if score > best_score:
            best_score = score
            best_id = ch.get("id", "")
    if best_score <= 0:
        return ""
    return best_id


def choose(sub, design):
    kind = instr_kind(design)
    write_reg = effective_write_reg(sub)
    state_regs = set()
    for s in sub.get("states", []):
        if s.startswith("x") and s[1:].isdigit():
            state_regs.add(int(s[1:]))

    relevant_gprs = set()
    for r in state_regs:
        relevant_gprs.add(r)

    if needs_sources(kind, sub, write_reg):
        for term in sub.get("case_terms", []):
            if term.get("op") == "==" and term.get("field") in design.get("operand_fields", []):
                relevant_gprs.add(term.get("value"))

    need_dcache = False
    if kind == "load" and write_reg is not None and write_reg != 0:
        need_dcache = True

    selected_operator = choose_operator(design, sub, kind, write_reg)

    levels = {}
    for ch in design.get("choices", []):
        cid = ch.get("id", "")
        ckind = ch.get("kind", "")
        if ckind == "unit":
            levels[cid] = unit_level(ch, kind, need_dcache)
        elif ckind == "gpr":
            r = ch.get("register")
            if r in relevant_gprs:
                levels[cid] = "keep"
            else:
                levels[cid] = "havoc"
        elif ckind == "operator":
            if cid == selected_operator:
                levels[cid] = "uf"
            else:
                levels[cid] = "keep"
    return levels
