def extract_constant_result(file_a, file_b, output_file):
    try:
        with open(file_a, 'r') as a_file:
            a_lines = {line.strip() for line in a_file.readlines()}


        with open(file_b, 'r') as b_file:
            b_lines = {line.strip() for line in b_file.readlines()}

        unique_lines = a_lines - b_lines

        with open(output_file, 'w') as out_file:
            for line in sorted(unique_lines):
                out_file.write(line + '\n')

        print(f"Unique lines from {file_a} written to {output_file}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")



# file_a = "/hpc/home/connect.zyan760/DreamMiner2/Piccolo_verification/verification/ADD/constant.txt"  # 第一个文件
# file_b = "/hpc/home/connect.zyan760/DreamMiner2/Piccolo_verification/verification/ADD/normal.txt"  # 第二个文件
# output_file = "/hpc/home/connect.zyan760/DreamMiner2/Piccolo_verification/verification/ADD/extract_1.txt"  # 输出文件

# extract_constant_result(file_a, file_b, output_file)
