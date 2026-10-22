import json
import os

from check import preserve_assignment_context
from luna_api import (
    REWRITE_LOG,
    append_jsonl,
    call_luna,
    checked_rewrite,
    next_request_id,
    response_text,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_OPTIONS = ("keep", "x")
PROBABILITY_TOLERANCE = 0.01

with open(os.path.join(SCRIPT_DIR, "decision_context.txt"), "r") as f:
    decision_context = f.read()


def parse_decision(text):
    try:
        decision = json.loads(text)
    except json.JSONDecodeError as e:
        return None, "invalid JSON: {:s}".format(str(e))
    if not isinstance(decision, dict) or set(decision) != {"answer", "probabilities"}:
        return None, "expected exactly the keys answer and probabilities"
    answer = decision["answer"]
    probabilities = decision["probabilities"]
    if answer not in DECISION_OPTIONS:
        return None, "answer is not one of {}".format(DECISION_OPTIONS)
    if not isinstance(probabilities, dict) or set(probabilities) != set(DECISION_OPTIONS):
        return None, "probabilities must contain exactly {}".format(DECISION_OPTIONS)
    for option in DECISION_OPTIONS:
        value = probabilities[option]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            return None, "probability for {:s} is not a number in [0, 1]".format(option)
    if abs(sum(probabilities.values()) - 1) > PROBABILITY_TOLERANCE:
        return None, "probabilities do not sum to 1"
    return decision, None


def x_rewrite(original_statement):
    return preserve_assignment_context(original_statement, "x = 'bx;")


def apply_decision(request_id, mode, decision, original_statement, width_map, replacer, replace_input_map, extra):
    record = {
        "request_id": request_id,
        "mode": mode,
        "original": original_statement,
        "decision": decision,
        "rewrite": "",
        "check": "keep",
        "check_error": None,
        "replaced_input": "",
    }
    record.update(extra)
    replaced_response, result, replace_input = "", "keep", ""
    if decision is not None and decision["answer"] == "x":
        checked, check_error = checked_rewrite(
            original_statement, x_rewrite(original_statement), width_map, replacer, replace_input_map
        )
        if checked is None:
            result = "error"
            record["check_error"] = check_error
        else:
            result, replaced_response, replace_input, replace_input_map = checked
        record.update({"rewrite": replaced_response, "check": result, "replaced_input": replace_input})
    elif decision is None:
        result = "invalid"
        record["check"] = result
    append_jsonl(REWRITE_LOG, record)
    return replaced_response, result, replace_input, replace_input_map


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    request_id = next_request_id()
    response, elapsed = call_luna(decision_context, message, request_id)
    content = response_text(response)
    decision, parse_error = parse_decision(content)
    return apply_decision(
        request_id,
        "decision",
        decision,
        original_statement,
        width_map,
        replacer,
        replace_input_map,
        {
            "model_output": content,
            "parse_error": parse_error,
            "usage": response.get("usage"),
            "reasoning": response.get("reasoning"),
            "elapsed_seconds": elapsed,
        },
    )
