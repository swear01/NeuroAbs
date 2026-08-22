import os
import re
import argparse

def find_and_read_includes(file_path, processed_files=None):
    if processed_files is None:
        processed_files = set()
    
    if file_path in processed_files:
        return ""
    
    processed_files.add(file_path)
    
    if not os.path.exists(file_path):
        print(f"Warning: File {file_path} not found")
        return ""
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        # 查找所有的include语句
        includes = re.findall(r'`include\s*"([^"]+)"', content)
        
        final_content = []
        # 添加文件头注释
        final_content.append(f"// Content from {file_path}\n")
        
        # 处理每个include
        for include in includes:
            include_path = os.path.join(os.path.dirname(file_path), include)
            included_content = find_and_read_includes(include_path, processed_files)
            if included_content:
                final_content.append(included_content)
        
        # 添加当前文件的内容
        final_content.append(content)
        
        return "\n".join(final_content)
        
    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")
        return ""

def merge_verilog_files(input_files, output_file):
    all_content = []
    processed_files = set()
    
    for input_file in input_files:
        content = find_and_read_includes(input_file, processed_files)
        if content:
            all_content.append(content)
    
    try:
        with open(output_file, 'w') as f:
            f.write("\n".join(all_content))
        print(f"Successfully merged files into {output_file}")
    except Exception as e:
        print(f"Error writing to output file: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Merge multiple Verilog files and their includes.')
    parser.add_argument('input_files', nargs='+', help='Input Verilog files')
    parser.add_argument('-o', '--output', default='merged_output.v', help='Output file path')
    
    args = parser.parse_args()
    
    # 确保所有输入文件都存在
    for input_file in args.input_files:
        if not os.path.exists(input_file):
            print(f"Error: Input file {input_file} does not exist")
            return
    
    merge_verilog_files(args.input_files, args.output)

if __name__ == "__main__":
    main()