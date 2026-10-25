import json
import os
import time

from deepseek_prices import usage_cost
from luna_api import LUNA_USER_AGENT, RATE_LIMIT_MAX_WAIT, RATE_LIMIT_PAUSE, post_json

DEEPSEEK_URL = "http://127.0.0.1:35001/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4.1-flash-1017"
DEEPSEEK_SERVED_MODEL = "deepseek/deepseek-v4.1-flash-1017"
DEEPSEEK_EFFORT = "low"
DEEPSEEK_CALL_LOG = "deepseek_calls.jsonl"
spent_usd = 0.0


def call_deepseek(instructions, user_input, request_id):
    global spent_usd
    budget = os.environ.get("LLM_BUDGET_USD")
    try:
        budget_usd = float(budget) if budget is not None else None
    except ValueError:
        raise RuntimeError("LLM_BUDGET_USD must be a number, got {!r}".format(budget)) from None
    if budget_usd is not None and spent_usd >= budget_usd:
        raise RuntimeError("DeepSeek budget of {:s} USD reached after ${:.4f}".format(budget, spent_usd))
    body = {
        "model": DEEPSEEK_MODEL,
        "reasoning_effort": DEEPSEEK_EFFORT,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_input},
        ],
    }
    headers = {"Content-Type": "application/json", "User-Agent": LUNA_USER_AGENT}
    deadline = time.time() + RATE_LIMIT_MAX_WAIT
    elapsed = 0.0
    while True:
        response, attempt_seconds = post_json(DEEPSEEK_URL, headers, body, request_id, None, DEEPSEEK_CALL_LOG, "DeepSeek")
        elapsed += attempt_seconds
        spent_usd += usage_cost(response.get("usage"))
        served = response.get("model")
        if not isinstance(served, str) or not served:
            raise RuntimeError("DeepSeek response has no model field: {:s}".format(json.dumps(response)[:500]))
        if served == DEEPSEEK_SERVED_MODEL:
            return response, elapsed
        if budget_usd is not None and spent_usd >= budget_usd:
            raise RuntimeError("DeepSeek budget of {:s} USD reached after ${:.4f}".format(budget, spent_usd))
        # Never accept an answer from a model other than the pinned 1017 snapshot.
        if time.time() + RATE_LIMIT_PAUSE > deadline:
            raise RuntimeError("DeepSeek request {:d} still served by {} after {:d} seconds".format(
                request_id, served, RATE_LIMIT_MAX_WAIT))
        print("DeepSeek served {}; pausing {:d} seconds before retrying the same request.".format(served, RATE_LIMIT_PAUSE))
        time.sleep(RATE_LIMIT_PAUSE)


def chat_text(response):
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek response has no choices: {:s}".format(json.dumps(response)[:500]))
    return (choices[0].get("message") or {}).get("content") or ""
