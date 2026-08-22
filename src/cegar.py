import subprocess
import time
import os
import re
import json
from optparse import OptionParser

YOSYS_BIN = os.environ.get('YOSYS_BIN', 'yosys')
ABC_BIN = os.environ.get('ABC_BIN', 'abc')
CEGAR_VERBOSE = os.environ.get('CEGAR_VERBOSE', '0') == '1'
ABC_BMC_BOUND = int(os.environ.get('ABC_BMC_BOUND', '25'))
ABC_BMC_FLAGS = os.environ.get('ABC_BMC_FLAGS', '')
PONO_DYNAMIC_COI_FLAG = os.environ.get('PONO_DYNAMIC_COI_FLAG', '--dynamic_coi_up_cex')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_pono_bin():
    configured = os.environ.get('PONO_BIN')
    candidates = []
    if configured:
        candidates.append(configured)
    candidates.extend([
        os.path.join(PROJECT_ROOT, 'ponocca', 'build', 'pono'),
        os.path.join(PROJECT_ROOT, 'ponocca', 'pono'),
        'pono',
    ])
    for candidate in candidates:
        if os.path.isabs(candidate) or os.sep in candidate:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            return candidate
    raise FileNotFoundError(
        "Pono executable not found. Set PONO_BIN to the built binary, e.g. "
        f"{os.path.join(PROJECT_ROOT, 'ponocca', 'build', 'pono')}"
    )

PONO_BIN = resolve_pono_bin()

def run_yosys_script(yosys_path):
    script_name = os.path.basename(yosys_path)
    log_name = 'yosys_{:s}.log'.format(script_name.replace(os.sep, '_'))
    with open(log_name, 'w') as log_file:
        subprocess.run(
            [YOSYS_BIN, yosys_path],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )

def write_temp_yosys_script(base_yosys_path, content):
    script_name = os.path.basename(base_yosys_path)
    temp_path = os.path.abspath('.cegar_{:s}'.format(script_name))
    with open(temp_path, 'w') as f:
        f.write(content)
    return temp_path

