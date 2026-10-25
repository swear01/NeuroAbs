"""Choice-level abstraction for the Flute and Piccolo ILA wrappers.

A unit is a module instance.  Each unit has ordered levels: keep, havoc (every
read port of the unit's memories returns a free value) when it holds memories,
and cut (every output of the instance becomes a free value).  Both cuts are
Yosys cutpoints, so every assignment of levels is a sound over-approximation.
The free values are renamed to choice__<id>__<n> so that a counterexample can
be traced back to the units that caused it.  CEGAR asks rIC3 for a verdict on
each abstract model; for a counterexample, Pono's dynamic cone of influence at
the same depth names the units involved, and each moves one level towards keep.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

PROPERTY_REMOVE = {"ila": "sanitycheck", "sanity": "normalassert"}
CHOICE_NAME = re.compile(r"choice__(\w+?)__\d+")
RIC3_KILL_GRACE = 60
MIN_UNIT_BITS = 64
SPLIT_OWN_FRACTION = 0.1


def yosys_bin():
    return os.environ.get("YOSYS_BIN", "yosys")


def pono_bin():
    return os.environ.get("PONO_BIN", "pono")


def run_yosys(lines, log_path):
    with tempfile.NamedTemporaryFile("w", suffix=".ys", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        script = f.name
    try:
        with open(log_path, "w") as log:
            result = subprocess.run([yosys_bin(), "-q", "-s", script], stdout=log, stderr=subprocess.STDOUT)
    finally:
        os.unlink(script)
    if result.returncode != 0:
        raise RuntimeError("Yosys failed; see " + log_path)


def header(wrapper, prop):
    return [
        "read_verilog -formal " + wrapper,
        "hierarchy -check -top wrapper",
        "proc",
        "chformal -assume -early;",
        "select wrapper/" + PROPERTY_REMOVE[prop],
        "chformal -remove",
        "select *",
    ]


def footer(out):
    return [
        "select *",
        "memory",
        "setundef -undriven -expose;",
        "chformal -lower;",
        "sim -clock clk -reset rst -rstlen 1 -n 1 -w wrapper",
        "write_btor -s " + out,
    ]


def hierarchy_json(wrapper, workdir):
    path = os.path.join(workdir, "hierarchy.json")
    run_yosys(["read_verilog -formal " + wrapper, "hierarchy -check -top wrapper", "proc",
               "write_json " + path], os.path.join(workdir, "hierarchy.yosys.log"))
    with open(path) as f:
        return json.load(f)["modules"]


def instance_table(modules):
    """Map each instance path to (parent module, cell name, module type)."""
    table = {}

    def walk(module, path):
        for cell, data in modules[module]["cells"].items():
            if data["type"] not in modules:
                continue
            child = path + "." + cell if path else cell
            table[child] = (module, cell, data["type"])
            walk(data["type"], child)

    walk("wrapper", "")
    return table


def memory_names(wrapper, prop, workdir):
    listing = os.path.join(workdir, "memories.txt")
    run_yosys(header(wrapper, prop) + ["flatten", "memory -nomap", "select -write " + listing + " t:$mem_v2"],
              os.path.join(workdir, "memories.yosys.log"))
    with open(listing) as f:
        return [line.strip().split("/", 1)[1] for line in f if line.strip()]


def read_btor(path):
    """Return (names by node id, next-state ids, sorts, nodes) of a BTOR2 file."""
    nodes, names, nexts, sorts = {}, {}, {}, {}
    with open(path) as f:
        for line in f:
            t = line.split(";")[0].split()
            if len(t) < 2 or not t[0].isdigit():
                continue
            nid = int(t[0])
            nodes[nid] = t
            if t[1] == "sort":
                sorts[t[0]] = int(t[3]) if t[2] == "bitvec" else 0
            elif t[1] in ("state", "input") and len(t) > 3:
                names[nid] = t[3]
            elif t[1] == "next":
                nexts[int(t[3])] = nid
    return names, nexts, sorts, nodes


def coi_state_bits(path):
    """Bits of every named state that has a next function and lies in the cone of influence."""
    names, nexts, sorts, nodes = read_btor(path)
    leaf = {"sort", "input", "state", "const", "constd", "consth", "zero", "one", "ones"}
    roots = [n for n, t in nodes.items() if t[1] in ("bad", "constraint", "fair", "justice")]
    seen, stack = set(), list(roots)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        t = nodes[n]
        if t[1] == "state" and n in nexts:
            stack.append(nexts[n])
        if t[1] in leaf:
            continue
        if t[1] in ("slice", "sext", "uext"):
            args = t[3:4]
        elif t[1] in ("bad", "constraint", "fair", "justice"):
            args = t[2:3]
        else:
            args = t[3:]
        for a in args:
            try:
                v = abs(int(a))
            except ValueError:
                continue
            if v in nodes and nodes[v][1] != "sort":
                stack.append(v)
    return {names.get(n, "<anon>{:d}".format(n)): sorts.get(nodes[n][2], 0)
            for n in seen if nodes[n][1] == "state" and n in nexts}


def under(name, path):
    return name.startswith(path) and name[len(path):len(path) + 1] in (".", "$", "[")


def module_name(type_name):
    parts = type_name.split("\\")
    return parts[1] if type_name.startswith("$paramod") else parts[-1]


def discover_units(wrapper, prop, b0_model, workdir):
    os.makedirs(workdir, exist_ok=True)
    table = instance_table(hierarchy_json(wrapper, workdir))
    memories = memory_names(wrapper, prop, workdir)
    bits = coi_state_bits(b0_model)

    def subtree(path):
        return sum(w for n, w in bits.items() if under(n, path))

    def children(path):
        return [c for c in table if c.startswith(path + ".") and c.count(".") == path.count(".") + 1]

    def expand(path):
        kids = [c for c in children(path) if subtree(c) >= MIN_UNIT_BITS]
        own = subtree(path) - sum(subtree(c) for c in children(path))
        if kids and own < SPLIT_OWN_FRACTION * subtree(path):
            return [u for c in kids for u in expand(c)]
        return [path]

    units = []
    for top in children("RTL"):
        if subtree(top) < MIN_UNIT_BITS:
            continue
        for path in expand(top):
            mems = [m for m in memories if under(m, path)]
            unit_id = re.sub(r"\W+", "_", path.split(".", 1)[1]).strip("_").replace("__", "_")
            units.append({
                "id": unit_id,
                "path": path,
                "module": module_name(table[path][2]),
                "coi_state_bits": subtree(path),
                "memories": [{"name": m, "coi_state_bits": subtree(m)} for m in mems],
                "levels": ["keep", "havoc", "cut"] if mems else ["keep", "cut"],
            })
    return units


def assignment_choices(units, assignment):
    choices = []
    for u in units:
        level = assignment.get(u["id"], "keep")
        if level not in u["levels"]:
            raise ValueError("unit {:s} has no level {:s}".format(u["id"], level))
        if level == "cut":
            choices.append({"id": u["id"], "kind": "module", "target": u["path"], "unit": u["id"]})
        elif level == "havoc":
            for i, m in enumerate(u["memories"]):
                choices.append({"id": "{:s}_m{:d}".format(u["id"], i), "kind": "memory", "target": m["name"],
                                "unit": u["id"]})
    return choices


def cut_lines(choices, table, select_dir, renames):
    """Yosys commands for the cuts; renames maps a select file to its cell renames."""
    module_cuts = [c for c in choices if c["kind"] == "module"]
    memory_cuts = [c for c in choices if c["kind"] == "memory"
                   and not any(under(c["target"], m["target"]) for m in module_cuts)]
    lines = []

    def cut(choice_id, selector):
        listing = os.path.join(select_dir, choice_id + ".txt")
        lines.extend(["select -set before t:$anyseq", "cutpoint " + selector,
                      "select -write " + listing + " t:$anyseq @before %d"])
        for module, old, new in renames.get(listing, []):
            lines.extend(["cd " + module, "rename " + old + " " + new, "cd .."])

    for c in module_cuts:
        module, cell, _ = table[c["target"]]
        cut(c["id"], module + "/" + cell)
    lines.extend(["select *", "flatten", "memory -nomap"])
    for c in memory_cuts:
        cut(c["id"], "wrapper/" + c["target"])
    return lines


def build(wrapper, prop, choices, out, workdir):
    os.makedirs(workdir, exist_ok=True)
    table = instance_table(hierarchy_json(wrapper, workdir)) if any(c["kind"] == "module" for c in choices) else {}
    select_dir = os.path.join(workdir, "cut_cells")
    os.makedirs(select_dir, exist_ok=True)
    for name in os.listdir(select_dir):
        os.unlink(os.path.join(select_dir, name))
    run_yosys(header(wrapper, prop) + cut_lines(choices, table, select_dir, {}) + footer(out), out + ".pass1.log")
    renames = {}
    for c in choices:
        listing = os.path.join(select_dir, c["id"] + ".txt")
        if not os.path.exists(listing):
            continue
        with open(listing) as f:
            cells = [line.strip() for line in f if line.strip()]
        renames[listing] = [(cell.split("/", 1)[0], cell.split("/", 1)[1], "choice__{:s}__{:d}".format(c["id"], i))
                            for i, cell in enumerate(cells)]
    run_yosys(header(wrapper, prop) + cut_lines(choices, table, select_dir, renames) + footer(out), out + ".yosys.log")
    names = read_btor(out)[0]
    return sorted({m.group(1) for name in names.values() for m in [CHOICE_NAME.search(name)] if m})


def ric3_bin():
    return os.environ.get("RIC3_BIN", "rIC3")


def ric3_check(model, time_limit, log_path):
    """Run the rIC3 portfolio and return (verdict, counterexample depth, seconds)."""
    started = time.time()
    with open(log_path, "w") as log:
        process = subprocess.Popen([ric3_bin(), "check", "--ui", "false", "--cex", model, "portfolio",
                                    "--time-limit", str(time_limit)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=time_limit + RIC3_KILL_GRACE)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    elapsed = time.time() - started
    if timed_out:
        return "TIMEOUT", None, elapsed
    with open(log_path) as f:
        lines = [line.strip() for line in f]
    if process.returncode != 0:
        return "ERROR", None, elapsed
    if "UNSAT" in lines:
        return "UNSAT", None, elapsed
    if "SAT" in lines:
        frames = [int(line[1:]) for line in lines if re.fullmatch(r"@\d+", line)]
        return "SAT", max(frames) if frames else None, elapsed
    return "UNKNOWN", None, elapsed


def pono_counterexample(model, workdir, bound, timeout):
    """Run Pono BMC up to bound; return (status, node ids in the counterexample's dynamic COI)."""
    os.makedirs(workdir, exist_ok=True)
    rev = os.path.join(workdir, "coi-check-rev.txt")
    if os.path.exists(rev):
        os.unlink(rev)
    cmd = [pono_bin(), "--bound", str(bound), "--promote-inputvars",
           os.environ.get("PONO_DYNAMIC_COI_FLAG", "--dynamic_coi_up_cex"), model]
    try:
        result = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", set()
    with open(os.path.join(workdir, "pono.out"), "w") as f:
        f.write(result.stdout + result.stderr)
    status = next((s for s in ("sat", "unsat", "unknown") if re.search(r"(?m)^" + s + "$", result.stdout)), None)
    if status is None:
        raise RuntimeError("Pono failed with exit code {:d}; see {:s}".format(result.returncode, workdir))
    ids = set()
    if status == "sat":
        with open(rev) as f:
            for line in f:
                parts = line.split()
                m = re.match(r"(?:state|input)(\d+)@", parts[1]) if len(parts) > 1 else None
                if m:
                    ids.add(int(m.group(1)))
    return status, ids


def cegar(wrapper, prop, units, assignment, workdir, time_limit, max_iterations):
    """rIC3 decides each abstract model; a counterexample is traced to its units with Pono's dynamic COI."""
    assignment = dict(assignment)
    history = []
    status = None
    for iteration in range(max_iterations + 1):
        started = time.time()
        choices = assignment_choices(units, assignment)
        by_choice = {c["id"]: c["unit"] for c in choices}
        model = os.path.join(workdir, "iter{:d}.btor2".format(iteration))
        present = build(wrapper, prop, choices, model, model + ".work")
        build_seconds = time.time() - started
        verdict, depth, ric3_seconds = ric3_check(model, time_limit, model + ".ric3.log")
        record = {
            "iteration": iteration,
            "assignment": {u["id"]: assignment.get(u["id"], "keep") for u in units},
            "model": model,
            "choices_with_free_values": present,
            "coi_state_bits": sum(coi_state_bits(model).values()),
            "ric3": verdict,
            "ric3_seconds": ric3_seconds,
            "cex_depth": depth,
            "build_seconds": build_seconds,
        }
        history.append(record)
        status = verdict
        if verdict != "SAT":
            break
        pono_started = time.time()
        pono, ids = pono_counterexample(model, model + ".pono", depth, time_limit)
        names = read_btor(model)[0]
        cex_choices = sorted({m.group(1) for i in ids for m in [CHOICE_NAME.search(names.get(i, ""))] if m})
        refined = sorted({by_choice[c] for c in cex_choices if c in by_choice})
        record.update({"pono": pono, "pono_seconds": time.time() - pono_started,
                       "counterexample_choices": cex_choices, "refined_units": refined})
        if pono != "sat":
            status = "pono_" + pono
            break
        if not refined:
            status = "real"
            break
        if iteration == max_iterations:
            status = "max_iterations"
            break
        for unit_id in refined:
            levels = next(u["levels"] for u in units if u["id"] == unit_id)
            assignment[unit_id] = levels[levels.index(assignment[unit_id]) - 1]
    total = sum(r["build_seconds"] + r["ric3_seconds"] + r.get("pono_seconds", 0) for r in history)
    return {"status": status, "final_model": history[-1]["model"], "final_assignment": history[-1]["assignment"],
            "refinements": len(history) - 1, "total_seconds": total, "history": history}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    u = sub.add_parser("units", help="list the abstraction units of a wrapper")
    r = sub.add_parser("cegar", help="refine an assignment of unit levels")
    for p in (u, r):
        p.add_argument("--wrapper", required=True)
        p.add_argument("--prop", choices=sorted(PROPERTY_REMOVE), required=True)
        p.add_argument("--workdir", required=True)
    u.add_argument("--b0", required=True, help="concrete BTOR2 model used to size the units")
    r.add_argument("--units", required=True)
    r.add_argument("--assignment", required=True, help="JSON object unit id -> level, or 'coarsest'")
    r.add_argument("--time-limit", type=int, default=3600, help="rIC3 portfolio time limit per model")
    r.add_argument("--max-iterations", type=int, default=20)
    args = parser.parse_args(argv)
    workdir = os.path.abspath(args.workdir)
    wrapper = os.path.abspath(args.wrapper)
    if args.command == "units":
        print(json.dumps(discover_units(wrapper, args.prop, os.path.abspath(args.b0), workdir), indent=2))
        return 0
    with open(args.units) as f:
        units = json.load(f)
    if args.assignment == "coarsest":
        assignment = {x["id"]: x["levels"][-1] for x in units}
    else:
        with open(args.assignment) as f:
            assignment = json.load(f)
    os.makedirs(workdir, exist_ok=True)
    result = cegar(wrapper, args.prop, units, assignment, workdir, args.time_limit, args.max_iterations)
    with open(os.path.join(workdir, "cegar.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "refinements", "total_seconds", "final_assignment")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
