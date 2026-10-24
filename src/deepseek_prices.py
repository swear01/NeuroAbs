# DeepSeek peak-hour list prices per million tokens; off-peak is half.
DEEPSEEK_INPUT_PRICE = 0.30
DEEPSEEK_CACHED_INPUT_PRICE = 0.006
DEEPSEEK_OUTPUT_PRICE = 1.20


def usage_cost(usage):
    usage = usage or {}
    prompt = usage.get("prompt_tokens", 0)
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    return ((prompt - cached) * DEEPSEEK_INPUT_PRICE + cached * DEEPSEEK_CACHED_INPUT_PRICE
            + usage.get("completion_tokens", 0) * DEEPSEEK_OUTPUT_PRICE) / 1e6
