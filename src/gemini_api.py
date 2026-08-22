import google.generativeai as genai
import pdfplumber
from google.generativeai import caching
from check import *
import datetime
import os

riscv_path = 'related_pdf/riscv_card.pdf'
verilog_path = 'related_pdf/978-3-031-44104-2.pdf'
api_key = os.environ.get("API_KEY", "")
if not api_key:
    raise RuntimeError("API_KEY is not set.")
genai.configure(api_key=api_key)
# 从文件中加载上下文内容
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SCRIPT_DIR, "initial_context.txt"), "r") as f:
    initial_context = f.read()

def pdf_to_text(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"PDF转换错误: {e}")
        return None
riscv_content = pdf_to_text(riscv_path)    
verilog_content = pdf_to_text(verilog_path)  
# 创建缓存内容
# predefined_content = initial_context + "Here, I will give you some relative background information in the RISCV: \n "+ riscv_content
predefined_content = initial_context #+ "Here, I will give you some relative background information in the RISCV: \n "+ riscv_content
try:
    cache = caching.CachedContent.create(
        model="models/gemini-1.5-flash-001",  # 确保模型名称正确并支持缓存
        system_instruction="Now you are an expert in the hardware design and formal verification",
        contents=[predefined_content*8],  # 传递实际内容，而非文件路径
        ttl=datetime.timedelta(minutes=60),  # 缓存时间
    )
    print(f"缓存已创建: {cache.name}")  # 输出缓存 ID

except Exception as e:
    print(f"缓存创建失败: {e}")
    cache = None  # 在失败时设置为 None

# 定义 API 调用函数
def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    print(message + '\n')
    
    if cache is None:
        print("缓存不可用，无法继续执行 API 调用。")
        return None, None

    # 使用缓存初始化模型
    model = genai.GenerativeModel.from_cached_content(cached_content=cache)
    try:
        # 调用模型生成文本
        response = model.generate_content([message])
        print(response.text)

        # 处理生成结果
        result, replaced_response, replace_input, replace_input_map = check_implies(original_statement, 
                                                                                     response.text, width_map, replacer, replace_input_map)
        return replaced_response, result, replace_input ,replace_input_map 

    except Exception as e:
        print(f"模型生成失败: {e}")
        with open('error.txt', 'a+') as f:
            # f.write(response.text + '\n')
            f.write(original_statement + '\n')
            f.write(f"模型生成失败: {e}")
        return None, None, None, replace_input_map
