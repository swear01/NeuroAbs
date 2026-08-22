coi_file = "/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD_Flatten/COI_var.txt" 
influential_vars_file = "/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD_Flatten/coi-check-rev.txt" 

# 解析第一个文件（COI 文件）
def parse_coi_file(filepath):
    coi_map = {}  # 用于存储变量和它的 COI
    with open(filepath, "r") as file:
        current_var = None
        for line in file:
            line = line.strip()
            if not line:  # 跳过空行
                continue
            if line.endswith(":"):  # 检测变量名（COI 的标志）
                current_var = line[:-1]  # 去掉末尾的 ":"
                coi_map[current_var] = set()  # 初始化对应的 COI 集合
            elif current_var:  # 如果在一个变量的 COI 列表中
                coi_map[current_var].add(line)  # 添加到该变量的 COI 中
    return coi_map

# 解析第二个文件（有影响的变量文件）
def parse_influential_vars_file(filepath):
    influential_vars = set()
    with open(filepath, "r") as file:
        for line in file:
            line = line.strip()
            if not line:  # 跳过空行
                continue
            parts = line.split()  # 按空格拆分
            if len(parts) > 1:  # 确保这一行是有效的
                var_name = parts[1].split("@")[0]  # 获取变量名，去掉 @ 后的部分
                influential_vars.add(var_name)
    return influential_vars


def find_influential_in_coi(coi_map, influential_vars):
    result = {}  
    for inf_var in influential_vars:
        result[inf_var] = []  
        for var, coi_set in coi_map.items():
            if inf_var in coi_set:  
                result[inf_var].append(var)  
    return result

def find_cois_with_influential(coi_map, influential_vars):
    result_with_inf = {}  # 存储包含有影响变量的 COI
    result_without_inf = []  # 存储不包含有影响变量的变量名

    for var, coi_set in coi_map.items():  # 遍历每个变量及其 COI
        influential_in_coi = coi_set.intersection(influential_vars)  # 找出 COI 中的有影响变量
        if influential_in_coi:  # 如果 COI 中存在有影响变量
            result_with_inf[var] = list(influential_in_coi)  # 将这些有影响变量记录下来
        else:  # 如果 COI 中不包含任何有影响变量
            result_without_inf.append(var)

    return result_with_inf, result_without_inf

def main():
    
    coi_map = parse_coi_file(coi_file)
    influential_vars = parse_influential_vars_file(influential_vars_file)


    result_with_inf, result_without_inf = find_cois_with_influential(coi_map, influential_vars)


    # for inf_var, related_vars in result.items():
    #     if related_vars: 
    #         print(f"'{inf_var}' is in the COI of: {', '.join(related_vars)}")
    #     else:
    #         print(f"'{inf_var}' is not in any COI.")
    print("Variables whose COI contains influential variables:")
    for var, inf_vars in result_with_inf.items():
        print(f"  {var}: {', '.join(inf_vars)}")

    print("\nVariables whose COI does NOT contain any influential variables:")
    for var in result_without_inf:
        print(f"  {var}")

if __name__ == "__main__":
    main()