def tokenize(s):
    s = s.lower()
    res = []
    cur = ""
    for c in s:
        if c in "abcdefghijklmnopqrstuvwxyz0123456789":
            cur += c
        else:
            if cur:
                res.append(cur)
                cur = ""
    if cur:
        res.append(cur)
    return res


def get_instr_type(desc):
    toks = tokenize(desc)
    mnemonics = {
        "addi", "slti", "sltiu", "xori", "ori", "andi", "slli", "srli", "srai",
        "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
        "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw",
        "beq", "bne", "blt", "bge", "bltu", "bgeu",
        "jal", "jalr", "lui", "auipc",
        "fence", "ecall", "ebreak",
        "csrrw", "csrrs", "csrrc", "csrrwi", "csrrsi", "csrrci"
    }
    for t in toks:
        if t in mnemonics:
            return t.upper()
    return "UNKNOWN"


def choose(sub, design):
    instr_type = get_instr_type(design.get("description", ""))
    states = sub["states"]
    case_terms = sub["case_terms"]

    loads = {"LB", "LH", "LW", "LBU", "LHU"}
    stores = {"SB", "SH", "SW"}
    branches = {"BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU"}
    jumps = {"JAL", "JALR"}
    alu_imm = {"ADDI", "SLTI", "SLTIU", "XORI", "ORI", "ANDI", "SLLI", "SRLI", "SRAI"}
    alu_reg = {"ADD", "SUB", "SLL", "SLT", "SLTU", "XOR", "SRL", "SRA", "OR", "AND"}
    csr_set = {"CSRRW", "CSRRS", "CSRRC", "CSRRWI", "CSRRSI", "CSRRCI"}

    is_load = instr_type in loads
    is_store = instr_type in stores
    is_branch = instr_type in branches
    is_jump = instr_type in jumps
    is_alu = instr_type in alu_imm or instr_type in alu_reg
    is_csr = instr_type in csr_set
    is_lui = instr_type == "LUI"
    is_auipc = instr_type == "AUIPC"
    is_jal = instr_type == "JAL"
    is_jalr = instr_type == "JALR"

    rd_val = None
    for t in case_terms:
        if t["field"] == "rd" and t["op"] == "==":
            rd_val = t["value"]
            break

    write_back = False
    if rd_val is not None:
        for s in states:
            if s.startswith("x") and s[1:].isdigit():
                if int(s[1:]) == rd_val:
                    write_back = True
                    break

    needed = set()
    for s in states:
        if s.startswith("x") and s[1:].isdigit():
            needed.add(int(s[1:]))

    fixed_ops = set()
    for t in case_terms:
        if t["field"] in design["operand_fields"] and t["op"] == "==":
            fixed_ops.add(t["value"])

    has_pc = "pc" in states
    is_mem = ("load_en" in states) or ("store_en" in states)

    if has_pc:
        if is_branch or is_jalr:
            needed.update(fixed_ops)

    if write_back:
        if rd_val != 0 and (is_alu or is_load):
            needed.update(fixed_ops)

    result = {}

    for c in design["choices"]:
        cid = c["id"]
        kind = c["kind"]
        if kind == "gpr":
            j = c["register"]
            if j in needed:
                result[cid] = "keep"
            else:
                result[cid] = "havoc"
        elif kind == "unit":
            keep = False
            name = c.get("instance", "") + " " + c.get("module", "")
            toks = set(tokenize(name))
            if write_back and is_load:
                if "dcache" in toks:
                    keep = True
            if write_back and is_csr:
                if "csr" in toks:
                    keep = True
            result[cid] = "keep" if keep else "cut"
        elif kind == "operator":
            pass
        else:
            result[cid] = c["levels"][0]

    groups = {}
    for c in design["choices"]:
        if c["kind"] == "operator":
            node = c["ila_node"]
            if node not in groups:
                groups[node] = []
            groups[node].append(c)

    candidates = []
    if not is_mem:
        for node, choices in groups.items():
            best_score = -1000
            best_choice = None
            for c in choices:
                toks = set(tokenize(c.get("rtl_node", "")))
                score = 0
                if has_pc:
                    if "target" in toks: score += 10
                    if "pc" in toks: score += 8
                    if "plus" in toks or "add" in toks: score += 5
                    if "br" in toks or "cond" in toks: score += 6
                    if "eq" in toks or "lt" in toks or "gt" in toks or "ne" in toks or "ge" in toks or "le" in toks: score += 6
                    if "addr" in toks or "eaddr" in toks: score += 2
                    if "rd" in toks and "val" in toks: score -= 5
                if write_back and rd_val != 0:
                    if ("rd" in toks and "val" in toks) or "result" in toks or "wdata" in toks: score += 10
                    if "plus" in toks or "add" in toks: score += 5
                    if "addr" in toks or "eaddr" in toks: score -= 10
                    if "pc" in toks: score -= 5
                    if "target" in toks: score -= 5
                if score > best_score:
                    best_score = score
                    best_choice = c
            if best_choice is not None and best_score > 0:
                candidates.append((best_score, best_choice))

    rtl_best = {}
    for score, c in candidates:
        rtl = c["rtl_node"]
        if rtl not in rtl_best or score > rtl_best[rtl][0]:
            rtl_best[rtl] = (score, c)

    selected_uf = set()
    for rtl, (score, c) in rtl_best.items():
        selected_uf.add(c["id"])

    for c in design["choices"]:
        if c["kind"] == "operator":
            cid = c["id"]
            if cid in selected_uf:
                result[cid] = "uf"
            else:
                result[cid] = "keep"

    return result
