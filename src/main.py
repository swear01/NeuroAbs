from optparse import OptionParser
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYVERILOG_ROOT = os.path.join(PROJECT_ROOT, "Pyverilog_NeuroAbs")
if PYVERILOG_ROOT not in sys.path:
    sys.path.insert(0, PYVERILOG_ROOT)

from example_dataflow_analyzer import lineno_extractor
import importlib
import subprocess
from extract_signal import get_signal
from different import extract_constant_result
import re
from replacer import *
from copy import deepcopy
import json
from aiger import *
import time 

YOSYS_BIN = os.environ.get('YOSYS_BIN', 'yosys')

CONSTANT_PROP_TEMPLATES = {
    'flute': """read_verilog -sv {verilog}

hierarchy -check -top {topmodule}
proc -noopt
flatten

memory
opt
write_verilog problem_1.v
""",
    'piccolo': """read_verilog -sv {verilog}

hierarchy -check -top {topmodule}
proc -noopt
flatten

memory
opt_expr
opt_clean
write_verilog problem_1.v
""",
    'i2c': """read_verilog -sv {verilog}

hierarchy -check -top {topmodule}
proc -noopt
flatten

memory
opt
write_verilog problem_1.v
""",
    'picorv32': """read_verilog -sv {verilog}

hierarchy -check -top {topmodule}
proc

memory -nordff
opt_expr
synth
opt_clean

write_verilog problem_0.v
techmap
dffunmap
abc -fast -g AND
write_verilog problem_1.v
write_aiger -vmap map.txt -symbols -zinit -ascii {aag}
""",
}

REGISTER_CONSTANT_PROP_TEMPLATES = {'picorv32'}

API_BACKENDS = {
    'openrouter': 'openrouter_api',
    'gpt': 'gpt_api',
    'gemini': 'gemini_api',
    'deepseek': 'deepseek_api',
    'llama': 'llama_api',
    'poe': 'poe_api',
}


def infer_constant_prop_template(verilog_file, topmodule):
    if options.constant_template != 'auto':
        return options.constant_template

    path = os.path.abspath(verilog_file).lower()
    if 'picorv32' in path or topmodule.lower() == 'picorv32' or 'riscv_formal' in path:
        return 'picorv32'
    if 'piccolo' in path:
        return 'piccolo'
    if 'i2c' in path or topmodule.lower() == 'tst_bench_top':
        return 'i2c'
    if 'flute' in path:
        return 'flute'
    return 'flute'


def write_constant_prop_script(script_path, template_name, verilog_name):
    template = CONSTANT_PROP_TEMPLATES[template_name]
    content = template.format(
        topmodule=options.topmodule,
        verilog=verilog_name,
        aag=verilog_name.replace('.v', '.aag'),
    )
    with open(script_path, 'w') as f:
        f.write(content)


def get_api_runner(api_backend):
    module_name = API_BACKENDS[api_backend]
    return importlib.import_module(module_name).run_api


def resolve_case_verilog_file(verilog_file):
    verilog_file = os.path.abspath(verilog_file)
    verilog_dir = os.path.dirname(verilog_file)
    base_name = os.path.basename(verilog_file)
    stem, ext = os.path.splitext(base_name)

    if ext != '.v' or stem.endswith('_new'):
        return verilog_file

    new_verilog = os.path.join(verilog_dir, stem + '_new.v')
    new_constant = os.path.join(verilog_dir, stem + '_new_constant.v')
    if os.path.exists(new_verilog) and os.path.exists(new_constant):
        print(
            "Using matched case files: {:s} and {:s}".format(
                os.path.basename(new_verilog),
                os.path.basename(new_constant),
            )
        )
        return new_verilog

    return verilog_file


def add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line_new, current_line_number, offset_number):
    new_replace_input_line = {}
    
    for input_var, lineno in replace_input_line.items():
        if lineno < current_line_number:
            new_replace_input_line[input_var] = replace_input_line_new[input_var]
        else:
            new_replace_input_line[input_var] = replace_input_line_new[input_var] + offset_number
    
    return new_replace_input_line

