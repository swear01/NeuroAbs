"""Let an LLM write the abstraction selection rule of fine_choice, then apply it without further calls.

A rule is restricted Python (llm_rule_exec) that defines choose(sub, design).
design describes the wrapper and the choices (built by design_input), sub one
sub-property (sub_input).  choose returns a dict that gives every choice id of
design["choices"] one of its levels; it becomes a fine_choice spec with
fine_choice_llm.to_spec.  An invalid rule or output is rejected and reported,
never repaired.

Commands:
  prompt    write the exact prompt (system and user message) for a case
  generate  send the prompt to DeepSeek n times and store each answer and the rule it contains
  apply     run a rule on every sub-property of a case and write the specs and the comparison with fine_choice.structural
"""
import argparse
import json
import os
import re
import subprocess
import sys

import fine_choice
import fine_choice_llm
import llm_rule_exec
from choice_llm import unit_ports

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXECUTOR = os.path.join(SCRIPT_DIR, "llm_rule_exec.py")
RUN_TIMEOUT = 120
CODE_BLOCK = re.compile(r"```(?:python)?[ \t]*\n(.*?)```", re.S)

with open(os.path.join(SCRIPT_DIR, "llm_rule_context.txt")) as f:
    rule_context = f.read()


def design_input(text, units, ufs, ports, description):
    """The design-level input of a rule: description, choices with levels, GPR assumptions and operand fields."""
    assigns = fine_choice.read_assigns(text)
    recorders = fine_choice.recorder_map(assigns)
    choices = []
    for c in fine_choice_llm.menu(units, ufs):
        entry = {"id": c["id"], "levels": c["levels"]}
        if "path" in c:
            entry.update({"kind": "unit", "instance": c["path"], "module": c["module"],
                          "coi_state_bits": c["coi_state_bits"], "outputs": ports[c["id"]]})
        elif "uf" in c:
            entry.update({"kind": "operator", "ila_node": c["uf"]["ila"], "ila_expr": list(c["uf"]["ila_expr"]),
                          "rtl_node": c["uf"]["rtl"], "rtl_expr": list(c["uf"]["rtl_expr"])})
        else:
            entry.update({"kind": "gpr", "register": int(c["id"][3:])})
        choices.append(entry)
    gpr_assumptions = {str(j): [] for j in range(fine_choice.NUM_GPRS)}
    for c in fine_choice.conjunct_names(assigns, "assume"):
        refs = fine_choice.gpr_refs(assigns[c], recorders)
        if len(refs) == 1:
            gpr_assumptions[str(next(iter(refs)))].append("{:s} = {:s}".format(c, assigns[c]))
    return {"description": description.strip(), "operand_fields": fine_choice.operand_fields(text),
            "choices": choices, "gpr_assumptions": gpr_assumptions}


def sub_input(sub, text):
    """The input of a rule for one sub-property: its states, case (also parsed) and assertion."""
    assigns = fine_choice.read_assigns(text)
    named = fine_choice.property_conjuncts(text)
    case = sub.get("case")
    terms = [{"field": f, "op": op, "value": int(v)} for f, op, v in fine_choice.CASE_TERM.findall(case or "")]
    return {"name": sub["name"], "states": list(sub["states"]), "case": case, "case_terms": terms,
            "assertion": ["{:s} = {:s}".format(c, assigns[c]) for s in sub["states"] for c in named[s]]}


def check_output(output, choices):
    """Return the errors of a rule output: it must give exactly every choice id one of its levels."""
    if not isinstance(output, dict):
        return ["output is not a dict"]
    errors = []
    ids = [c["id"] for c in choices]
    missing = [i for i in ids if i not in output]
    extra = sorted(set(output) - set(ids))
    if missing:
        errors.append("missing choices {}".format(missing))
    if extra:
        errors.append("unknown choices {}".format(extra))
    for c in choices:
        if c["id"] in output and output[c["id"]] not in c["levels"]:
            errors.append("{:s}: {!r} is not one of {}".format(c["id"], output[c["id"]], c["levels"]))
    return errors


def run_rule(source, design, subs, python=sys.executable):
    """Run a rule on sub-properties in a separate isolated interpreter; return {name: output} or raise."""
    request = json.dumps({"source": source, "design": design, "subs": subs})
    proc = subprocess.run([python, "-I", EXECUTOR], input=request, capture_output=True, text=True,
                          timeout=RUN_TIMEOUT, cwd="/")
    if proc.returncode != 0:
        raise RuntimeError("rule executor failed with exit {:d}: {:s}".format(proc.returncode, proc.stderr[-2000:]))
    return json.loads(proc.stdout)["results"]


def apply_rule(source, design, subs, ufs):
    """Return ({name: spec}, {name: errors}) for every sub-property."""
    specs, errors = {}, {}
    for r in run_rule(source, design, subs):
        if "error" in r:
            errors[r["name"]] = [r["error"]]
            continue
        problems = check_output(r["output"], design["choices"])
        if problems:
            errors[r["name"]] = problems
            continue
        sub = next(s for s in subs if s["name"] == r["name"])
        specs[r["name"]] = fine_choice_llm.to_spec(sub, r["output"], ufs)
    return specs, errors


