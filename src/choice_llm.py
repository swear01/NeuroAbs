"""Ask an LLM to choose an abstraction level for every unit of a wrapper.

The answer is strict JSON with one choice and calibrated probabilities per
unit.  An invalid answer for a unit leaves that unit at keep.
"""
import argparse
import json
import os
import re
import sys

from choice_abstraction import PROPERTY_REMOVE, hierarchy_json, instance_table

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSERT_PREFIX = {"ila": ("variable_map_assert",), "sanity": ("post_value_holder_overly_constrained",
                                                             "post_value_holder_triggered")}
MAX_PORTS = 40
PROBABILITY_TOLERANCE = 0.01

with open(os.path.join(SCRIPT_DIR, "choice_context.txt")) as f:
    choice_context = f.read()


def assertion_lines(wrapper, prop):
    with open(wrapper) as f:
        return [line.strip() for line in f
                if re.match(r"\s*assign\s+(" + "|".join(ASSERT_PREFIX[prop]) + r")\w*\s*=", line)]


def unit_ports(units, wrapper, workdir):
    modules = hierarchy_json(wrapper, workdir)
    table = instance_table(modules)
    ports = {}
    for u in units:
        spec = modules[table[u["path"]][2]]["ports"]
        ports[u["id"]] = ["{:s}[{:d}]".format(p, len(v["bits"])) for p, v in spec.items() if v["direction"] == "output"]
    return ports


def build_message(units, ports, description, assertions):
    lines = ["The description of the property:", description.strip(), "",
             "The assertion, as Verilog assignments that are all required to hold:"]
    lines.extend(assertions)
    lines.extend(["", "The units:"])
    for u in units:
        lines.append("- id: " + u["id"])
        lines.append("  instance: {:s} (module {:s})".format(u["path"], u["module"]))
        lines.append("  state bits in the cone of influence: {:d}".format(u["coi_state_bits"]))
        if u["memories"]:
            lines.append("  memories: " + ", ".join("{:s} ({:d} bits)".format(m["name"][len(u["path"]) + 1:],
                                                                             m["coi_state_bits"])
                                                    for m in u["memories"]))
        names = ports[u["id"]]
        shown = names[:MAX_PORTS]
        more = " and {:d} more".format(len(names) - len(shown)) if len(names) > len(shown) else ""
        lines.append("  outputs: " + ", ".join(shown) + more)
        lines.append("  levels: " + ", ".join(u["levels"]))
    return "\n".join(lines)


def parse_choices(text, units):
    """Return (assignment, probabilities, errors) from the model's answer."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {}, {}, {"*": "invalid JSON: {:s}".format(str(e))}
    if not isinstance(data, dict) or set(data) != {"choices"} or not isinstance(data["choices"], dict):
        return {}, {}, {"*": "expected exactly the key choices"}
    assignment, probabilities, errors = {}, {}, {}
    for u in units:
        entry = data["choices"].get(u["id"])
        if not isinstance(entry, dict) or set(entry) != {"answer", "probabilities"}:
            errors[u["id"]] = "expected exactly the keys answer and probabilities"
            continue
        answer, probs = entry["answer"], entry["probabilities"]
        if answer not in u["levels"]:
            errors[u["id"]] = "answer is not one of {}".format(u["levels"])
            continue
        if not isinstance(probs, dict) or set(probs) != set(u["levels"]) or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in probs.values()):
            errors[u["id"]] = "probabilities must give a number in [0, 1] for each of {}".format(u["levels"])
            continue
        if abs(sum(probs.values()) - 1) > PROBABILITY_TOLERANCE:
            errors[u["id"]] = "probabilities do not sum to 1"
            continue
        assignment[u["id"]] = answer
        probabilities[u["id"]] = probs
    extra = sorted(set(data["choices"]) - {u["id"] for u in units})
    if extra:
        errors["*"] = "unknown units {}".format(extra)
    return assignment, probabilities, errors


def decide(units, wrapper, prop, description, workdir, call, extract_text):
    message = build_message(units, unit_ports(units, wrapper, workdir), description, assertion_lines(wrapper, prop))
    response, elapsed = call(choice_context, message, 1)
    text = extract_text(response)
    assignment, probabilities, errors = parse_choices(text, units)
    return {
        "assignment": {u["id"]: assignment.get(u["id"], "keep") for u in units},
        "probabilities": probabilities,
        "errors": errors,
        "model_output": text,
        "served_model": response.get("model"),
        "usage": response.get("usage"),
        "elapsed_seconds": elapsed,
        "message": message,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--prop", choices=sorted(PROPERTY_REMOVE), required=True)
    parser.add_argument("--units", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the message without calling the model")
    args = parser.parse_args(argv)
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    with open(args.units) as f:
        units = json.load(f)
    with open(args.description) as f:
        description = f.read()
    wrapper = os.path.abspath(args.wrapper)
    if args.dry_run:
        print(build_message(units, unit_ports(units, wrapper, workdir), description, assertion_lines(wrapper, args.prop)))
        return 0
    from deepseek_chat import call_deepseek, chat_text
    os.chdir(workdir)
    result = decide(units, wrapper, args.prop, description, workdir, call_deepseek, chat_text)
    with open("decision.json", "w") as f:
        json.dump(result, f, indent=2)
    with open("assignment.json", "w") as f:
        json.dump(result["assignment"], f, indent=2)
    print(json.dumps({k: result[k] for k in ("assignment", "errors", "served_model")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