def collect_replacement_inputs(current_module, instance_map, replace_input_module_map):
    new_inputs = []
    instance_names = [inst for inst, mod in instance_map.items()
                    if mod == current_module]

    for instance in instance_names:
        if instance in replace_input_module_map:
            new_inputs.extend(replace_input_module_map[instance])
        elif current_module in replace_input_module_map: ## Maybe it is the top module
            new_inputs.extend(replace_input_module_map[current_module])

    return new_inputs

def advance_parameter_header(content, start_index, depth):
    port_list_opened = False
    for char in content[start_index:]:
        if depth > 0:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            continue

        if char == '(':
            port_list_opened = True
            break

    return depth, port_list_opened

def process_verilog_content_new(verilog_map, module_map, instance_map, replace_input_map, replace_input_module_map, replace_input_line):
    output_lines = []
    current_module = None  # 用于跟踪当前正在处理的模块
    pending_port_module = None
    pending_param_depth = 0
    replace_input_line_new = {}
    line_nums = sorted(verilog_map.keys())
    for i, line_num in enumerate(line_nums):
        content = verilog_map[line_num]
        
        # 如果当前行在module_map中，说明是模块定义开始
        if line_num in module_map:
            current_module = module_map[line_num]
            if current_module in instance_map.values():
                parameter_match = re.search(r'#\s*\(', content)
                if parameter_match:
                    pending_port_module = current_module
                    pending_param_depth, port_list_opened = advance_parameter_header(
                        content,
                        parameter_match.end(),
                        1,
                    )
                    output_lines.append(content)
                    if not port_list_opened:
                        continue
                else:
                    port_list_opened = '(' in content

                # 处理端口列表：找到第一个端口的位置（通常是带括号的下一行）
                if port_list_opened:
                    next_line_num = line_nums[i + 1]
                    leading_spaces = len(verilog_map[next_line_num]) - len(verilog_map[next_line_num].lstrip())
                    indent = " " * leading_spaces
                    
                    # 收集需要添加的端口
                    new_ports = []
                    for new_input in collect_replacement_inputs(current_module, instance_map, replace_input_module_map):
                        new_ports.append(f"{indent}{new_input},")
                    # 添加新端口
                    if not parameter_match:
                        output_lines.append(content)  # 添加module行
                    for port in new_ports:  # 添加新端口
                        output_lines.append(port)
                    if(len(replace_input_line_new)==0):
                        replace_input_line_new = add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line, line_num, len(new_ports))
                    else:
                        replace_input_line_new = add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line_new, line_num, len(new_ports))
                    pending_port_module = None
                    continue

        if pending_port_module:
            pending_param_depth, port_list_opened = advance_parameter_header(
                content,
                0,
                pending_param_depth,
            )
            output_lines.append(content)
            if port_list_opened:
                next_line_num = line_nums[i + 1]
                leading_spaces = len(verilog_map[next_line_num]) - len(verilog_map[next_line_num].lstrip())
                indent = " " * leading_spaces
                new_ports = [
                    f"{indent}{new_input},"
                    for new_input in collect_replacement_inputs(pending_port_module, instance_map, replace_input_module_map)
                ]
                output_lines.extend(new_ports)
                if(len(replace_input_line_new)==0):
                    replace_input_line_new = add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line, line_num, len(new_ports))
                else:
                    replace_input_line_new = add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line_new, line_num, len(new_ports))
                pending_port_module = None
            continue
        
        output_lines.append(content)
        
        
        if ');' in content and current_module:
            if current_module in instance_map.values():
                # 收集所有需要添加的inputs
                all_new_inputs = {}
                for new_input in collect_replacement_inputs(current_module, instance_map, replace_input_module_map):
                    width = replace_input_map[new_input]
                    all_new_inputs[new_input] = width
                # 获取缩进
                leading_spaces = len(content) - len(content.lstrip())
                indent = " " * leading_spaces
                
                # 生成input声明
                for name, width in all_new_inputs.items():
                    input_decl = f"{indent}input wire [{width-1}:0] {name};"
                    output_lines.append(input_decl)
                
                replace_input_line_new = add_offset_lines_for_replace_input_liner(replace_input_line, replace_input_line_new, line_num, len(all_new_inputs))
            
            
            current_module = None  # 重置当前模块
    
    return output_lines, replace_input_line_new

