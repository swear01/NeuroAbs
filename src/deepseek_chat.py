import os

from deepseek_prices import usage_cost
from luna_api import LUNA_USER_AGENT, post_json

DEEPSEEK_URL = "http://127.0.0.1:35001/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_EFFORT = "low"
DEEPSEEK_CALL_LOG = "deepseek_calls.jsonl"
spent_usd = 0.0


def call_deepseek(instructions, user_input, request_id):
    global spent_usd
    budget = os.environ.get("LLM_BUDGET_USD")
    if budget is not None and spent_usd >= float(budget):
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
    response, elapsed = post_json(DEEPSEEK_URL, headers, body, request_id, None, DEEPSEEK_CALL_LOG, "DeepSeek")
    spent_usd += usage_cost(response.get("usage"))
    return response, elapsed


def chat_text(response):
    return response["choices"][0]["message"].get("content") or ""
