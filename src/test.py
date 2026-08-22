from pyverilog.vparser.lexer import VerilogLexer


def test_lexer():
    lexer = VerilogLexer(lambda msg, line, col: print(f"Error: {msg} at line {line}, column {col}"))
    lexer.build()
    
    # 测试1：以module开始
    test1 = '''
    module test;
    wire a;
    endmodule
    '''
    
    # 测试2：不以module开始
    test2 = '''
    assign alu_outputs___1_addr__h5385 =\t     near_mem$imem_pc +\t     { {11{near_memimem_instr_BIT_31_CONCAT_near_memime_ETC__q2[20]}},\t       near_memimem_instr_BIT_31_CONCAT_near_memime_ETC__q2 } ;
    '''
    
    print("Test 1 - Starting with module:")
    lexer.input(test1)
    while True:
        tok = lexer.token()
        if not tok:
            break
        print(tok)
    
    print("\nTest 2 - Not starting with module:")
    lexer.input(test2)
    while True:
        tok = lexer.token()
        if not tok:
            break
        print(tok)

# 运行测试
if __name__ == '__main__':
    test_lexer()