def process_verilog_content(verilog_map, module_map, instance_map, replace_input_map, replace_input_module_map):
    output_lines = []
    skip_next = False
    
    line_nums = sorted(verilog_map.keys())
    for i, line_num in enumerate(line_nums):
        if skip_next:
            skip_next = False
            continue
            
        content = verilog_map[line_num]
        print(instance_map)
        if line_num in module_map:
            module_name = module_map[line_num]
            if module_name in instance_map.values():
                # 收集所有需要添加的inputs
                all_new_inputs = {}
                instance_names = [inst for inst, mod in instance_map.items() 
                                if mod == module_name]
                print(instance_names)
                for instance in instance_names:
                    print('input collect is: \n ')
                    print(replace_input_map)
                    print('input module is: \n ')
                    print(replace_input_module_map)
                    if instance in replace_input_module_map:
                        new_inputs = replace_input_module_map[instance]
                        for new_input in new_inputs:
                            print(new_input)
                            width = replace_input_map[new_input]
                            all_new_inputs[new_input] = width
                
                # 准备新的input字符串
                leading_spaces = len(content) - len(content.lstrip())
                indent = " " * leading_spaces
                new_input_strs = []
                # for name, width in all_new_inputs.items():
                #     new_input_strs.append(f"input wire [{width-1}:0] {name}")

                for name, width in all_new_inputs.items():
                    new_input_strs.append(f"input wire [{width-1}:0] {name}")

                if len(new_input_strs)!= 0:
                    new_input_text =  indent + "    " + f",\n{indent}    ".join(new_input_strs)
                    
                    if '(' in content:
                        # 处理当前行有括号的情况
                        content = process_line_with_bracket(content, new_input_text)
                    else:
                        # 检查下一行
                        if i + 1 < len(line_nums):
                            next_line_num = line_nums[i + 1]
                            next_content = verilog_map[next_line_num]
                            if '(' in next_content:
                                # 处理下一行的括号
                                next_content = process_next_line_bracket(next_content, new_input_text)
                                verilog_map[next_line_num] = next_content
                                skip_next = True
        
        output_lines.append(content)
    
    return output_lines

def process_line_with_bracket(content, new_input_text):
    content = content.rstrip()
    
    # 处理行尾是 ); 的情况
    if content.endswith(');'):
        parts = content.rsplit(');', 1)
        open_part, rest = parts[0].split('(', 1)
        if rest.strip():  # 如果括号中有内容
            return f"{open_part}({new_input_text}, {rest});"
        else:  # 如果括号是空的
            return f"{open_part}({new_input_text});"
    
    # 处理行尾是 ( 的情况
    if content.endswith('('):
        return content + new_input_text

    # 处理行中有 ( 且有其他内容的情况
    parts = content.split('(')
    return parts[0] + '(' + new_input_text + ', ' + parts[1]

def process_next_line_bracket(content, new_input_text):
    content = content.rstrip()
    leading_spaces = len(content) - len(content.lstrip())
    content = content.lstrip()
    
    # 如果下一行只有括号
    if content == '(':
        return " " * leading_spaces + '(' + new_input_text
    
    # 如果下一行有括号和其他内容
    if content.startswith('('):
        if content.endswith(');'):
            # 处理 (input clk); 的情况
            content = content[1:-2]  # 移除括号和分号
            return " " * leading_spaces + '(' + new_input_text + ', ' + content + ');'
        else:
            # 处理 (input clk, 的情况
            content = content[1:]  # 只移除开始括号
            return " " * leading_spaces + '(' + new_input_text + ', ' + content

    return content


def read_verilog_to_map(file_path):
    file_path = os.path.abspath(file_path)
    verilog_map = {}
    
    with open(file_path, 'r') as file:
        for line_num, line in enumerate(file, 1):  
            verilog_map[line_num] = line.rstrip()  
    file_path_without_assert = file_path.replace('.v', '_noassert.v') ## Since the Pyverilog does not support the assertion block, we comment the assertions       

    with open(file_path_without_assert, 'w') as file:
        for line_num in sorted(verilog_map.keys()):
            line = verilog_map[line_num]
            if "assert property" in line or "assume property" in line or 'assert(' in line or 'assume(' in line or 'assume (' in line:
                file.write("//" + line + '\n')
            else:
                file.write(line + '\n')

    return verilog_map, file_path_without_assert

