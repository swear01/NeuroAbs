import http.client
import json
import os
import time
import urllib.error
import urllib.request

from check import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LUNA_URL = "https://opencode.ai/zen/go/v1/responses"
LUNA_MODEL = "gpt-6-luna"
LUNA_EFFORT = "low"
LUNA_KEY_FILE = os.path.expanduser("~/.config/opencode_key")
LUNA_USER_AGENT = "neuroabs-experiment/1.0"
LUNA_CALL_LOG = "luna_calls.jsonl"
REWRITE_LOG = "rewrite_records.jsonl"
RATE_LIMIT_PAUSE = 600
RATE_LIMIT_MAX_WAIT = 6 * 3600
SYSTEM_PROMPT = "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()

request_counter = 0


def append_jsonl(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def next_request_id():
    global request_counter
    request_counter += 1
    return request_counter


def response_text(response):
    texts = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                texts.append(part["text"])
    return "".join(texts)


def call_luna(instructions, user_input, request_id):
    session = os.environ.get("LUNA_SESSION_ID")
    if not session:
        raise RuntimeError("LUNA_SESSION_ID is not set.")
    with open(LUNA_KEY_FILE, "r") as f:
        api_key = f.read().strip()
    body = {
        "model": LUNA_MODEL,
        "reasoning": {"effort": LUNA_EFFORT},
        "instructions": instructions,
        "input": user_input,
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "x-opencode-session": session,
        "Content-Type": "application/json",
        "User-Agent": LUNA_USER_AGENT,
    }
    return post_json(LUNA_URL, headers, body, request_id, session, LUNA_CALL_LOG, "Luna")


def post_json(url, headers, body, request_id, session, call_log, label):
    attempt = 0
    transient_retry_used = False
    while True:
        attempt += 1
        started = time.time()
        request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        retry_after = None
        try:
            with urllib.request.urlopen(request, timeout=600) as handle:
                raw = handle.read().decode()
                status = handle.status
            error_text = None
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            status = e.code
            error_text = str(e)
            retry_after = e.headers.get("Retry-After") if e.headers else None
        except (http.client.HTTPException, OSError) as e:
            raw = ""
            status = None
            error_text = repr(e)
        elapsed = time.time() - started
        append_jsonl(call_log, {
            "request_id": request_id,
            "attempt": attempt,
            "session": session,
            "url": url,
            "request": body,
            "status": status,
            "error": error_text,
            "elapsed_seconds": elapsed,
            "response_raw": raw,
            "timestamp": started,
        })
        if status == 200:
            try:
                return json.loads(raw), elapsed
            except json.JSONDecodeError as e:
                raise RuntimeError("{:s} request {:d} returned invalid JSON: {:s}".format(label, request_id, str(e)))
        if status == 429:
            pause = max(RATE_LIMIT_PAUSE, int(retry_after)) if retry_after and retry_after.isdigit() else RATE_LIMIT_PAUSE
            if pause > RATE_LIMIT_MAX_WAIT:
                raise RuntimeError("{:s} request {:d} rate limited for {:d} seconds: {}".format(label, request_id, pause, raw[:500]))
            print(label + " rate limited; pausing {:d} seconds before retrying the same request.".format(pause))
            time.sleep(pause)
            continue
        if not transient_retry_used and (status is None or status >= 500):
            transient_retry_used = True
            time.sleep(30)
            continue
        raise RuntimeError("{:s} request {:d} failed with status {}: {}".format(label, request_id, status, raw[:500] or error_text))


def checked_rewrite(original_statement, abstract_statement, width_map, replacer, replace_input_map):
    try:
        return check_implies(original_statement, abstract_statement, width_map, replacer, replace_input_map), None
    except Exception as e:
        return None, "{:s}: {:s}".format(type(e).__name__, str(e))


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    return run_generate(call_luna, response_text, message, original_statement, width_map, replacer, replace_input_map)


def run_generate(call, extract_text, message, original_statement, width_map, replacer, replace_input_map):
    request_id = next_request_id()
    response, elapsed = call(SYSTEM_PROMPT, initial_context + message, request_id)
    content = extract_text(response)
    checked, check_error = checked_rewrite(original_statement, content, width_map, replacer, replace_input_map)
    if checked is None:
        result, replaced_response, replace_input = "error", "", ""
    else:
        result, replaced_response, replace_input, replace_input_map = checked
    append_jsonl(REWRITE_LOG, {
        "request_id": request_id,
        "mode": "generate",
        "original": original_statement,
        "model_output": content,
        "rewrite": replaced_response,
        "check": result,
        "check_error": check_error,
        "replaced_input": replace_input,
        "usage": response.get("usage"),
        "reasoning": response.get("reasoning"),
        "elapsed_seconds": elapsed,
    })
    return replaced_response, result, replace_input, replace_input_map
