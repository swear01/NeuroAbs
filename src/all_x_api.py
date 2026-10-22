from luna_api import next_request_id
from luna_decision_api import apply_decision


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    return apply_decision(
        next_request_id(),
        "all_x",
        {"answer": "x", "probabilities": {"keep": 0.0, "x": 1.0}},
        original_statement,
        width_map,
        replacer,
        replace_input_map,
        {},
    )
