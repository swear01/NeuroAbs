import google.generativeai as genai
import os
import pathlib
import textwrap
import re
import argparse
import requests

# Proxy configuration
# proxy_url should be provided through local environment/config, not committed.
# from urllib.parse import urlparse
# parsed = urlparse(proxy_url)
# proxy_address = parsed.hostname
# proxy_port = parsed.port

# # Set environment variables for proxy
# os.environ['HTTP_PROXY'] = f'http://{proxy_address}:{proxy_port}'
# os.environ['HTTPS_PROXY'] = f'http://{proxy_address}:{proxy_port}'

# # Test proxy connection before making Gemini API calls
# def test_proxy():
#     try:
#         response = requests.get('https://api.ipify.org?format=json', timeout=50)
#         print(f"Proxy connection successful. Current IP: {response.json()['ip']}")
#         return True
#     except Exception as e:
#         print(f"Proxy connection failed: {str(e)}")
#         return False

# # Gemini configuration and API calls
# try:
#     if test_proxy():
#         genai.configure(api_key=os.environ["API_KEY"])
#         # model = genai.GenerativeModel("gemini-1.5-pro")
#         model = genai.GenerativeModel("gemini-1.5-flash")
#         response = model.generate_content("Tell me something about NBA.")
#         print(response.text)
#     else:
#         print("Please check proxy connection before proceeding.")
# except Exception as e:
#     print(f"Error with Gemini API: {str(e)}")

genai.configure(api_key=os.environ["API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content("Who is Lebron James. Use Chinese to answer my question")
print(response.text)
# # Use pathlib for more robust path handling
# def read_file_content(file_path):
#     with open(file_path, 'r') as file:
#         return file.read()

# def create_lont_text(cpp_content, SMT_LIB2_content, origin_c_content):
#     return textwrap.dedent(
#     f"""
#     try to find the correct symbol name in `smtlib_reader.lookup_symbol` in this program
#     {cpp_content}

#     You should look up this SMT-lib2
#     {SMT_LIB2_content}

#     The original C model is here
#     {origin_c_content}

#     For understanding the assertion in SMT-lib2, for example:
#     ` (assert (= |main::1::dividend!0@1#1| |symex::args::0|)) ` this means an assertion for dividend, and `symex::args::0` is not the correct answer for this task. 

#     Both input and output format for `smtlib_reader.lookup_symbol` are needed, 
#     for example: the code have two inputs var and one output var, so you need to return 3 lines as `smtlib_reader.lookup_symbol(`

#     If the input and output of the main function call other functions, the final output should be based on the content of these other functions. for example: `|main::1::a!0@1#2|` is not the correct answer because the main function input a is definitely used in other function, so the correct answer is `__mulsf3::a!0@1#1`

#     When you find the answer, please check the answer is not begin with `symex::args`, because this is for `assert`.
    
#     Only Return the line of ` smtlib_reader.lookup_symbol(` , think slowly and step by step
#     """
# )

# def extract_lookup_symbols(text):
#     cleaned_text = text.replace("```cpp\n", "").replace("```\n", "")
#     matches = re.findall(r'auto (\w+) = smtlib_reader\.lookup_symbol\("\|?([^"]+?)\|?"\);', cleaned_text)
#     return [(var, symbol) for var, symbol in matches]

# def format_symbols(matches):
#     formatted_output = ""
#     for var, symbol in matches:
#         formatted_output += f'a'