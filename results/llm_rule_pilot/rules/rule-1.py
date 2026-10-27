def get_eq(terms, field):
    for t in terms:
        if t.get("field") == field and t.get("op") == "==":
            return t.get("value")
    return None


def get_neq(terms, field):
    vals = set()
    for t in terms:
        if t.get("field") == field and t.get("op") == "!=":
            vals.add(t.get("value"))
    return vals


def gpr_levels(sub, design):
    states = sub.get("states", [])
    terms = sub.get("case_terms", [])
    operand_fields = design.get("operand_fields", [])
    rd_eq = get_eq(terms, "rd")
    rd_neq = get_neq(terms, "rd")
    keep = set()
    word = set()
    all_keep = False
    for j in range(32):
        if ("x" + str(j)) not in states:
            continue
        possibly_written = True
        possibly_not_written = True
        if rd_eq is not None:
            if rd_eq == j:
                possibly_not_written = False
            else:
                possibly_written = False
        if j in rd_neq:
            possibly_written = False
        if possibly_not_written:
            keep.add(j)
        if possibly_written:
            if j == 0:
                keep.add(0)
            else:
                for f in operand_fields:
                    f_eq = get_eq(terms, f)
                    if f_eq is not None:
                        keep.add(f_eq)
                    else:
                        all_keep = True
                if rd_eq == j and not all_keep and j not in keep:
                    word.add(j)
    levels = {}
    for j in range(32):
        if all_keep or j in keep:
            levels[j] = "keep"
        elif j in word:
            levels[j] = "word"
        else:
            levels[j] = "havoc"
    return levels


def unit_needed(unit, sub, design):
    assertions = sub.get("assertion", [])
    inst = unit.get("instance", "")
    prefix = inst.replace(".", "__DOT__")
    for a in assertions:
        if prefix in a:
            return True
    for out in unit.get("outputs", []):
        base = out.split("[")[0]
        if len(base) >= 6:
            for a in assertions:
                if base in a:
                    return True
    desc = design.get("description", "").upper()
    cid = unit.get("id", "")
    mod = unit.get("module", "").upper()
    if ("CSR" in desc or "TRAP" in desc or "ECALL" in desc or
            "EBREAK" in desc or "MRET" in desc or "WFI" in desc or
            "INTERRUPT" in desc):
        if "csr" in cid.lower() or "CSR" in mod:
            return True
    if ("LOAD" in desc or "STORE" in desc or "LW" in desc or
            "SW" in desc or "LD" in desc or "SD" in desc or
            "LB" in desc or "SB" in desc or "LH" in desc or
            "SH" in desc):
        if "dcache" in cid.lower():
            return True
    return False


def choose(sub, design):
    gprs = gpr_levels(sub, design)
    result = {}
    for choice in design["choices"]:
        cid = choice["id"]
        kind = choice["kind"]
        if kind == "gpr":
            j = choice["register"]
            result[cid] = gprs.get(j, "havoc")
        elif kind == "unit":
            if unit_needed(choice, sub, design):
                result[cid] = "keep"
            else:
                result[cid] = "cut"
        elif kind == "operator":
            result[cid] = "uf"
        else:
            result[cid] = choice["levels"][0]
    return result
