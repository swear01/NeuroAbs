import requests
import json
import os
from check import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()
url = os.environ.get("API_URL", "")
api_key = os.environ.get("API_KEY", "")
if "hkust-gz.edu.cn" in url:
    auth_value = api_key
else:
    auth_value = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
headers = {
    "Content-Type": "application/json",
    "Authorization": auth_value,
}

# def generate():
#     for chunk in response.iter_lines():
#         if chunk:  # filter out keep-alive new chunks
#             yield chunk      
# for i in range(1,5):
#     data = {
#         "model": "gpt-3.5-turbo",# "gpt-3.5-turbo" version in gpt-4o-mini, "gpt-4" version in gpt-4o-2024-08-06
#         "messages":[
#         {"role": "system", "content": "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"}, 
#         {"role": "user", "content": initial_context}
#     ],
#     }
#     response = requests.post(url, headers=headers, data=json.dumps(data))
#     for chunk in generate():
#         chunk_str = chunk.decode('utf-8')
#         chunk_str = chunk_str.replace('data: ', '')  # decode the binary data to string
#         chunk_json = json.loads(chunk_str)  # convert the JSON string to a Python dictionary
#         print(chunk_json)
#         break
#     print(chunk_json['choices'][0]['message']['content'])

def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    if not api_key:
        raise RuntimeError("API_KEY is not set.")
    if not url:
        raise RuntimeError("API_URL is not set.")

    print(message + '\n')



    try:
        # 调用模型生成文本
 
 
        data = {
            "model": "gpt-3.5-turbo",# "gpt-3.5-turbo" version in gpt-4o-mini, "gpt-4" version in gpt-4o-2024-08-06
            "messages":[
            {"role": "system", "content": "Now you are an expert in the hardware design and formal verification, help me generate the abstraction for the given RTL statement"}, 
            {"role": "user", "content": initial_context + message}
        ],
        }
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        try:
            chunk_json = response.json()
        except json.JSONDecodeError:
            chunk_json = None
            for chunk in response.iter_lines():
                if not chunk:
                    continue
                chunk_str = chunk.decode('utf-8')
                if chunk_str.startswith('data: '):
                    chunk_str = chunk_str[len('data: '):]
                if chunk_str == '[DONE]':
                    continue
                chunk_json = json.loads(chunk_str)
                break
            if chunk_json is None:
                raise RuntimeError(f"Empty response from API_URL={url}")

        print(chunk_json)
        content = chunk_json['choices'][0]['message']['content']
        print(content)
        # 处理生成结果
        result, replaced_response, replace_input, replace_input_map = check_implies(original_statement, 
                                                                                     content, width_map, replacer, replace_input_map)
        return replaced_response, result, replace_input ,replace_input_map 

    except Exception as e:
        print(f"模型生成失败: {e}")
        with open('error.txt', 'a+') as f:
            if 'response' in locals():
                f.write(response.text + '\n')
            f.write(original_statement + '\n')
            f.write(f"模型生成失败: {e}")
        return None, None, None, replace_input_map 
