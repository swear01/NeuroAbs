
from openai import OpenAI
import time
import os
from check import *
api_key = os.environ.get("API_KEY", "")
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()
def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    if not api_key:
        raise RuntimeError("API_KEY is not set.")

    print(message + '\n')



    try:
        # 调用模型生成文本
        response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"}, 
            {"role": "user", "content": initial_context + message}
        ],
        stream=False
        )
        print(response)
        print(response.choices[0].message.content)
        # print(response.text)

        # 处理生成结果
        result, replaced_response, replace_input, replace_input_map = check_implies(original_statement, 
                                                                                     response.choices[0].message.content, width_map, replacer, replace_input_map)
        return replaced_response, result, replace_input ,replace_input_map 

    except Exception as e:
        print(f"模型生成失败: {e}")
        with open('error.txt', 'a+') as f:
            # f.write(response.text + '\n')
            f.write(original_statement + '\n')
            f.write(f"模型生成失败: {e}")
        return None, None, None, replace_input_map
