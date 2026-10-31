"""Replay a BTOR2 witness and compute its dynamic cone of influence.

The witness is simulated frame by frame.  Starting from the violated bad
property in the last frame, the cone follows only the operands that decide
each value: the taken branch of an ite, and one controlling operand of an and
or or.  The result names the free values (inputs and states without a next
function) whose values the violation depends on.
"""
import re

LEAF = {"input", "state", "const", "constd", "consth", "zero", "one", "ones"}


def mask(width):
    return (1 << width) - 1


def signed(value, width):
    return value - (1 << width) if value >> (width - 1) & 1 else value


class Model:
    def __init__(self, path):
        self.nodes = {}
        self.width = {}
        self.sorts = {}
        self.states = []
        self.inputs = []
        self.init = {}
        self.next = {}
        self.bad = []
        self.constraints = []
        self.names = {}
        with open(path) as f:
            for line in f:
                t = line.split(";")[0].split()
                if len(t) < 2 or not t[0].isdigit():
                    continue
                nid, op = int(t[0]), t[1]
                if op == "sort":
                    if t[2] != "bitvec":
                        raise ValueError("array sorts are not supported")
                    self.sorts[nid] = int(t[3])
                    continue
                self.nodes[nid] = (op, t)
                if op in ("bad", "constraint", "fair", "justice", "output"):
                    if op == "bad":
                        self.bad.append(nid)
                    elif op == "constraint":
                        self.constraints.append(nid)
                    continue
                if op in ("init", "next"):
                    target = self.init if op == "init" else self.next
                    target[int(t[3])] = int(t[4])
                    continue
                self.width[nid] = self.sorts[int(t[2])]
                if op == "state":
                    self.states.append(nid)
                elif op == "input":
                    self.inputs.append(nid)
                if op in ("state", "input") and len(t) > 3:
                    self.names[nid] = t[3]
        self.order = [n for n in sorted(self.nodes) if n in self.width]

    def args(self, nid):
        op, t = self.nodes[nid]
        if op in LEAF:
            return []
        if op in ("slice", "sext", "uext"):
            return [int(t[3])]
        return [int(a) for a in t[3:] if re.fullmatch(r"-?\d+", a)][:3]


def parse_witness(path):
    """Return a list of frames, each {"state": {index: value}, "input": {index: value}}."""
    frames = []
    section = None
    with open(path) as f:
        lines = [line.strip() for line in f]
    start = next(i for i, line in enumerate(lines) if line == "sat")
    for line in lines[start + 1:]:
        if not line or line.startswith("b"):
            continue
        if line == ".":
            break
        m = re.fullmatch(r"([#@])(\d+)", line)
        if m:
            k = int(m.group(2))
            while len(frames) <= k:
                frames.append({"state": {}, "input": {}})
            section = frames[k]["state" if m.group(1) == "#" else "input"]
            continue
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"[01]+", parts[1]):
            section[int(parts[0])] = int(parts[1], 2)
    return frames


def evaluate(model, op, t, nid, value):
    w = model.width[nid]

    def v(a):
        a = int(a)
        x = value[abs(a)]
        return (~x) & mask(model.width[abs(a)]) if a < 0 else x

    if op == "const":
        return int(t[3], 2)
    if op == "constd":
        return int(t[3]) & mask(w)
    if op == "consth":
        return int(t[3], 16) & mask(w)
    if op == "zero":
        return 0
    if op == "one":
        return 1
    if op == "ones":
        return mask(w)
    if op in ("sext", "uext"):
        a = int(t[3])
        x, aw = v(a), model.width[abs(a)]
        return (signed(x, aw) & mask(w)) if op == "sext" else x
    if op == "slice":
        return (v(t[3]) >> int(t[5])) & mask(w)
    if op == "not":
        return ~v(t[3]) & mask(w)
    if op in ("inc", "dec", "neg"):
        x = v(t[3])
        return {"inc": x + 1, "dec": x - 1, "neg": -x}[op] & mask(w)
    if op in ("redand", "redor", "redxor"):
        a = int(t[3])
        x, aw = v(a), model.width[abs(a)]
        return int(x == mask(aw)) if op == "redand" else int(x != 0) if op == "redor" else bin(x).count("1") & 1
    if op == "ite":
        return v(t[4]) if v(t[3]) else v(t[5])
    a, b = int(t[3]), int(t[4])
    x, y = v(a), v(b)
    aw = model.width[abs(a)]
    if op == "concat":
        return (x << model.width[abs(b)]) | y
    if op in ("eq", "iff"):
        return int(x == y)
    if op == "neq":
        return int(x != y)
    if op == "implies":
        return int(not x or y)
    if op in ("ugt", "ugte", "ult", "ulte"):
        return int({"ugt": x > y, "ugte": x >= y, "ult": x < y, "ulte": x <= y}[op])
    if op in ("sgt", "sgte", "slt", "slte"):
        sx, sy = signed(x, aw), signed(y, aw)
        return int({"sgt": sx > sy, "sgte": sx >= sy, "slt": sx < sy, "slte": sx <= sy}[op])
    m = mask(w)
    if op == "and":
        return x & y
    if op == "or":
        return x | y
    if op == "xor":
        return x ^ y
    if op == "nand":
        return ~(x & y) & m
    if op == "nor":
        return ~(x | y) & m
    if op == "xnor":
        return ~(x ^ y) & m
    if op == "add":
        return (x + y) & m
    if op == "sub":
        return (x - y) & m
    if op == "mul":
        return (x * y) & m
    if op == "udiv":
        return m if y == 0 else x // y
    if op == "urem":
        return x if y == 0 else x % y
    if op == "sll":
        return (x << y) & m if y < w else 0
    if op == "srl":
        return x >> y if y < w else 0
    if op == "sra":
        return (signed(x, w) >> min(y, w)) & m
    raise ValueError("unsupported operator " + op)