def replace_filename_in_yosys(file_path, new_filename):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        if 'read_verilog -sv' in line:
            parts = line.split('read_verilog -sv')
            lines[i] = f'{parts[0]}read_verilog -sv {new_filename}\n'
            
        if 'hierarchy -check -top wrapper' in line:
            parts = line.split('hierarchy -check -top')
            lines[i] = f'{parts[0]}hierarchy -check -top {options.topmodule}\n'
            # break
        if 'write_aiger -vmap map.txt -symbols -zinit -ascii' in line:
            parts = line.split('write_aiger -vmap map.txt -symbols -zinit -ascii')
            lines[i] = f'{parts[0]}write_aiger -vmap map.txt -symbols -zinit -ascii {new_filename.replace(".v", ".aag")}\n'
            with open(file_path, 'w') as file:
                file.writelines(lines)
            return new_filename.replace(".v", ".aag")
            # break
    with open(file_path, 'w') as file:
        file.writelines(lines)


def run_constant_prop_for_file(script_name, output_name):
    current_path = os.getcwd()
    script_path = os.path.dirname(os.path.abspath(script_name))
    try:
        os.chdir(script_path)
        yosys_output = output_name.replace('.txt', '_extract.txt')
        with open(yosys_output,'w') as f:
            subprocess.run([YOSYS_BIN, '-g', script_name],
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True)
        get_signal( yosys_output ,output_name, options.prefix)
    finally:
        os.chdir(current_path)


def running_constant_propagation(verilog_file):
    verilog_path = os.path.dirname(os.path.abspath(verilog_file))
    verilog_name = os.path.basename(verilog_file)
    new_path_constant_prop = os.path.join(verilog_path,'.llm4abs_constant_prop.ys')
    template_name = infer_constant_prop_template(verilog_file, options.topmodule)
    write_constant_prop_script(new_path_constant_prop, template_name, verilog_name)
    ## We first run optimizaion for the verilog without setting the constant
    run_constant_prop_for_file(new_path_constant_prop,'normal.txt')
    
    ## We first run optimizaion for the verilog setting the constant    
    verilog_name_constant = verilog_name.replace('.v', '_constant.v')
    verilog_file_constant = os.path.join(verilog_path, verilog_name_constant)
    assert (os.path.exists(verilog_file_constant))
    
    write_constant_prop_script(new_path_constant_prop, template_name, verilog_name_constant)
    run_constant_prop_for_file(new_path_constant_prop,'constant.txt')

    ## After comparing the optimized signals, we can know which signals are optimized based on our setting constant
    current_path = os.getcwd()
    os.chdir(verilog_path)
    extract_constant_result('constant.txt','normal.txt', 'extract.txt')
    with open('extract.txt', 'r') as f:
        extract_signals = f.readlines()
    
    os.chdir(current_path)
    return extract_signals

