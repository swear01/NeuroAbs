"""Ask an LLM to choose the abstraction of every sub-property of an ILA wrapper.

The choices are the units of choice_abstraction other than the GPR file
(keep or cut), one choice per GPR (keep or havoc), and the operator pairs that
may be abstracted by an uninterpreted function (keep or uf).  One call per
sub-property; the answer uses the strict JSON of choice_llm.  An invalid answer
for a choice leaves it at keep.
"""
import argparse
import json
import os
import re
import sys

import fine_choice
from choice_llm import MAX_PORTS, parse_choices, unit_ports

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "fine_choice_context.txt")) as f:
    fine_choice_context = f.read()


def menu(units, ufs):
    """Return the choices offered for a sub-property, in the units format of choice_llm."""
    choices = [u for u in units if u["id"] != fine_choice.GPR_UNIT]
    choices = [dict(u, levels=[level for level in u["levels"] if level != "havoc"]) for u in choices]
    choices += [{"id": "gpr{:d}".format(j), "levels": ["keep", "word", "havoc"]} for j in range(fine_choice.NUM_GPRS)]
    choices += [{"id": "uf{:d}".format(i), "levels": ["keep", "uf"], "uf": uf} for i, uf in enumerate(ufs)]
    return choices


def build_message(sub, choices, ports, description, text):
    """The description and the choices come first, so that the message prefix is shared by all sub-properties."""
    assigns = fine_choice.read_assigns(text)
    named = fine_choice.property_conjuncts(text)
    lines = ["The description of the property:", description.strip(), "", "The choices:"]
    for c in choices:
        lines.append("- id: " + c["id"])
        if "path" in c:
            lines.append("  unit: {:s} (module {:s}), {:d} state bits in the cone of influence of the property"
                         .format(c["path"], c["module"], c["coi_state_bits"]))
            names = ports[c["id"]]
            more = " and {:d} more".format(len(names) - MAX_PORTS) if len(names) > MAX_PORTS else ""
            lines.append("  outputs: " + ", ".join(names[:MAX_PORTS]) + more)
        elif "uf" in c:
            lines.append("  operator: ILA {:s} = {:s}; RTL {:s} = {:s}".format(
                c["uf"]["ila"], " ".join(c["uf"]["ila_expr"]), c["uf"]["rtl"], " ".join(c["uf"]["rtl_expr"])))
        else:
            lines.append("  register x{:s}: the RTL register file word and the ILA state".format(c["id"][3:]))
        lines.append("  levels: " + ", ".join(c["levels"]))
    lines.extend(["", "The sub-property {:s}, as Verilog assignments that are all required to hold:".format(sub["name"])])
    for state in sub["states"]:
        for c in named[state]:
            line = "assign {:s} = {:s} ;".format(c, assigns[c])
            if sub.get("rd_guard") and state != "x0" and state.startswith("x"):
                line += " // required only when rd == " + state[1:]
            lines.append(line)
    lines.append("")
    if sub.get("case"):
        lines.append("The case: the sub-property is checked only for an instruction with {:s}, where rd is "
                     "inst[11:7], rs1 is inst[19:15], rs2 is inst[24:20] and imm is inst[31:20] of the checked "
                     "instruction.".format(sub["case"].replace("&&", " and ")))
    else:
        lines.append("The case: every instruction.")
    return "\n".join(lines)


def to_spec(sub, assignment, ufs):
    return {
        "states": sub["states"],
        "case": sub.get("case"),
        "rd_guard": sub.get("rd_guard", False),
        "keep_gprs": [j for j in range(fine_choice.NUM_GPRS) if assignment.get("gpr{:d}".format(j), "keep") == "keep"],
        "word_gprs": [j for j in range(fine_choice.NUM_GPRS) if assignment.get("gpr{:d}".format(j)) == "word"],
        "units": {k: v for k, v in assignment.items() if not re.fullmatch(r"(gpr|uf)\d+", k)},
        "uf": [{"ila": uf["ila"], "rtl": uf["rtl"]} for i, uf in enumerate(ufs)
               if assignment.get("uf{:d}".format(i)) == "uf"],
    }


def decide(sub, choices, ports, description, text, ufs, call, extract_text, request_id):
    message = build_message(sub, choices, ports, description, text)
    response, elapsed = call(fine_choice_context, message, request_id)
    output = extract_text(response)
    assignment, probabilities, errors = parse_choices(output, choices)
    full = {c["id"]: assignment.get(c["id"], "keep") for c in choices}
    return {
        "name": sub["name"],
        "assignment": full,
        "spec": to_spec(sub, full, ufs),
        "probabilities": probabilities,
        "errors": errors,
        "model_output": output,
        "served_model": response.get("model"),
        "usage": response.get("usage"),
        "elapsed_seconds": elapsed,
        "message": message,
    }


def uf_details(text, ufs):
    ila_module, rtl_module = fine_choice.instance_module(text, "ILA"), fine_choice.instance_module(text, "RTL")
    return [dict(uf, ila_expr=fine_choice.operator_args(text, ila_module, uf["ila"]),
                 rtl_expr=fine_choice.operator_args(text, rtl_module, uf["rtl"])) for uf in ufs]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--units", required=True)
    parser.add_argument("--subs", required=True, help="JSON list of sub-properties (name, states, case)")
    parser.add_argument("--uf", required=True, help="JSON list of operator pairs (ila, rtl)")
    parser.add_argument("--description", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the first message without calling the model")
    args = parser.parse_args(argv)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    wrapper = os.path.abspath(args.wrapper)
    with open(wrapper) as f:
        text = f.read()
    with open(args.units) as f:
        units = json.load(f)
    with open(args.subs) as f:
        subs = json.load(f)
    with open(args.uf) as f:
        ufs = uf_details(text, json.load(f))
    with open(args.description) as f:
        description = f.read()
    choices = menu(units, ufs)
    ports = unit_ports([c for c in choices if "path" in c], wrapper, workdir)
    if args.dry_run:
        print(build_message(subs[0], choices, ports, description, text))
        return 0
    from deepseek_chat import call_deepseek, chat_text
    import deepseek_chat
    os.chdir(workdir)
    done = set()
    if os.path.exists("decisions.jsonl"):
        with open("decisions.jsonl") as f:
            done = {json.loads(line)["name"] for line in f if line.strip()}
    for i, sub in enumerate(subs):
        if sub["name"] in done:
            continue
        result = decide(sub, choices, ports, description, text, ufs, call_deepseek, chat_text, i + 1)
        with open("decisions.jsonl", "a") as f:
            f.write(json.dumps(result) + "\n")
        print(json.dumps({"name": sub["name"], "spec": result["spec"], "errors": result["errors"],
                          "spent_usd": round(deepseek_chat.spent_usd, 4)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
