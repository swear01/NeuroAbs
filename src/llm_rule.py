"""Let an LLM write the abstraction selection rule of fine_choice, then apply it without further calls.

A rule is restricted Python (llm_rule_exec) that defines choose(sub, design).
design describes the wrapper and the choices (built by design_input), sub one
sub-property (sub_input).  choose returns a dict that gives every choice id of
design["choices"] one of its levels; it becomes a fine_choice spec with
fine_choice_llm.to_spec.  An invalid rule or output is rejected and reported,
never repaired.

Commands:
  prompt    write the exact prompt (system and user message) for a case
  generate  send the prompt to DeepSeek or Claude (claude_cli) n times and store each answer and the rule it contains
  feedback  send each answer of a generate run one follow-up message in the same conversation; store the revised
            rules
  apply     run a rule on every sub-property of a case and write the comparison with fine_choice.structural
            (with both specs where they differ)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid

import fine_choice
import fine_choice_llm
import llm_rule_exec
from choice_llm import unit_ports

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXECUTOR = os.path.join(SCRIPT_DIR, "llm_rule_exec.py")
RUN_TIMEOUT = 120
DEEPSEEK_DIRECT = {"deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash"}
ASSIGNMENT = re.compile(r"(?:assign|wire\s*\[[^\]]*\])\s+(\w+)\s*=\s*(.*?);", re.S)
OPERAND_DEPTH = 3
OPERAND_LINES = 6
OPERAND_CHARS = 300
CODE_BLOCK = re.compile(r"```(?:python)?[ \t]*\n(.*?)```", re.S)

with open(os.path.join(SCRIPT_DIR, "llm_rule_context.txt")) as f:
    rule_context = f.read()


def operand_sources(text, instance, operands):
    """For each operand of an operator node, the assignments of the operand and of the signals it reads,
    OPERAND_DEPTH levels deep in breadth-first order (at most OPERAND_LINES per operand, each cut to OPERAND_CHARS
    characters, each signal once)."""
    start, end = fine_choice.module_span(text, fine_choice.instance_module(text, instance))
    defs = {m.group(1): " ".join(m.group(2).split()) for m in ASSIGNMENT.finditer(text, start, end)}
    out, seen = [], set()
    for operand in operands:
        frontier, lines = [operand], 0
        for _ in range(OPERAND_DEPTH):
            following = []
            for name in frontier:
                if name in seen or name not in defs or lines == OPERAND_LINES:
                    continue
                seen.add(name)
                lines += 1
                body = defs[name]
                out.append("{:s} = {:s}".format(name, body if len(body) <= OPERAND_CHARS
                                                else body[:OPERAND_CHARS] + " ..."))
                following.extend(re.findall(r"(?<!')\b[A-Za-z_]\w*", body))
            frontier = following
    return out


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
            ila_expr, rtl_expr = list(c["uf"]["ila_expr"]), list(c["uf"]["rtl_expr"])
            entry.update({"kind": "operator", "ila_node": c["uf"]["ila"], "ila_expr": ila_expr,
                          "ila_operand_sources": operand_sources(text, "ILA", [ila_expr[0], ila_expr[2]]),
                          "rtl_node": c["uf"]["rtl"], "rtl_expr": rtl_expr,
                          "rtl_operand_sources": operand_sources(text, "RTL", [rtl_expr[0], rtl_expr[2]])})
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
    for side in ("ila_node", "rtl_node"):
        nodes = [c[side] for c in choices if c.get("kind") == "operator" and output.get(c["id"]) == "uf"]
        for node in sorted({n for n in nodes if nodes.count(n) > 1}):
            errors.append("more than one operator choice at level uf has {:s} {:s}".format(side, node))
    return errors


def run_rule(source, design, subs, python=sys.executable):
    """Run a rule on sub-properties in a separate isolated interpreter; return {name: output} or raise."""
    request = json.dumps({"source": source, "design": design, "subs": subs})
    proc = subprocess.run([python, "-I", EXECUTOR], input=request, capture_output=True, text=True,
                          timeout=RUN_TIMEOUT, cwd="/")
    if proc.returncode != 0:
        raise RuntimeError("rule executor failed with exit {:d}: {:s}".format(proc.returncode, proc.stderr[-2000:]))
    return json.loads(proc.stdout)["results"]


def apply_rule(source, design, inputs, subs, ufs):
    """Return ({name: spec}, {name: errors}) for every sub-property; inputs are the rule arguments of subs."""
    if [i["name"] for i in inputs] != [s["name"] for s in subs]:
        raise ValueError("inputs and subs must name the same sub-properties in the same order")
    by_name = {s["name"]: s for s in subs}
    specs, errors = {}, {}
    for r in run_rule(source, design, inputs):
        if "error" in r:
            errors[r["name"]] = [r["error"]]
            continue
        problems = check_output(r["output"], design["choices"])
        if problems:
            errors[r["name"]] = problems
            continue
        specs[r["name"]] = fine_choice_llm.to_spec(by_name[r["name"]], r["output"], ufs)
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


def store_rule(answer, path):
    """Write the rule of an answer to path; return its validation errors (or the extraction error)."""
    try:
        source = extract_rule(answer)
    except ValueError as e:
        return [str(e)]
    with open(path, "w") as f:
        f.write(source)
    return llm_rule_exec.validate(source)


def ask(backend, prompt, rule_path, request_id, previous=None, follow_up=None):
    """Send the prompt, or, given the record of an earlier answer to it, the follow-up turn; store the rule of the
    answer at rule_path and return the record of the call.  A follow-up continues the same conversation: DeepSeek
    gets the prompt, the earlier answer and the follow-up; Claude resumes its session."""
    started = time.time()
    if backend == "deepseek":
        from deepseek_chat import call_deepseek_messages, chat_text
        import deepseek_chat
        messages = [{"role": "system", "content": rule_context}, {"role": "user", "content": prompt}]
        if previous is not None:
            messages += [{"role": "assistant", "content": previous["answer"]}, {"role": "user", "content": follow_up}]
        response, _ = call_deepseek_messages(messages, request_id)
        if response.get("model") not in DEEPSEEK_DIRECT or "provider" in response:
            raise RuntimeError("DeepSeek request {:d} was not served by OpenCode Go or Command Code: model {!r}"
                               .format(request_id, response.get("model")))
        answer = chat_text(response)
        record = {"backend": backend, "served_model": response.get("model"), "usage": response.get("usage"),
                  "spent_usd_process": deepseek_chat.spent_usd}
    elif backend == "claude":
        import claude_cli
        if previous is None:
            session = {"session_id": str(uuid.uuid4()),
                       "workdir": os.path.abspath("claude-cwd/request-{:d}".format(request_id))}
        else:
            session = {k: previous[k] for k in ("session_id", "workdir")}
        reply = claude_cli.call_claude(rule_context, prompt if previous is None else follow_up, session["workdir"],
                                       session["session_id"], os.path.abspath(rule_path[:-3] + ".claude.jsonl"),
                                       resume=previous is not None)
        init = reply["init"]
        answer = reply["answer"]
        record = dict(session, backend=backend, served_models=reply["models"], usage=reply["result"].get("usage"),
                      model_usage=reply["result"].get("modelUsage"),
                      list_cost_usd=reply["result"].get("total_cost_usd"),
                      init={k: init.get(k) for k in ("model", "tools", "mcp_servers", "apiKeySource", "cwd",
                                                     "claude_code_version", "permissionMode")})
    else:
        raise ValueError("unknown backend " + backend)
    record.update({"elapsed_seconds": time.time() - started, "answer": answer,
                   "errors": store_rule(answer, rule_path)})
    return record


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


def feedback(out, feedback_path):
    """Send each sample of a generate directory its follow-up message; the revised rules are rule-fb<i>.py."""
    with open(feedback_path) as f:
        messages = json.load(f)
    os.chdir(out)
    if os.path.exists("answers-feedback.jsonl"):
        raise SystemExit("answers-feedback.jsonl already exists in " + out)
    with open("prompt-user.txt") as f:
        prompt = f.read()
    with open("answers.jsonl") as f:
        previous = {r["sample"]: r for r in map(json.loads, filter(str.strip, f))}
    for i in sorted(int(k) for k in messages):
        record = dict(ask(previous[i]["backend"], prompt, "rule-fb{:d}.py".format(i), 100 + i, previous[i],
                          messages[str(i)]), sample=i, follow_up=messages[str(i)])
        with open("answers-feedback.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")
        print(json.dumps({"sample": i, "errors": record["errors"]}), flush=True)
    return 0


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
    sub.choices["generate"].add_argument("--backend", choices=["deepseek", "claude"], required=True)
    sub.choices["apply"].add_argument("--rule", required=True)
    sub.choices["apply"].add_argument("--subs", required=True, help="JSON list of sub-properties")
    sub.choices["apply"].add_argument("--out", required=True, help="output JSON")
    f = sub.add_parser("feedback", help="one follow-up turn per earlier answer of a generate directory")
    f.add_argument("--out", required=True, help="the generate output directory")
    f.add_argument("--feedback", required=True, help="JSON object: sample number -> follow-up message")
    args = parser.parse_args(argv)
    if args.command == "feedback":
        return feedback(args.out, args.feedback)
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
        os.chdir(args.out)
        if os.path.exists("answers.jsonl"):
            raise SystemExit("answers.jsonl already exists in " + args.out)
        for i in range(1, args.samples + 1):
            record = dict(ask(args.backend, message, "rule-{:d}.py".format(i), i), sample=i)
            with open("answers.jsonl", "a") as f:
                f.write(json.dumps(record) + "\n")
            print(json.dumps({"sample": i, "errors": record["errors"]}), flush=True)
        return 0
    with open(args.rule) as f:
        source = f.read()
    with open(args.subs) as f:
        subs = json.load(f)
    specs, errors = apply_rule(source, design, [sub_input(s, text) for s in subs], subs, ufs)
    rows = []
    for s in subs:
        structural = fine_choice.structural(s, [u for u in units if u["id"] != fine_choice.GPR_UNIT], ufs)
        row = {"name": s["name"]}
        if s["name"] in specs:
            row["same"] = normal(specs[s["name"]]) == normal(structural)
            if not row["same"]:
                row.update({"spec": specs[s["name"]], "structural": structural})
        else:
            row.update({"errors": errors[s["name"]], "structural": structural})
        rows.append(row)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=1)
    print(json.dumps({"subs": len(rows), "same": sum(r.get("same", False) for r in rows),
                      "different": sum(r.get("same") is False for r in rows), "rejected": len(errors)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
