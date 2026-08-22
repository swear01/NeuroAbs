def extract_info(file_content,target_vars):

    # 存储uext行的信息：{第四个数字: (变量名, 原始行)}
    uext_info = {}
    # 存储需要输出的变量名（没有被引用的uext的变量名）
    unused_vars = []
    
    # 存储uext行的信息：{第四个数字: (变量名, 原始行)}
    uext_info = {}
    # 存储需要输出的变量名（没有被引用的uext的变量名）
    unused_vars = []
    
    # 第一遍遍历：找到所有uext行，但只处理变量名在target_vars中的行
    for line in file_content:
        parts = line.split()
        if len(parts) < 4:
            continue
            
        if parts[1] == 'uext':
            # 提取变量名（如果存在）
            var_name = None
            if ';' in line:
                var_name = line.split(';')[0].strip().split()[5]
            if var_name:    
                # 只有当变量名在target_vars中时才处理
                if var_name and var_name in target_vars:
                    fourth_num = parts[3]
                    uext_info[fourth_num] = (var_name, line)
    
    # 对每个符合条件的uext的第四个数字进行检查
    for fourth_num, (var_name, original_line) in uext_info.items():
        found = False
        
        # 检查每一行
        for line in file_content:
            if line == original_line:  # 跳过自身
                continue
                
            parts = line.split()
            if len(parts) < 2:
                continue
                
            # 跳过第一个数字（index）和第二个数字（如果是宽度）
            search_parts = parts[2:]
            
            # 检查剩余的数字
            for part in search_parts:
                if part.isdigit() and part == fourth_num:
                    found = True
                    break
                    
            if found:
                break
        
        # 如果没有找到引用，则添加到结果中
        if not found:
            unused_vars.append(var_name)
    
    return unused_vars


file_btor = "/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD_Flatten/problem_abstract.btor2"
target_signal = '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD_Flatten/target_signal.txt'
with open(file_btor, 'r') as f:
    file_content = f.readlines()

with open(target_signal,'r') as f:
    signals = [line.strip() for line in f.readlines()]
results = extract_info(file_content,signals)
for var_name in results:
    print(var_name)