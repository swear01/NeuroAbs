def get_signal(input_filename, output_filename, prefix):
    try:
        with open(input_filename, 'r') as infile:
            lines = infile.readlines()


        with open(output_filename, 'w') as outfile:
            found_expr_key_line = False
            found_clean_key_line = False
            lines_after_expr_key = 0

            for line in lines:
               
                line = line.rstrip()


                if not found_expr_key_line and "Executing OPT_EXPR pass (perform const folding)." in line:
                    found_expr_key_line = True
                    continue  

                if found_expr_key_line:
                    lines_after_expr_key += 1
                    if lines_after_expr_key <= 2:
                        continue  
                   

                    if line.startswith(f'\\{prefix}'):
                        outfile.write(line + '\n')  

                    if line.strip() == "":
                        found_expr_key_line = False  
                        lines_after_expr_key = 0  

                if not found_clean_key_line and "Executing OPT_CLEAN pass (remove unused cells and wires)." in line:
                    found_clean_key_line = True
                    continue 

                if found_clean_key_line:
                    # We assume the optimize part locate in the submodule RTL, so we find whether the signal starts with \RTL
                    if line.startswith("\\RTL."):
                        outfile.write(line + '\n') 

                    
                    if line.strip() == "":
                        found_clean_key_line = False  

        print(f"Processing complete. Results written to {output_filename}")
    
    except FileNotFoundError:
        print(f"Error: The file {input_filename} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


