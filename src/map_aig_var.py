def parse_input_file(input_file):
    to_find = []
    with open(input_file, 'r') as f:
        for line in f:
            name = line.strip().split('@')[0]
            if name.startswith('lo'):
                index = int(name[2:])
                to_find.append(('lo', index))
            elif name.startswith('pi'):
                index = int(name[2:])
                to_find.append(('pi', index))
    return to_find

def find_variable_names(names_file, indices_to_find):
    results = []
    lo_count = 0
    pi_count = 0
    
    with open(names_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
                
            if parts[0] in ('latch', 'lvlatch'):
                for type_, index in indices_to_find:
                    if type_ == 'lo' and index == lo_count:
                        # 取最后一个部分作为变量名
                        results.append((f'lo{index:04d}', parts[-1]))
                lo_count += 1
                
            elif parts[0] in ('init', 'input'):
                for type_, index in indices_to_find:
                    if type_ == 'pi' and index == pi_count:
                        # 取最后一个部分作为变量名
                        results.append((f'pi{index:05d}', parts[-1]))
                pi_count += 1
    
    return results

def write_output(results, output_file):
    with open(output_file, 'w') as f:
        for index_name, var_name in sorted(results):
            f.write(f'{var_name}\n')

# 使用示例
input_file = '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/BNE_new/coi.txt'    # 包含lo/pi索引的文件
names_file = '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/BNE_new/map.txt'    # 包含实际变量名的文件
output_file = '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/BNE_new/aig_varmap.txt'  # 输出文件

indices = parse_input_file(input_file)
results = find_variable_names(names_file, indices)
write_output(results, output_file)