def simulate(model, frames):
    """Return per-frame node values; states take their witness or init value in frame 0."""
    values = []
    state_index = {n: i for i, n in enumerate(model.states)}
    input_index = {n: i for i, n in enumerate(model.inputs)}
    for k, frame in enumerate(frames):
        value = {}
        pending_init = []
        for n in model.states:
            i = state_index[n]
            if k > 0 and n in model.next:
                nxt = model.next[n]
                x = values[k - 1][abs(nxt)]
                value[n] = (~x) & mask(model.width[n]) if nxt < 0 else x
            elif i in frame["state"]:
                value[n] = frame["state"][i]
            elif k == 0 and n in model.init:
                pending_init.append(n)
                value[n] = 0
            else:
                value[n] = 0
        for n in model.inputs:
            value[n] = frame["input"].get(input_index[n], 0)
        for n in model.order:
            op, t = model.nodes[n]
            if op not in ("state", "input"):
                value[n] = evaluate(model, op, t, n, value)
        if pending_init:
            for n in pending_init:
                init = model.init[n]
                value[n] = value[abs(init)] if init > 0 else (~value[-init]) & mask(model.width[n])
            for n in model.order:
                op, t = model.nodes[n]
                if op not in ("state", "input"):
                    value[n] = evaluate(model, op, t, n, value)
        values.append(value)
    return values


def dynamic_coi(model, values, visited=None):
    """Return {(node id, frame)} of the free values that the violated bad property depends on; `visited` (a set)
    receives every (node id, frame) on the way."""
    last = len(values) - 1
    violated = [b for b in model.bad if value_of(values[last], int(model.nodes[b][1][2])) == 1]
    if not violated:
        raise ValueError("the witness does not violate a bad property in its last frame")
    for c in model.constraints:
        for k, frame in enumerate(values):
            if value_of(frame, int(model.nodes[c][1][2])) != 1:
                raise ValueError("the witness violates a constraint in frame {:d}".format(k))
    stack = [(abs(int(model.nodes[violated[0]][1][2])), last)]
    seen = set() if visited is None else visited
    free = set()
    while stack:
        n, k = stack.pop()
        if (n, k) in seen:
            continue
        seen.add((n, k))
        op, t = model.nodes[n]
        if op == "input" or (op == "state" and n not in model.next):
            free.add((n, k))
            continue
        if op == "state":
            if k > 0:
                stack.append((abs(model.next[n]), k - 1))
            elif n in model.init:
                stack.append((abs(model.init[n]), 0))
            else:
                free.add((n, 0))
            continue
        args = model.args(n)
        if op == "ite":
            cond = value_of(values[k], args[0])
            stack.append((abs(args[0]), k))
            stack.append((abs(args[1] if cond else args[2]), k))
            continue
        if op in ("and", "or") and model.width[n] == 1:
            control = 0 if op == "and" else 1
            deciding = [a for a in args if value_of(values[k], a) == control]
            if deciding:
                stack.append((abs(deciding[0]), k))
                continue
        stack.extend((abs(a), k) for a in args)
    return free


def value_of(frame, a):
    return frame[a] if a > 0 else 1 - frame[-a] if frame[-a] in (0, 1) else None


def free_values(model_path, witness_path):
    """Return sorted (name, frame) pairs of the free values that the violation depends on."""
    model = Model(model_path)
    values = simulate(model, parse_witness(witness_path))
    return sorted((model.names.get(n, ""), k) for n, k in dynamic_coi(model, values))


def free_names(model_path, witness_path):
    return {name for name, _ in free_values(model_path, witness_path)}
