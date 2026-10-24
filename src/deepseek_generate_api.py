from deepseek_chat import call_deepseek, chat_text
from luna_api import run_generate


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    return run_generate(call_deepseek, chat_text, message, original_statement, width_map, replacer, replace_input_map)
