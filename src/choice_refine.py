"""Refinement strategies for choice-level CEGAR beyond counting free values.

bmc: refine each candidate unit alone and run rIC3 BMC up to the counterexample
depth; take the smallest model with no counterexample up to that depth, or, if
every candidate still has one, the candidate whose first counterexample is
deepest.  The builds of the other candidates and every BMC run are its cost.

llm: send a summary of the counterexample (free values per unit, the signals
they drive and their cycles), the units with their sizes and levels, and the
earlier refinements to an LLM, which names one unit.  An invalid answer stops
the refinement.
"""
import functools
import json
import os
import time

import choice_abstraction as ca
from choice_llm import assertion_lines

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_SIGNALS = 8
PROBABILITY_TOLERANCE = 0.01

with open(os.path.join(SCRIPT_DIR, "refine_context.txt")) as f:
    refine_context = f.read()

request_counter = 0


def refine_bmc(context):
    units, assignment, bound = context["units"], context["assignment"], context["cex_depth"]
    candidates = []
    for unit_id in sorted(context["counts"]):
        refined = ca.finer(units, assignment, unit_id)
        info = ca.abstract_model(context["wrapper"], context["prop"], units, refined, context["models_dir"])
        check = ca.bmc_verdict(info, bound, context["time_limit"])
        candidates.append({"unit": unit_id, "level": refined[unit_id], "coi_state_bits": info["coi_state_bits"],
                           "bmc": check["bmc"], "cex_depth": check["cex_depth"],
                           "build_seconds": info["build_seconds"], "bmc_seconds": check["bmc_seconds"]})
    rank = {"NONE": 0, "TIMEOUT": 1, "SAT": 2}
    if any(c["bmc"] not in rank for c in candidates):
        raise RuntimeError("rIC3 BMC failed on a candidate: {:s}".format(json.dumps(candidates)))
    best = min(candidates, key=lambda c: (rank[c["bmc"]], -(c["cex_depth"] or 0), c["coi_state_bits"], c["unit"]))
    seconds = sum(c["bmc_seconds"] + (c["build_seconds"] if c is not best else 0) for c in candidates)
    return {"refined": [best["unit"]], "seconds": seconds, "bound": bound, "candidates": candidates}


def model_signals(context):
    directory = os.path.dirname(context["model"])
    choices = ca.assignment_choices(context["units"], context["assignment"])

    def compute():
        started = time.time()
        signals = ca.free_value_signals(context["wrapper"], context["prop"], choices, context["model"] + ".work")
        return {"signals": signals, "seconds": time.time() - started}

    return ca.stored(os.path.join(directory, "signals.json"), compute)


def unit_signals(values, signals):
    frames = {}
    for v in values:
        frames.setdefault(signals.get(v["name"], v["name"]), set()).add(v["frame"])
    ordered = sorted(frames, key=lambda s: (-len(frames[s]), min(frames[s]), s))
    shown = ["{:s} (cycle{:s} {:s})".format(s, "s" if len(frames[s]) > 1 else "",
                                           ", ".join(str(k) for k in sorted(frames[s])))
             for s in ordered[:MAX_SIGNALS]]
    more = "; and {:d} more signals".format(len(ordered) - MAX_SIGNALS) if len(ordered) > MAX_SIGNALS else ""
    return "; ".join(shown) + more