def running_constant_propagation_reg(verilog_file):
    verilog_path = os.path.dirname(os.path.abspath(verilog_file))
    verilog_name = os.path.basename(verilog_file)
    new_path_constant_prop = os.path.join(verilog_path,'.llm4abs_constant_prop.ys')
    template_name = infer_constant_prop_template(verilog_file, options.topmodule)
    if template_name not in REGISTER_CONSTANT_PROP_TEMPLATES:
        raise ValueError(
            "--use_register requires a register-aware template. "
            "Use --constant-template picorv32, or omit --use_register for "
            "Flute/Piccolo/i2c wrappers."
        )
    write_constant_prop_script(new_path_constant_prop, template_name, verilog_name)
    ## We first run optimizaion for the verilog without setting the constant
    original_aag_path = replace_filename_in_yosys(new_path_constant_prop, verilog_name)
    run_constant_prop_for_file(new_path_constant_prop,'normal.txt')
    
    ## We first run optimizaion for the verilog setting the constant    
    verilog_name_constant = verilog_name.replace('.v', '_constant.v')
    verilog_file_constant = os.path.join(verilog_path, verilog_name_constant)
    assert (os.path.exists(verilog_file_constant))
    
    write_constant_prop_script(new_path_constant_prop, template_name, verilog_name_constant)
    aag_constant_path = replace_filename_in_yosys(new_path_constant_prop, verilog_name_constant)
    run_constant_prop_for_file(new_path_constant_prop,'constant.txt')

    ## After comparing the optimized signals, we can know which signals are optimized based on our setting constant
    current_path = os.getcwd()
    os.chdir(verilog_path)
    extract_constant_result('constant.txt','normal.txt', 'extract.txt')
    with open('extract.txt', 'r') as f:
        extract_signals = f.readlines()
    
    assert ('aag' in original_aag_path and 'aag' in aag_constant_path)
    extract_signals_reg = extract_different_from_aiger(original_aag_path, aag_constant_path)
    combined_extract = list(set(extract_signals_reg + extract_signals))  
    print(combined_extract)
    os.chdir(current_path)
    return combined_extract


def replace_backslash_with_topmodule(variable):
    if variable.startswith('\\'):
        new_variable = options.topmodule  + '.' + variable[1:]
        return new_variable.strip()
    else:
        new_variable = options.topmodule  + '.' + variable
        return new_variable.strip()
    return variable.strip() 

def extract_fully_lines_number(update_info, verilog_map,variable, update_statement_lineno):
    print(update_info.lines)
    variable_in_module = variable.split('.')[-1].strip()
    output_strings = []
    for line in update_info.lines:
        assert line in verilog_map
        output_string = ''
        if ';' not in verilog_map[line]: # We need to find assigning information in the neibourhood
            start_line = line
            for i in range(start_line,-1,-1):
                if variable_in_module in verilog_map[i]:
                    start_line = i
                    break
            
            end_line= line        
            for i in range(end_line,len(verilog_map),1):
                if ';' in verilog_map[i]:
                    end_line = i
                    break
            
            for i in range(start_line, end_line+1, 1):
                output_string += verilog_map[i] + '\n'
            update_statement_lineno[output_string]  = [start_line, end_line]
        
        elif variable_in_module not in verilog_map[line]: # We need to find assigning information in the neibourhood
            start_line = line
            for i in range(start_line,-1,-1):
                if variable_in_module in verilog_map[i]:
                    start_line = i
                    break
            
            end_line= line        
            
            for i in range(start_line, end_line+1, 1):
                output_string += verilog_map[i] + '\n'
            update_statement_lineno[output_string]  = [start_line, end_line]
        
        else:
            assert variable_in_module in verilog_map[line] and ';' in verilog_map[line]
            output_string += verilog_map[line] + '\n'
            update_statement_lineno[output_string]  = [line, line]
        
        output_strings.append(output_string)

    return output_strings, update_statement_lineno

def extract_helper_lines_number(update_info, verilog_map,variable): ## We assume that one variable updating information includes in one block 
    
    max_line = max(update_info.lines)
    min_line = min(update_info.lines)
    output_string = ''
    for line in range(min_line,-1,-1):
        search_pattern = "".join(verilog_map[line].split())
        if 'always@' in search_pattern or 'initial' in search_pattern or 'case(' in search_pattern: # We need to find assigning information in the neibourhood
            min_line = line
            break
        
    
    for line in range(max_line,len(verilog_map),1):
        if verilog_map[line].strip()  == 'end' or verilog_map[line].strip()  == 'endcase': # We need to find assigning information in the neibourhood
            max_line = line
            break
                    
    for i in range(min_line, max_line+1, 1):
        output_string += verilog_map[i] + '\n'
        
    

    return output_string

def get_variable_from_statement(statement):
        if '=' in statement:
            variable = statement.split('=')[0].strip()
            new_variable = replace_backslash_with_topmodule(variable)
        else:
            new_variable = replace_backslash_with_topmodule(statement)
        return new_variable

