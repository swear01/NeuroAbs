from openai import OpenAI
import os
from check import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    print(message + '\n')
    api_key = os.environ.get("META_API_KEY")
    if not api_key:
        raise RuntimeError("META_API_KEY is not set.")
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.meta.ai/v1",
    )
    response = client.chat.completions.create(
        model="muse-spark-1.2-contributor",
        messages=[
            {"role": "system", "content": "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"},
            {"role": "user", "content": initial_context + message},
        ],
        stream=False,
    )
    print(response)
    if not response.choices or not response.choices[0].message.content:
        raise RuntimeError("Meta API returned no content.")
    content = response.choices[0].message.content
    print(content)
    result, replaced_response, replace_input, replace_input_map = check_implies(
        original_statement,
        content,
        width_map,
        replacer,
        replace_input_map,
    )
    return replaced_response, result, replace_input, replace_input_map