def build_message(description, assertions, context, signals):
    units, assignment, depth = context["units"], context["assignment"], context["cex_depth"]
    lines = ["The description of the property:", description.strip(), "",
             "The assertion, as Verilog assignments that are all required to hold:"]
    lines.extend(assertions)
    lines.extend(["",
                  "The current abstract model has {:d} state bits in the cone of influence of the property.".format(
                      context["coi_state_bits"]),
                  "The counterexample has {:d} cycles, 0 to {:d}; the property fails in cycle {:d}.".format(
                      depth + 1, depth, depth),
                  "", "The units:"])
    for u in units:
        level = assignment[u["id"]]
        lines.append("- id: " + u["id"])
        lines.append("  instance: {:s} (module {:s})".format(u["path"], u["module"]))
        lines.append("  state bits in the cone of influence of the original design: {:d}".format(u["coi_state_bits"]))
        if level == "keep":
            lines.append("  level: keep")
            continue
        lines.append("  level: {:s}; refining moves it to {:s}".format(
            level, ca.finer(units, assignment, u["id"])[u["id"]]))
        values = [v for v in context["counterexample"] if v["unit"] == u["id"]]
        lines.append("  unconstrained values in the counterexample: {:d}".format(len(values)))
        if values:
            lines.append("  signals they drive: " + unit_signals(values, signals))
    lines.extend(["", "Candidate units: " + ", ".join(sorted(context["counts"])), ""])
    earlier = [r for r in context["history"][:-1] if r.get("refined_units")]
    if not earlier:
        lines.append("Earlier refinements: none.")
    else:
        lines.append("Earlier refinements:")
        for r in earlier:
            lines.append("- iteration {:d}: counterexample of {:d} cycles with unconstrained values from {:s}; "
                         "refined {:s}.".format(r["iteration"], r["cex_depth"] + 1,
                                                ", ".join("{:s} ({:d})".format(k, n)
                                                          for k, n in sorted(r["counterexample_units"].items())),
                                                ", ".join(r["refined_units"])))
    return "\n".join(lines)


def parse_refinement(text, candidates):
    """Return (unit, probabilities, reason) from the model's answer; raise ValueError if it is invalid."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("invalid JSON: {:s}".format(str(e))) from None
    if not isinstance(data, dict) or set(data) != {"refine", "probabilities", "reason"}:
        raise ValueError("expected exactly the keys refine, probabilities and reason")
    unit, probs, reason = data["refine"], data["probabilities"], data["reason"]
    if unit not in candidates:
        raise ValueError("refine is not one of {}".format(sorted(candidates)))
    if not isinstance(probs, dict) or set(probs) != set(candidates) or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in probs.values()):
        raise ValueError("probabilities must give a number in [0, 1] for each of {}".format(sorted(candidates)))
    if abs(sum(probs.values()) - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("probabilities do not sum to 1")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")
    return unit, probs, reason


def refine_llm(context, description, call, extract_text, cost):
    global request_counter
    named = model_signals(context)
    message = build_message(description, assertion_lines(context["wrapper"], context["prop"]), context,
                            named["signals"])
    request_counter += 1
    response, elapsed = call(refine_context, message, request_counter)
    text = extract_text(response)
    artifact = {"iteration": context["history"][-1]["iteration"], "message": message, "model_output": text,
                "served_model": response.get("model"), "usage": response.get("usage"),
                "cost_usd": cost(response.get("usage")), "elapsed_seconds": elapsed}
    path = os.path.join(context["workdir"], "refine-iter{:d}.json".format(artifact["iteration"]))
    try:
        unit, probabilities, reason = parse_refinement(text, set(context["counts"]))
    except ValueError as e:
        artifact["error"] = str(e)
        with open(path, "w") as f:
            json.dump(artifact, f, indent=2)
        raise RuntimeError("LLM refinement answer rejected ({:s}); see {:s}".format(str(e), path)) from None
    artifact.update({"refine": unit, "probabilities": probabilities, "reason": reason})
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2)
    return {"refined": [unit], "seconds": named["seconds"] + elapsed, "llm_seconds": elapsed,
            "signal_seconds": named["seconds"], "probabilities": probabilities, "reason": reason,
            "usage": response.get("usage"), "cost_usd": artifact["cost_usd"], "served_model": response.get("model")}


def strategy(name, description_path=None):
    if name == "bmc":
        return refine_bmc
    if name == "llm":
        if not description_path:
            raise ValueError("--refine llm needs --description")
        with open(description_path) as f:
            description = f.read()
        from deepseek_chat import call_deepseek, chat_text
        from deepseek_prices import usage_cost
        return functools.partial(refine_llm, description=description, call=call_deepseek, extract_text=chat_text,
                                 cost=usage_cost)
    raise ValueError("unknown refinement strategy " + name)