def gen_signal_update_statement(verilog_map, extract_signals_constant, update_map):
    signal_update_statement = {}
    update_statement_lineno = {}
    signal_helper_statement = {}
    count =  0
    for signal in extract_signals_constant:
        # if signal == '\\RTL.rd_val__h7330\n':
        #     print(signal)
        
        new_variable = get_variable_from_statement(signal)
        if new_variable in update_map:
            update_info = update_map[new_variable]
            count += 1
        else:
            print("New variable {:s} not conclude the update information".format(new_variable))
            continue
       
        output_strings, update_statement_lineno = extract_fully_lines_number(update_info, verilog_map,new_variable, update_statement_lineno)
        signal_update_statement[signal] = output_strings
        if update_info.always_info is not None:
            output_strings_helper = extract_helper_lines_number(update_info, verilog_map,new_variable)
        else:
            output_strings_helper = "".join(output_strings)
        signal_helper_statement[signal] = output_strings_helper

    print('The total number of signal that can be abstract: {:d}'.format(count))
    return signal_update_statement, signal_helper_statement, update_statement_lineno

def construct_message(one_line_statement, helper_statement,constant_value_assign):
    message = 'One-line RTL code:\n'
    message += one_line_statement + '\n'
    message += "Complete code:\n"
    message += helper_statement + '\n'
    message += "The description of the property:\n"
    with open(options.description,'r') as f:
        message += f.read() 
    message += '\n'
    # message += "Here is one brief example, if we only execute the verified instruction, the constant is assigned to the target variable:\n"
    # message += constant_value_assign
    
    return message

def save_maps_to_files(reponse_orginal_statement_map, replace_input_line, statement_file, line_file):
    # 将字典中的列表转换为字符串
    converted_map = {}
    for key, value in reponse_orginal_statement_map.items():
        converted_map[key] = '\t'.join(value)  # 将列表用换行符连接成字符串
    
    # 保存第一个字典
    with open(statement_file, 'w') as f:
        json.dump(converted_map, f, indent=4)
    
    # 保存第二个字典
    with open(line_file, 'w') as f:
        json.dump(replace_input_line, f, indent=4)

