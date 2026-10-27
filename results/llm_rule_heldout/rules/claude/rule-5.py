RV32I = ["LUI", "AUIPC", "JAL", "JALR", "BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU",
         "LB", "LH", "LW", "LBU", "LHU", "SB", "SH", "SW",
         "ADDI", "SLTI", "SLTIU", "XORI", "ORI", "ANDI", "SLLI", "SRLI", "SRAI",
         "ADD", "SUB", "SLL", "SLT", "SLTU", "XOR", "SRL", "SRA", "OR", "AND",
         "FENCE", "ECALL", "EBREAK"]

LOADS = ["LB", "LH", "LW", "LBU", "LHU"]
STORES = ["SB", "SH", "SW"]


def tokens(text):
    out = []
    cur = ""
    for ch in text:
        if ch.isalnum() if hasattr(ch, "isalnum") else False:
            cur = cur + ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def is_alnum(ch):
    return ch.isdigit() or (ch.lower() != ch.upper()) or ch == "_"


def tokenize(text):
    out = []
    cur = ""
    for ch in text:
        if is_alnum(ch):
            cur = cur + ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def mnemonic(design):
    desc = design.get("description", "") or ""
    lines = desc.split("\n")
    # prefer the Benchmark line
    for line in lines:
        toks = tokenize(line)
        if len(toks) > 0 and toks[0] == "Benchmark":
            for t in toks:
                if t.upper() == t and t in RV32I:
                    return t
    for t in tokenize(desc):
        if t in RV32I:
            return t
    return ""


def choose(sub, design):
    instr = mnemonic(design)
    is_mem_instr = (instr in LOADS) or (instr in STORES) or instr.startswith("AMO")
    operand_fields = design.get("operand_fields", []) or []
    states = sub.get("states", []) or []
    terms = sub.get("case_terms", []) or []

    rd_eq = None
    rd_ne = None
    src_regs = set()
    for t in terms:
        f = t.get("field")
        op = t.get("op")
        v = t.get("value")
        if f == "rd":
            if op == "==":
                rd_eq = v
            else:
                rd_ne = v
        elif f in ("rs1", "rs2") and op == "==":
            src_regs.add(int(v))

    state_regs = set()
    for s in states:
        if len(s) > 1 and s[0] == "x" and s[1:].isdigit():
            state_regs.add(int(s[1:]))

    is_frame = rd_ne is not None and rd_eq is None
    is_write = rd_eq is not None
    no_case = len(terms) == 0

    # Which operand fields are fixed by the case
    fixed_fields = set([t.get("field") for t in terms if t.get("op") == "=="])
    unfixed_operands = [f for f in operand_fields if f not in fixed_fields]

    keep_all_gprs = False
    if no_case and len(unfixed_operands) > 0:
        # mem-like sub-property without operand split: keep GPRs only if
        # non-register states may read source registers
        non_x = [s for s in states if not (len(s) > 1 and s[0] == "x" and s[1:].isdigit())]
        if len(non_x) > 0 and (instr == "JALR" or is_mem_instr or instr == ""):
            keep_all_gprs = True
    elif is_write and len(unfixed_operands) > 0:
        keep_all_gprs = True
    elif (not is_frame) and (not is_write) and len(unfixed_operands) > 0:
        keep_all_gprs = True

    result = {}
    for c in design["choices"]:
        cid = c["id"]
        kind = c["kind"]
        levels = c["levels"]
        lvl = levels[0]
        if kind == "unit":
            inst = c.get("instance", "")
            parts = inst.split(".")
            last = parts[-1] if len(parts) > 0 else inst
            if last == "dcache":
                lvl = "keep" if is_mem_instr else "cut"
            elif last == "icache":
                lvl = "keep"
            elif c.get("module", "") == "mkCSR_RegFile":
                lvl = "cut" if is_frame else "keep"
            else:
                lvl = "keep"
        elif kind == "gpr":
            j = int(c.get("register", -1))
            if keep_all_gprs:
                lvl = "keep"
            elif j in src_regs:
                lvl = "keep"
            elif is_frame and j == rd_ne:
                lvl = "keep"
            elif is_write and j == rd_eq:
                lvl = "word" if "word" in levels else "keep"
            elif j in state_regs:
                lvl = "keep"
            else:
                lvl = "havoc" if "havoc" in levels else "keep"
        else:
            lvl = "keep"
        if lvl not in levels:
            lvl = levels[0]
        result[cid] = lvl
    return result
