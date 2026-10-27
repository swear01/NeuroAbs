import json
import os

from deepseek_prices import usage_cost
from luna_api import LUNA_USER_AGENT, post_json

DEEPSEEK_URL = "http://127.0.0.1:35001/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_EFFORT = "low"
DEEPSEEK_CALL_LOG = "deepseek_calls.jsonl"
spent_usd = 0.0


def call_deepseek(instructions, user_input, request_id):
    return call_deepseek_messages([{"role": "system", "content": instructions},
                                   {"role": "user", "content": user_input}], request_id)


def call_deepseek_messages(messages, request_id):
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
        "messages": messages,
    }
    headers = {"Content-Type": "application/json", "User-Agent": LUNA_USER_AGENT}
    response, elapsed = post_json(DEEPSEEK_URL, headers, body, request_id, None, DEEPSEEK_CALL_LOG, "DeepSeek")
    spent_usd += usage_cost(response.get("usage"))
    served = response.get("model")
    if not isinstance(served, str) or not served:
        raise RuntimeError("DeepSeek response has no model field: {:s}".format(json.dumps(response)[:500]))
    return response, elapsed


def chat_text(response):
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek response has no choices: {:s}".format(json.dumps(response)[:500]))
    return (choices[0].get("message") or {}).get("content") or ""