def main(topmodule, verilog_file):
    
    verilog_map, file_path_without_assert = read_verilog_to_map(verilog_file)
    start_time = time.time()

    if options.use_register:
        extract_signals_constant = running_constant_propagation_reg(verilog_file)
    else:
        extract_signals_constant = running_constant_propagation(verilog_file)
    end_time = time.time()
    working_path = os.path.dirname(os.path.abspath(file_path_without_assert))
    os.chdir(working_path)
    with open('time_constant_prop.txt','w') as f:
        f.write('The total time of constant propagation is: {:f}\n'.format(end_time - start_time))
        print('The total time of constant propagation is: {:f}'.format(end_time - start_time))

    if options.constant_only:
        print('The total number of constant-propagation candidates is: {:d}'.format(len(extract_signals_constant)))
        return

    update_map, width_map, instance_map, module_map = lineno_extractor(file_path_without_assert, topmodule)
    signal_update_statement, signal_helper_statement, update_statement_lineno = gen_signal_update_statement(verilog_map, extract_signals_constant, update_map)
    # new_verilog_map = deepcopy(verilog_map)
    ## Now we iteratively update the verilog code from the LLM
    count = 0

    replacer = UnknownValReplacer()
    replace_input_map = {}
    replace_input_line = {}
    replace_input_module_map = {}
    reponse_orginal_statement_map = {}
    run_api = get_api_runner(options.api_backend)
    
    variable_visited = []
    start_time = time.time()
    for key,statements in signal_update_statement.items():
        # if count==5:
        #     break
        count +=1

        assert key in signal_helper_statement
        # if(key=='\\RTL.rd_val__h7330\n'):
        #     print(key)
        variable = get_variable_from_statement(key)
        variable_without_module = variable.split('.')[-1]
        if variable_without_module in variable_visited:
            continue
        variable_visited.append(variable_without_module)
        last_module = variable.split('.')[-2]

        for statement in statements:
            
            message = construct_message(statement, signal_helper_statement[key],key)         
            response, result, replaced_input, replace_input_map = run_api(options.robot , message, statement, width_map, replacer, replace_input_map)
            if result == 'unsat':
                start_end = update_statement_lineno[statement]
                
                  
                if replaced_input != '':
                    ##Generally, only generate the new input need the futher consideration
                    
                    replace_input_line[replaced_input] = start_end[0]
                    if last_module not in replace_input_module_map :
                        replace_input_module_map[last_module] =[replaced_input]
                    else:
                        replace_input_module_map[last_module].append(replaced_input)


                
                for line in range(start_end[0], start_end[1]+1):
                    if line == start_end[0]:
                        if replaced_input != '':
                            reponse_orginal_statement_map[replaced_input] = [verilog_map[line]]
                        # new_response =  replacer.replace(response)
                        verilog_map[line] = response.replace('\n','')
                        
                    else:
                        if replaced_input != '':
                            reponse_orginal_statement_map[replaced_input].append(verilog_map[line])
                        verilog_map[line] = ''
                
    
    end_time = time.time()
    
    with open('time.txt','w') as f:
        f.write('The total time is: {:f}\n'.format(end_time - start_time))
        f.write('The average time of abstracting: {:f}\n'.format((end_time - start_time)/count))
        print('The total time is: {:f}'.format(end_time - start_time))
        print('The average time of abstracting: {:f}'.format((end_time - start_time)/count))
    processed_lines, replace_input_line =  process_verilog_content_new(verilog_map, module_map, instance_map, replace_input_map, replace_input_module_map, replace_input_line)
    save_maps_to_files(reponse_orginal_statement_map, replace_input_line, 'statement.json',  'input_line.json')
    with open(os.path.join(working_path, 'wrapper_abstract_llm_new.v'),'w') as f:
        for line in processed_lines:
            # print(line)
            # if line in module_map:
            #     module_name = module_map[line]                     
            #     if module_name in instance_map.values():
            #         instance_names = [instance for instance, module in instance_map.items() 
            #                  if module == module_name]
            #         for instance in instance_names:
            #             new_inputs = replace_input_map[instance]
            #             for new_input in new_inputs:
            #                 width =  replace_input_map[new_input]
            #                 if content.endswith(',')
            #                     content = content + ',' +  f'wire [{str(width-1) : 0}] {new_input}'
            #             # for 
            # else:
            f.write(line+'\n')


if __name__ == '__main__':
    optparser = OptionParser()
    optparser.add_option("-t", "--top", dest="topmodule",
                         default="TOP", help="Top module, Default=TOP")
    optparser.add_option("-d", "--description", dest="description",
                         default="description.txt", help="description of the property")
    optparser.add_option("-f", "--prefix", dest="prefix",
                         default="", help="We only extract the signal with the same prefix")
    optparser.add_option("-r", "--robot", dest="robot",
                         default="RTLabstractor_1", help="Model or bot name passed to the API backend")
    optparser.add_option("--api-backend", dest="api_backend",
                         default="gpt",
                         type="choice",
                         choices=sorted(API_BACKENDS.keys()),
                         help="LLM API backend module. Default=gpt")
    optparser.add_option("--constant-only", action="store_true", dest="constant_only",
                         default=False, help="Run constant propagation and stop before LLM abstraction")
    optparser.add_option("-l", "--use_register", action="store_true",dest="use_register",
                         default=False, help="Also use the constant propagation for the register")
    optparser.add_option("--constant-template", dest="constant_template",
                         default="auto",
                         type="choice",
                         choices=["auto", "flute", "piccolo", "i2c", "picorv32"],
                         help="Constant-propagation Yosys template. Default=auto")
    optparser.add_option("-a", "--aux", dest="auxname",
                         default="", help="The name that can generated to the file")
    (options, args) = optparser.parse_args()
    verilog_file = args
    if len(verilog_file) != 1:
        optparser.error(
            "expected exactly one RTL file. If you split the command across "
            "lines, make sure each backslash is the final character on the "
            "line with no trailing spaces."
        )

    options.description = os.path.abspath(options.description)
    verilog_file[0] = resolve_case_verilog_file(verilog_file[0])
    
    main(options.topmodule, verilog_file[0])
