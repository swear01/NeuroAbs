"""Choice-level abstraction for the Flute and Piccolo ILA wrappers.

A unit is a module instance.  Each unit has ordered levels: keep, havoc (every
read port of the unit's memories returns a free value) when it holds memories,
and cut (every output of the instance becomes a free value).  Both cuts are
Yosys cutpoints, so every assignment of levels is a sound over-approximation.
The free values are renamed to choice__<id>__<n> so that a counterexample can
be traced back to the units that caused it.  CEGAR asks rIC3 for a verdict on
each abstract model; a counterexample is replayed, its dynamic cone of
influence names the units involved, and each moves one level towards keep.
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

import btor_witness

PROPERTY_REMOVE = {"ila": "sanitycheck", "sanity": "normalassert"}
CHOICE_NAME = re.compile(r"choice__(\w+?)__\d+")
RIC3_KILL_GRACE = 60
MIN_UNIT_BITS = 64
SPLIT_OWN_FRACTION = 0.1


def yosys_bin():
    return os.environ.get("YOSYS_BIN", "yosys")


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
    renames = cut_renames(choices, select_dir)
    run_yosys(header(wrapper, prop) + cut_lines(choices, table, select_dir, renames) + footer(out), out + ".yosys.log")
    names = read_btor(out)[0]
    return sorted({m.group(1) for name in names.values() for m in [CHOICE_NAME.search(name)] if m})


def cut_renames(choices, select_dir):
    renames = {}
    for c in choices:
        listing = os.path.join(select_dir, c["id"] + ".txt")
        if not os.path.exists(listing):
            continue
        with open(listing) as f:
            cells = [line.strip() for line in f if line.strip()]
        renames[listing] = [(cell.split("/", 1)[0], cell.split("/", 1)[1], "choice__{:s}__{:d}".format(c["id"], i))
                            for i, cell in enumerate(cells)]
    return renames


def free_value_signals(wrapper, prop, choices, workdir):
    """Map each choice__<id>__<n> of a model built by build() in workdir to the net it drives."""
    table = instance_table(hierarchy_json(wrapper, workdir)) if any(c["kind"] == "module" for c in choices) else {}
    select_dir = os.path.join(workdir, "cut_cells")
    signal_dir = os.path.join(workdir, "signals")
    os.makedirs(signal_dir, exist_ok=True)
    for name in os.listdir(signal_dir):
        os.unlink(os.path.join(signal_dir, name))
    renames = cut_renames(choices, select_dir)
    names = [new for cells in renames.values() for _, _, new in cells]
    lines = header(wrapper, prop) + cut_lines(choices, table, select_dir, renames) + ["opt_clean"]
    lines.extend("select -write {:s} wrapper/*{:s} %co:+[Y] w:* %i".format(os.path.join(signal_dir, n + ".txt"), n)
                 for n in names)
    run_yosys(lines, os.path.join(workdir, "signals.yosys.log"))
    signals = {}
    for n in names:
        with open(os.path.join(signal_dir, n + ".txt")) as f:
            wires = sorted(line.strip().split("/", 1)[1] for line in f if line.strip())
        public = [w for w in wires if not w.startswith("$")]
        signals[n] = (public or wires or [n])[0]
    return signals


def ric3_bin():
    return os.environ.get("RIC3_BIN", "rIC3")


def run_ric3(args, time_limit, log_path):
    """Run rIC3 and return (output lines, return code, timed out, seconds)."""
    started = time.time()
    with open(log_path, "w") as log:
        process = subprocess.Popen([ric3_bin(), "check", "--ui", "false"] + args,
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
    with open(log_path) as f:
        lines = [line.strip() for line in f]
    return lines, process.returncode, timed_out, time.time() - started


def ric3_check(model, time_limit, log_path):
    """Run the rIC3 portfolio and return (verdict, counterexample depth, seconds)."""
    lines, returncode, timed_out, elapsed = run_ric3(["--cex", model, "portfolio", "--time-limit", str(time_limit)],
                                                     time_limit, log_path)
    if timed_out:
        return "TIMEOUT", None, elapsed
    if "UNSAT" not in lines and "SAT" not in lines and elapsed >= time_limit:
        # With --cex, rIC3 panics instead of printing UNKNOWN when the time limit is reached.
        return "TIMEOUT", None, elapsed
    if returncode != 0:
        return "ERROR", None, elapsed
    if "UNSAT" in lines:
        return "UNSAT", None, elapsed
    if "SAT" in lines:
        frames = [int(line[1:]) for line in lines if re.fullmatch(r"@\d+", line)]
        return "SAT", max(frames) if frames else None, elapsed
    return "UNKNOWN", None, elapsed


def ric3_bmc(model, bound, time_limit, log_path):
    """Run rIC3 BMC up to bound and return (verdict, counterexample depth, seconds).

    The verdict is SAT, NONE (no counterexample up to the bound), TIMEOUT or ERROR.
    """
    lines, returncode, timed_out, elapsed = run_ric3([model, "bmc", "--end", str(bound), "--time-limit",
                                                      str(time_limit)], time_limit, log_path)
    if timed_out:
        return "TIMEOUT", None, elapsed
    if returncode != 0:
        return "ERROR", None, elapsed
    if "SAT" in lines:
        depths = [int(m.group(1)) for line in lines for m in [re.search(r"counterexample at depth (\d+)", line)] if m]
        return "SAT", depths[0] if depths else None, elapsed
    if any("reached bound {:d}".format(bound) in line for line in lines):
        return "NONE", None, elapsed
    return "TIMEOUT", None, elapsed


def assignment_key(units, assignment):
    return "+".join("{:s}={:s}".format(u["id"], assignment.get(u["id"], "keep")) for u in units)


def stored(path, compute):
    """Return the JSON stored at path, or compute, store and return it; cached is set on reuse."""
    if os.path.exists(path):
        with open(path) as f:
            return dict(json.load(f), cached=True)
    result = compute()
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    return dict(result, cached=False)


def abstract_model(wrapper, prop, units, assignment, models_dir):
    """Build the model of an assignment once per models_dir; its measured build time is kept with it."""
    directory = os.path.join(models_dir, assignment_key(units, assignment))
    os.makedirs(directory, exist_ok=True)
    model = os.path.join(directory, "model.btor2")

    def compute():
        started = time.time()
        present = build(wrapper, prop, assignment_choices(units, assignment), model, model + ".work")
        return {"model": model, "choices_with_free_values": present, "build_seconds": time.time() - started,
                "coi_state_bits": sum(coi_state_bits(model).values())}

    return stored(os.path.join(directory, "build.json"), compute)


def portfolio_verdict(info, time_limit):
    log = "{:s}.ric3-{:d}.log".format(info["model"], time_limit)

    def compute():
        verdict, depth, seconds = ric3_check(info["model"], time_limit, log)
        return {"ric3": verdict, "cex_depth": depth, "ric3_seconds": seconds, "log": log}

    return stored("{:s}.ric3-{:d}.json".format(info["model"], time_limit), compute)


def bmc_verdict(info, bound, time_limit):
    log = "{:s}.bmc{:d}-{:d}.log".format(info["model"], bound, time_limit)

    def compute():
        verdict, depth, seconds = ric3_bmc(info["model"], bound, time_limit, log)
        return {"bmc": verdict, "cex_depth": depth, "bmc_seconds": seconds, "log": log}

    return stored("{:s}.bmc{:d}-{:d}.json".format(info["model"], bound, time_limit), compute)


def refine_all(context):
    return {"refined": sorted(context["counts"]), "seconds": 0.0}


def refine_one(context):
    counts = context["counts"]
    return {"refined": [min(counts, key=lambda unit_id: (-counts[unit_id], unit_id))], "seconds": 0.0}


REFINERS = {"all": refine_all, "one": refine_one}


def finer(units, assignment, unit_id):
    levels = next(u["levels"] for u in units if u["id"] == unit_id)
    return dict(assignment, **{unit_id: levels[levels.index(assignment[unit_id]) - 1]})


def cegar(wrapper, prop, units, assignment, workdir, time_limit, max_iterations, refine=refine_all, models_dir=None):
    """rIC3 decides each abstract model; its counterexample is replayed to find the units it depends on.

    refine(context) picks the units of the counterexample that move one level towards keep; it returns
    {"refined": [unit ids], "seconds": selection cost, ...}.  Models and rIC3 verdicts are stored per
    assignment in models_dir and reused with their measured times.
    """
    models_dir = models_dir or os.path.join(workdir, "models")
    assignment = {u["id"]: assignment.get(u["id"], "keep") for u in units}
    history = []
    status = None
    for iteration in range(max_iterations + 1):
        choices = assignment_choices(units, assignment)
        by_choice = {c["id"]: c["unit"] for c in choices}
        info = abstract_model(wrapper, prop, units, assignment, models_dir)
        check = portfolio_verdict(info, time_limit)
        record = {
            "iteration": iteration,
            "assignment": dict(assignment),
            "model": info["model"],
            "choices_with_free_values": info["choices_with_free_values"],
            "coi_state_bits": info["coi_state_bits"],
            "ric3": check["ric3"],
            "ric3_seconds": check["ric3_seconds"],
            "cex_depth": check["cex_depth"],
            "build_seconds": info["build_seconds"],
            "reused": check["cached"],
        }
        history.append(record)
        status = check["ric3"]
        if status != "SAT":
            break
        replay_started = time.time()
        counterexample = []
        for name, frame in btor_witness.free_values(info["model"], check["log"]):
            m = CHOICE_NAME.search(name)
            if m and m.group(1) in by_choice:
                counterexample.append({"unit": by_choice[m.group(1)], "name": m.group(0), "frame": frame})
        counts = {}
        for value in counterexample:
            counts[value["unit"]] = counts.get(value["unit"], 0) + 1
        record.update({"replay_seconds": time.time() - replay_started, "counterexample_units": counts})
        if not counts:
            status = "real"
            break
        if iteration == max_iterations:
            status = "max_iterations"
            break
        selection = refine({"wrapper": wrapper, "prop": prop, "units": units, "assignment": dict(assignment),
                            "model": info["model"], "coi_state_bits": info["coi_state_bits"],
                            "cex_depth": check["cex_depth"], "counterexample": counterexample, "counts": counts,
                            "history": history, "models_dir": models_dir, "time_limit": time_limit,
                            "workdir": workdir})
        record.update({"refined_units": selection["refined"], "selection_seconds": selection["seconds"],
                       "selection": {k: v for k, v in selection.items() if k not in ("refined", "seconds")}})
        if not selection["refined"] or not set(selection["refined"]) <= set(counts):
            raise ValueError("refined units {} are not in the counterexample".format(selection["refined"]))
        for unit_id in selection["refined"]:
            assignment = finer(units, assignment, unit_id)
    total = sum(r["build_seconds"] + r["ric3_seconds"] + r.get("replay_seconds", 0) + r.get("selection_seconds", 0)
                for r in history)
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
    r.add_argument("--refine", choices=["all", "one", "bmc", "llm"], default="all")
    r.add_argument("--models", help="directory of models and verdicts reused across runs (default: workdir/models)")
    r.add_argument("--description", help="property description for --refine llm")
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
    if args.refine in REFINERS:
        refine = REFINERS[args.refine]
    else:
        import choice_refine
        refine = choice_refine.strategy(args.refine, args.description)
    models_dir = os.path.abspath(args.models) if args.models else None
    os.chdir(workdir)
    result = cegar(wrapper, args.prop, units, assignment, workdir, args.time_limit, args.max_iterations, refine,
                   models_dir)
    with open(os.path.join(workdir, "cegar.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "refinements", "total_seconds", "final_assignment")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