class CEGARLoop:
    def __init__(self, ce_strategy,  process_verilog, original_statement_map, 
                                    revised_map,  initial_module_path, yosys_path, collect_folder= 'iter', timeout =1000):
        self.ce_strategy = ce_strategy
        self.iteration = 0
        self.timeout = timeout
        self.verilog = process_verilog
        self.revised_map = revised_map
        self.original_statement_map = original_statement_map
        self.module_path = initial_module_path
        self.yosys_path = yosys_path 
        self.collect_folder = collect_folder
        self.total_time = 0
    def update_module_path(self, new_path):
        self.module_path = new_path    

    def replace_unmap_input(self, input_mapping):
        count = 0
        for input_name in self.revised_map.keys():
           if input_name not in input_mapping:
                modified_line = self.revised_map[input_name]
                if input_name in self.verilog[modified_line-1]:
                    original_statements = self.original_statement_map[input_name]               
                    self.verilog[modified_line-1] = original_statements + '\n'
                    count += 1
        return count
    
    
    def run_yosys(self,verilog_path):
        return self.ce_strategy.run_yosys(self.yosys_path, verilog_path)
        
    def get_counterexample(self):
        return self.ce_strategy.find_counterexample(self.module_path, self.timeout)
    
    def is_generate_input(self, text):
        if text in self.revised_map:
            return True
        
        else:
            return False
        
    def write_verilog(self):
        if os.path.exists(self.collect_folder) == False:
            os.mkdir(self.collect_folder)
        new_verilog_path = os.path.join(self.collect_folder, str(self.iteration) + '.v')
        with open(new_verilog_path,'w') as f:
            for line in self.verilog:
                f.write(line)
        return new_verilog_path
    
    def refine(self, ce, input_mapping):
        var_visited = []
        count = 0
        for var in ce:
            var_without_module = var.split('.')[-1]
            if var_without_module in var_visited:
                continue
            
            var_visited.append(var_without_module)
            if CEGAR_VERBOSE:
                print(var_without_module)
            if self.is_generate_input(var_without_module):
                ## We need a map to refine the input
                count +=1
                assert (var_without_module in self.revised_map )
                assert (var_without_module in self.revised_map )
                modified_line = self.revised_map[var_without_module]
                assert(var_without_module in self.verilog[modified_line-1])
                original_statements = self.original_statement_map[var_without_module]
                
                self.verilog[modified_line-1] = original_statements + '\n'
        if count == 0:
            count_umap = self.replace_unmap_input(input_mapping)
            if count_umap == 0:
                return "False"
        new_verilog_path = self.write_verilog()
        new_output_path = self.run_yosys(new_verilog_path)        
        self.update_module_path(new_output_path)
        return "Continue"
    
    
    def run(self):
        while True:
            start_time = time.time()
            ce, input_mapping = self.get_counterexample()
            if not ce:
                self.replace_input_with_unknown_value()
                return "No cex found"
            self.iteration +=1
            end_time = time.time()
            self.total_time += end_time - start_time
            result = self.refine(ce, input_mapping)
            if result == "False":
                return "Assertion Fail"

    def replace_input_with_unknown_value(self):
        if os.path.exists(self.collect_folder) == False:
            os.mkdir(self.collect_folder)
        verilog_path = os.path.join(self.collect_folder, str(self.iteration) + '.v')
        if self.iteration == 0:
            with open(verilog_path,'w') as f:
                for line in self.verilog:
                    f.write(line)        
        pattern = r'\binput\d+\b'
        
        with open(verilog_path, 'r') as infile:
            lines = infile.readlines()
        self.run_yosys(verilog_path)
        processed_lines = []
        for line in lines:
            # 直接替换为'bx
            if re.search(pattern, line) and ('input wire' not in line and ',' not in line):
                new_line = re.sub(pattern, "'bx", line)
                processed_lines.append(new_line)
            else:
                processed_lines.append(line)
        
        output_path = os.path.join(self.collect_folder, str(self.iteration) + '_bx' + '.v')
        # 写入新文件
        with open(output_path, 'w') as outfile:
            for line in processed_lines: 
                outfile.write(line)
        
        self.run_yosys(output_path)

class CounterExampleStrategy:
    def find_counterexample(self, model_path, timeout):
        raise NotImplementedError()



