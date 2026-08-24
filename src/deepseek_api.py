
from openai import OpenAI
import os
from check import *
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()
def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    print(message + '\n')
    client = OpenAI(
        api_key="local-gateway",
        base_url="http://127.0.0.1:35001/v1",
    )
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"}, 
            {"role": "user", "content": initial_context + message}
        ],
        stream=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
    print(response)
    print(response.choices[0].message.content)
    result, replaced_response, replace_input, replace_input_map = check_implies(
        original_statement,
        response.choices[0].message.content,
        width_map,
        replacer,
        replace_input_map,
    )
    return replaced_response, result, replace_input, replace_input_map