def normal(spec):
    """The parts of a spec that define the abstraction, in a comparable form."""
    return {"keep_gprs": sorted(spec.get("keep_gprs", [])), "word_gprs": sorted(spec.get("word_gprs", [])),
            "units": dict(sorted(spec.get("units", {}).items())),
            "uf": sorted((u["ila"], u["rtl"]) for u in spec.get("uf", []))}


def build_prompt(design, examples):
    lines = ["The design and the choices (the design argument of choose):",
             json.dumps(design, indent=1), "",
             "Training examples: sub-property arguments of choose for this design. They show the format; the rule "
             "is applied to every sub-property of the split, including ones not shown here.", ""]
    for e in examples:
        lines.append(json.dumps(e, indent=1))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def extract_rule(text):
    """Return the single Python code block of an answer, or raise ValueError."""
    blocks = CODE_BLOCK.findall(text)
    if len(blocks) != 1:
        raise ValueError("expected exactly one code block, found {:d}".format(len(blocks)))
    return blocks[0]


def case_inputs(args):
    wrapper = os.path.abspath(args.wrapper)
    with open(wrapper) as f:
        text = f.read()
    with open(args.units) as f:
        units = json.load(f)
    with open(args.uf) as f:
        ufs = fine_choice_llm.uf_details(text, json.load(f))
    with open(args.description) as f:
        description = f.read()
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    unit_choices = [c for c in fine_choice_llm.menu(units, ufs) if "path" in c]
    ports = unit_ports(unit_choices, wrapper, workdir)
    return text, units, ufs, design_input(text, units, ufs, ports, description)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prompt", "generate", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--wrapper", required=True)
        p.add_argument("--units", required=True)
        p.add_argument("--uf", required=True, help="JSON list of operator pairs (ila, rtl)")
        p.add_argument("--description", required=True)
        p.add_argument("--workdir", required=True, help="scratch directory for the Yosys hierarchy")
    for name in ("prompt", "generate"):
        sub.choices[name].add_argument("--examples", required=True, help="JSON list of training sub-properties")
        sub.choices[name].add_argument("--out", required=True, help="output directory")
    sub.choices["generate"].add_argument("--samples", type=int, required=True)
    sub.choices["apply"].add_argument("--rule", required=True)
    sub.choices["apply"].add_argument("--subs", required=True, help="JSON list of sub-properties")
    sub.choices["apply"].add_argument("--out", required=True, help="output JSON")
    args = parser.parse_args(argv)
    text, units, ufs, design = case_inputs(args)
    if args.command in ("prompt", "generate"):
        with open(args.examples) as f:
            examples = [sub_input(s, text) for s in json.load(f)]
        message = build_prompt(design, examples)
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "prompt-system.txt"), "w") as f:
            f.write(rule_context)
        with open(os.path.join(args.out, "prompt-user.txt"), "w") as f:
            f.write(message)
        if args.command == "prompt":
            return 0
        from deepseek_chat import call_deepseek, chat_text
        import deepseek_chat
        os.chdir(args.out)
        for i in range(1, args.samples + 1):
            response, elapsed = call_deepseek(rule_context, message, i)
            answer = chat_text(response)
            record = {"sample": i, "served_model": response.get("model"), "usage": response.get("usage"),
                      "elapsed_seconds": elapsed, "answer": answer}
            try:
                source = extract_rule(answer)
                record["errors"] = llm_rule_exec.validate(source)
                with open("rule-{:d}.py".format(i), "w") as f:
                    f.write(source)
            except ValueError as e:
                record["errors"] = [str(e)]
            with open("answers.jsonl", "a") as f:
                f.write(json.dumps(record) + "\n")
            print(json.dumps({"sample": i, "errors": record["errors"], "spent_usd": round(deepseek_chat.spent_usd, 4)}),
                  flush=True)
        return 0
    with open(args.rule) as f:
        source = f.read()
    with open(args.subs) as f:
        subs = json.load(f)
    specs, errors = apply_rule(source, design, [sub_input(s, text) for s in subs], ufs)
    rows = []
    for s in subs:
        structural = fine_choice.structural(s, [u for u in units if u["id"] != fine_choice.GPR_UNIT], ufs)
        row = {"name": s["name"], "structural": structural}
        if s["name"] in specs:
            row.update({"spec": specs[s["name"]], "same": normal(specs[s["name"]]) == normal(structural)})
        else:
            row["errors"] = errors[s["name"]]
        rows.append(row)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=1)
    print(json.dumps({"subs": len(rows), "same": sum(r.get("same", False) for r in rows),
                      "different": sum(r.get("same") is False for r in rows), "rejected": len(errors)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