class Strategy_bit_level(CounterExampleStrategy):

    def run_yosys(self, yosys_path, verilog_path):
        assert (os.path.exists(yosys_path))
        with open(yosys_path, 'r') as f:
            content = f.read()
        
        # 只替换不含 -sv 的行
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if 'read_verilog' in line:
                if '-sv' not in line:
                    if '-formal' in line:
                        line = re.sub(
                            r'(read_verilog\s+-formal\s+)\S+',
                            r'\1' + verilog_path,
                            line
                        )
                    else:
                        line = re.sub(
                            r'(read_verilog\s+)\S+',
                            r'\1' + verilog_path,
                            line
                        )
            new_lines.append(line)
        content = '\n'.join(new_lines)
        
        # 从input_path生成output_path：把后缀改为.aig
        output_path = re.sub(r'\.[^.]+$', '.aig', verilog_path)
        
        # 替换write_aiger行
        content = re.sub(
            r'(write_aiger -vmap\s+map\.txt\s+)\S+',
            r'\1' + output_path,
            content
        )        
        content = re.sub(
            r'(write_aiger -zinit\s+-vmap\s+map\.txt\s+)\S+',
            r'\1' + output_path,
            content
        )  

        temp_yosys_path = write_temp_yosys_script(yosys_path, content)
        run_yosys_script(temp_yosys_path)
        
        return output_path
        
    
    def find_counterexample(self, model_path, timeout):
        abc_cmd = f'read_aiger {model_path}; fold; bmc3 -F {ABC_BMC_BOUND} {ABC_BMC_FLAGS}; write_cex -o -m -n -v coi.txt'
        process = subprocess.Popen([ABC_BIN, '-c', abc_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            stdout_text = stdout.decode()
            stderr_text = stderr.decode()
            if process.returncode != 0:
                raise RuntimeError(
                    "ABC failed with exit code {:d}.\nSTDOUT:\n{:s}\nSTDERR:\n{:s}".format(
                        process.returncode, stdout_text, stderr_text
                    )
                )
            if "was asserted in frame" in stdout_text:
                assert(os.path.exists('coi.txt'))
                indices = self.parse_cex_file('coi.txt')
                assert(os.path.exists('map.txt'))
                results,input_mapping = self.find_variable_names('map.txt', indices)
                # write_output(results, output_file)
                return results,input_mapping
            
            else:
                return None, None
        
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            return None, None
            
    def parse_cex_file(self, cex_file):
        to_find = []
        with open(cex_file, 'r') as f:
            for line in f:
                name = line.strip().split('@')[0]
                if name.startswith('lo'):
                    index = int(name[2:])
                    to_find.append(('lo', index))
                elif name.startswith('pi'):
                    index = int(name[2:])
                    to_find.append(('pi', index))
        return to_find

    def find_variable_names(self, map_file, indices_to_find):
        results = set()
        lo_count = 0
        pi_count = 0
        lo_indices = {idx: True for type_, idx in indices_to_find if type_ == 'lo'}
        pi_indices = {idx: True for type_, idx in indices_to_find if type_ == 'pi'}
        input_mapping = {}
        with open(map_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                    
                if parts[0] in ('latch', 'lvlatch'):
                    if lo_count in lo_indices:
                        results.add(parts[-1])
                    lo_count += 1
                    
                elif parts[0] in ('init', 'input'):
                    if 'input' in parts[-1]:
                        # print(parts[-1])
                        input_without_module_name = parts[-1].split('.')[-1]
                        input_mapping[input_without_module_name] = True

                    if pi_count in pi_indices:

                        results.add(parts[-1])
                    pi_count += 1
        results = list(results)
        return results, input_mapping
    

    
        

    
    def write_output(self, results, output_file):
        with open(output_file, 'w') as f:
            for index_name, var_name in sorted(results):
                f.write(f'{var_name}\n')

class Strategy_word_level(CounterExampleStrategy):
    def run_yosys(self, yosys_path, verilog_path):
        assert (os.path.exists(yosys_path))
        with open(yosys_path, 'r') as f:
            content = f.read()
        
        # 只替换不含 -sv 的行
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if 'read_verilog' in line:
                if '-sv' not in line:
                    if '-formal' in line:
                        line = re.sub(
                            r'(read_verilog -formal\s+)\S+',
                            r'\1' + verilog_path,
                            line
                        )
                    else:
                        line = re.sub(
                            r'(read_verilog\s+)\S+',
                            r'\1' + verilog_path,
                            line
                        )
            new_lines.append(line)
        content = '\n'.join(new_lines)
        
        output_path = re.sub(r'\.[^.]+$', '.btor2', verilog_path)
        
        content = re.sub(
            r'(write_btor\s+-s\s+)(?:[\w./\-_]+)\.btor2',  # 修改以匹配包含路径的文件名
            fr'\1{output_path}',
            content
        )

        temp_yosys_path = write_temp_yosys_script(yosys_path, content)
        run_yosys_script(temp_yosys_path)
        return output_path
    
    def find_counterexample(self, model_path, timeout,unsat_core = False):
        if unsat_core:
            command_to_run = [
                PONO_BIN,
                '--bound', '25',
                '--promote-inputvars',
                # "--logging-smt-solver",
                '--witness',
                '--pivot_input',
                model_path,
            ]
        else:
            command_to_run = [
                PONO_BIN,
                '--bound', '25',
                '--promote-inputvars',
                # "--logging-smt-solver",
                PONO_DYNAMIC_COI_FLAG,
                model_path,
            ]
        process = subprocess.Popen(command_to_run, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            stdout_text = stdout.decode()
            stderr_text = stderr.decode()
            if re.search(r'(?m)^unknown$', stdout_text):
                print("Pono returned unknown; stopping CEGAR without a usable counterexample.")
                return None, None
            if process.returncode != 0:
                raise RuntimeError(
                    "Pono failed with exit code {:d}.\nSTDOUT:\n{:s}\nSTDERR:\n{:s}".format(
                        process.returncode, stdout_text, stderr_text
                    )
                )
            if re.search(r'(?m)^sat$', stdout_text):
                if unsat_core:
                    if not os.path.exists('pivot_input.txt'):
                        raise RuntimeError(
                            "Pono reported sat but did not write pivot_input.txt. "
                            "Use the tacas24/ponocca build or disable pivot-input extraction."
                        )
                    results, input_mapping = self.find_variable_names_pivot('pivot_input.txt', model_path)
                else:
                    if not os.path.exists('coi-check-rev.txt'):
                        raise RuntimeError(
                            "Pono reported sat but did not write coi-check-rev.txt. "
                            "Use the tacas24/ponocca build or run with a compatible "
                            "counterexample strategy."
                        )
                    results, input_mapping = self.find_variable_names('coi-check-rev.txt', model_path)                    
                # write_output(results, output_file)
                return results, input_mapping
            
            else:
                return None, None
        
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            return None, None


    def find_variable_names(self, filepath, model_path):
        influential_vars = set()
        with open(filepath, "r") as file:
            for line in file:
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                parts = line.split()  # 按空格拆分
                if len(parts) > 1:  # 确保这一行是有效的
                    var_parts = parts[1].split('@')
                    if parts[1].startswith('BTOR_'):
                        var_name = var_parts[1]
                    else:
                        var_name = var_parts[0]
                    influential_vars.add(var_name)
        influential_vars = list(influential_vars)

        input_mapping = {}
        with open(model_path, 'r') as file:
            for line in file:
                columns = line.strip().split()
                
                if len(columns) >= 2 and columns[1] == 'input':
                    if len(columns) >= 4:
                        last_part = columns[3].split('.')[-1]
                        if re.fullmatch(r'input\d+', last_part):
                            input_mapping[last_part] = True

        return influential_vars, input_mapping
    
    def find_variable_names_pivot(self, filepath, model_path):
        influential_vars = set()
        with open(filepath, "r") as file:
            for line in file:
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                parts = line.split()
                if len(parts) >= 3: 
                    var_name = parts[2]  
                    base_name = var_name.split("@")[0]  
                    influential_vars.add(base_name)
        influential_vars = list(influential_vars)

        input_mapping = {}
        with open(model_path, 'r') as file:
            for line in file:
                columns = line.strip().split()
                
                if len(columns) >= 2 and columns[1] == 'input':
                    if len(columns) >= 4:
                        last_part = columns[3].split('.')[-1]
                        if re.fullmatch(r'input\d+', last_part):
                            input_mapping[last_part] = True

        return influential_vars, input_mapping   
    
def load_maps_from_files(statement_file, line_file):
    # 读取第一个字典
    with open(statement_file, 'r') as f:
        reponse_orginal_statement_map = json.load(f)
    
    # 读取第二个字典
    with open(line_file, 'r') as f:
        replace_input_line = json.load(f)
    
    return reponse_orginal_statement_map, replace_input_line

def load_maps_from_files(statement_file, line_file):
    # 读取第一个字典
    with open(statement_file, 'r') as f:
        reponse_orginal_statement_map = json.load(f)
    
    # 读取第二个字典
    with open(line_file, 'r') as f:
        replace_input_line = json.load(f)
    
    return reponse_orginal_statement_map, replace_input_line

def run_yosys_init(yosys_path, verilog_path):
    assert (os.path.exists(yosys_path))
    with open(yosys_path, 'r') as f:
        content = f.read()
    
    # 只替换不含 -sv 的行
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if 'read_verilog' in line:
            if '-sv' not in line:
                if '-formal' in line:
                    line = re.sub(
                        r'(read_verilog -formal\s+)\S+',
                        r'\1' + verilog_path,
                        line
                    )
                else:
                    line = re.sub(
                        r'(read_verilog\s+)\S+',
                        r'\1' + verilog_path,
                        line
                    )
        new_lines.append(line)
    content = '\n'.join(new_lines)
    
    output_path = re.sub(r'\.[^.]+$', '.aig', verilog_path) if 'write_aiger' in content else re.sub(r'\.[^.]+$', '.btor2', verilog_path)
    if output_path.endswith('btor2'):
        content = re.sub(
            r'(write_btor\s+-s\s+)(?:[\w./\-_]+)\.btor2',  # 修改以匹配包含路径的文件名
            fr'\1{output_path}',
            content
        )
    else:
        content = re.sub(
            r'(write_aiger -vmap\s+map\.txt\s+)\S+',
            r'\1' + output_path,
            content
        )        
        content = re.sub(
            r'(write_aiger -zinit\s+-vmap\s+map\.txt\s+)\S+',
            r'\1' + output_path,
            content
        )  

    temp_yosys_path = write_temp_yosys_script(yosys_path, content)
    run_yosys_script(temp_yosys_path)
    
    return output_path

def write_cegar_time(yosys_file, cegar_loop):
    content = ''
    content += yosys_file + '\n'
    content += 'The total iteration is: {:d}\n'.format(cegar_loop.iteration+1)
    content += 'The total time is: {:f}\n'.format(cegar_loop.total_time)
    content += 'The average time of cegar: {:f}\n'.format((cegar_loop.total_time)/(cegar_loop.iteration+1))
    with open('cegar_time.txt','a+') as f:
        f.write(content)
    print(content, end='')


def run_cegar(verilog_file,yosys_file, collector, timeout):
    verilog_file = os.path.abspath(verilog_file)
    yosys_file = os.path.abspath(yosys_file)
    folder_path = os.path.dirname(verilog_file)
    with open(verilog_file,'r') as f:
        process_verlog = f.readlines()

    os.chdir(folder_path)
    assert os.path.exists(yosys_file)
    assert(os.path.exists('statement.json') and os.path.exists('input_line.json'))

    original_statement_map, revised_map = load_maps_from_files('statement.json', 'input_line.json')
    module_path = run_yosys_init(yosys_file, verilog_file)
    if module_path.endswith('.btor2'):
        strategy = Strategy_word_level()
    else:
        strategy = Strategy_bit_level()
        
    start_time = time.time()
    cegar_loop = CEGARLoop(strategy, process_verlog, original_statement_map, revised_map, module_path, yosys_file, collect_folder=collector, timeout=timeout)
    try:
        result = cegar_loop.run()
    except Exception:
        write_cegar_time(options.yosys, cegar_loop)
        raise

    write_cegar_time(options.yosys, cegar_loop)
    if result == "Assertion Fail":
        print("The property fail")

if __name__ == '__main__':
    optparser = OptionParser()
    optparser.add_option("-f", "--folder", dest="folder",
                         default="iter", help="The path that collects the generated btor or aiger")
    optparser.add_option("-y", "--yosys", dest="yosys",
                         default="yosys", help="Yosys script used to build AIG or BTOR2")
    optparser.add_option("--timeout", dest="timeout", type="int",
                         default=90, help="Timeout in seconds for each CEGAR backend query")
    (options, verilog_file) = optparser.parse_args()
    # print(verilog_file)
    run_cegar(verilog_file[0], options.yosys, options.folder, options.timeout)
