import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYVERILOG_ROOT = os.path.join(PROJECT_ROOT, "Pyverilog_NeuroAbs")
if PYVERILOG_ROOT not in sys.path:
    sys.path.insert(0, PYVERILOG_ROOT)

from pyverilog.vparser.lexer import VerilogLexer
from ply import yacc
import pathlib
from z3_gen import *
import re
from replacer import *
class VerilogAssignParser(object):
    def __init__(self, outputdir=".", debug=True):
        self.lexer = VerilogLexer(error_func=self._lexer_error_func)
        self.lexer.build()
        self.tokens = self.lexer.tokens
        
        # 添加缺失的token
        additional_tokens = [
            'UMINUS', 'UPLUS', 'ULNOT', 'UNOT', 
            'UAND', 'UNAND', 'UOR', 'UNOR', 'UXOR', 'UXNOR'
        ]
        self.tokens = self.tokens + tuple(additional_tokens)
        
        pathlib.Path(outputdir).mkdir(parents=True, exist_ok=True)
        self.parser = yacc.yacc(
            module=self,
            method="LALR",
            outputdir=outputdir,
            start='condition',
            debug=debug
        )

    def _lexer_error_func(self, msg, line, column):
        raise Exception(f"Lexer error: {msg} at line {line}, column {column}")

    precedence = (
        ('left', 'COND', 'COLON'),  # 条件运算符
        ('left', 'LOR'),
        ('left', 'LAND'),
        ('left', 'OR'),
        ('left', 'XOR', 'XNOR'),
        ('left', 'AND'),
        ('left', 'EQ', 'NE', 'EQL', 'NEL'),
        ('left', 'LT', 'GT', 'LE', 'GE'),
        ('left', 'LSHIFT', 'RSHIFT', 'LSHIFTA', 'RSHIFTA'),
        ('left', 'PLUS', 'MINUS'),
        ('left', 'TIMES', 'DIVIDE', 'MOD'),
        ('left', 'POWER'),
        ('right', 'UMINUS', 'UPLUS', 'ULNOT', 'UNOT',
         'UAND', 'UNAND', 'UOR', 'UNOR', 'UXOR', 'UXNOR')
    )

    def p_condition(self, p):
        '''condition : DEFAULT COLON assignment
                    | primary COLON assignment
                    | assignment'''
        if len(p)== 2:
            p[0] = p[1]
        else:
            p[0] = ('CONDITION', (p[1]), p[3])


    def p_assignment(self, p):
        '''assignment : ASSIGN ID EQUALS expression SEMICOLON
                    | ID EQUALS expression SEMICOLON
                    | ASSIGN ID LE SEMICOLON
                    | DEFAULT COLON assignment
                    | primary COLON assignment
                    | ID LE expression SEMICOLON'''
        if len(p) == 6:
            p[0] = ('CONTINUOUS_ASSIGN', ('ID', p[2]), p[4])
        else:
            p[0] = ('BLOCKING_ASSIGN', ('ID', p[1]), p[3])

    def p_expression(self, p):
        '''expression : primary
                     | expression PLUS expression
                     | expression MINUS expression
                     | expression TIMES expression
                     | expression DIVIDE expression
                     | expression MOD expression
                     | expression POWER expression
                     | expression LOR expression
                     | expression LAND expression
                     | expression OR expression
                     | expression XOR expression
                     | expression XNOR expression
                     | expression AND expression
                     | expression EQ expression
                     | expression NE expression
                     | expression EQL expression
                     | expression NEL expression
                     | expression LE expression
                     | expression GE expression
                     | expression LT expression
                     | expression GT expression
                     | expression LSHIFT expression
                     | expression RSHIFT expression
                     | expression LSHIFTA expression
                     | expression RSHIFTA expression
                     | PLUS expression %prec UPLUS
                     | MINUS expression %prec UMINUS
                     | LNOT expression %prec ULNOT
                     | NOT expression %prec UNOT
                     | AND expression %prec UAND
                     | NAND expression %prec UNAND
                     | OR expression %prec UOR
                     | NOR expression %prec UNOR
                     | XOR expression %prec UXOR
                     | XNOR expression %prec UXNOR
                     | expression COND expression COLON expression
                     | bit_select
                     | part_select
                     | concat'''
        if len(p) == 2:
            p[0] = p[1]
        elif len(p) == 3:
            p[0] = ('UNOP', p[1], p[2])
        elif len(p) == 6 and p[2] == '?':  # 条件运算符
            p[0] = ('CONDITIONAL', p[1], p[3], p[5])
        else:
            p[0] = ('BINOP', p[2], p[1], p[3])

    def p_concat(self, p):
        '''concat : LBRACE concat_list RBRACE
                | LBRACE replication RBRACE'''
        if len(p) == 4:
            if isinstance(p[2], tuple) and p[2][0] == 'REPLICATION':
                p[0] = p[2]
            else:
                p[0] = ('CONCAT', p[2])

    def p_replication(self, p):
        '''replication : expression LBRACE concat_list RBRACE
                    | expression LBRACE expression RBRACE'''
        if isinstance(p[3], list):
            p[0] = ('REPLICATION', p[1], ('CONCAT', p[3]))
        else:
            p[0] = ('REPLICATION', p[1], p[3])

    def p_concat_list(self, p):
        '''concat_list : expression
                      | concat_list COMMA expression'''
        if len(p) == 2:
            p[0] = [p[1]]
        else:
            p[0] = p[1] + [p[3]]
 
 
 
    def p_bit_select(self, p):
        '''bit_select : ID LBRACKET expression RBRACKET'''
        p[0] = ('BIT_SELECT', p[1], p[3])

    def p_part_select(self, p):
        '''part_select : ID LBRACKET expression COLON expression RBRACKET'''
        p[0] = ('PART_SELECT', p[1], p[3], p[5])

    def p_primary(self, p):
        '''primary : constant
                  | ID
                  | LPAREN expression RPAREN'''
        if len(p) == 4:
            p[0] = p[2]
        elif isinstance(p[1], str) and p[1] != 'ID':
            p[0] = ('ID', p[1])
        else:
            p[0] = p[1]

    def p_constant(self, p):
        '''constant : INTEGER
                   | INTNUMBER_DEC
                   | SIGNED_INTNUMBER_DEC
                   | INTNUMBER_BIN
                   | SIGNED_INTNUMBER_BIN
                   | INTNUMBER_OCT
                   | SIGNED_INTNUMBER_OCT
                   | INTNUMBER_HEX
                   | SIGNED_INTNUMBER_HEX'''
        p[0] = ('CONST', p[1])

    def p_error(self, p):
        if p:
            raise Exception(f"Syntax error at '{p.value}', line {p.lineno}")
        else:
            raise Exception("Syntax error at EOF")

    def parse(self, text):
        return self.parser.parse(text, lexer=self.lexer)

# 测试代码
def test_parser():
    parser = VerilogAssignParser()
    # test_cases = [
    #     "assign a = 42;",
    #     "assign b = 8'b1010_1011;",
    #     "assign c = 16'hABCD;",
    #     "assign result = (8'b1010_1011 + 16'hFFFF) * 42;",
    #     "assign complex = (a & b) | (c ^ d);",
    #     "x = y + z;",
    #     "out = 32'h1234_5678 >> 4;",
    #     "assign d = ~a;",
    #     "assign e = a >>> 2;",
    #     "assign f = &b;",
    #     "assign g = a ^~ b;",
    #     "assign h = a === b;",
    #     "assign data = mem[4:0];",
    #     "assign out = sel ? a : b;",
    #     "a = b? c: d;",
    #     "assign IF_near_mem_imem_instr__59_BITS_6_TO_0_79_EQ_0_ETC___d649 = near_mem$imem_instr[6:0] == 7'b0110011 ? 1'b0 : 'bx;",
    #     "      default: IF_rg_addr_6_BITS_2_TO_0_4_EQ_0x0_18_THEN_SEXT_ETC___d276 =64'd0;",
    #     "  assign master_xactor_f_wr_addr$D_IN ={ 4'd0, mem_req_wr_addr_awaddr__h2473, 8'd0, x__h2520, 18'd65536 } ;",
    #     "  CASE_near_memimem_instr_BITS_6_TO_0_0b10011_N_ETC__q8 =                near_mem$imem_instr[6:0] != 7'b0110111 &&               near_mem$imem_instr[6:0] != 7'b0010111 &&             ((near_mem$imem_instr[6:0] == 7'b0000011) ?                near_mem$imem_instr[14:12] != 3'b0 &&                   near_mem$imem_instr[14:12] != 3'b100 &&               near_mem$imem_instr[14:12] != 3'b001 &&                 near_mem$imem_instr[14:12] != 3'b101 &&                 near_mem$imem_instr[14:12] != 3'b010 :                near_mem$imem_instr[6:0] != 7'b0100011 ||               near_mem$imem_instr[14:12] != 3'b0 &&                near_mem$imem_instr[14:12] != 3'b001 &&                  near_mem$imem_instr[14:12] != 3'b010);"
    # ]
    test_cases = ["  2'b0: CASE_rg_cur_priv_0b0_8_0b1_9_11__q3 = 4'd8; ",
                  "2'b0: CASE_rg_cur_priv_0b0_8_0b1_9_11__q3 = 'bx; "]
    for test in test_cases:
        # try:
            map_temp = {}
            map_temp['CASE_rg_cur_priv_0b0_8_0b1_9_11__q3'] = 4
            print(f"\nParsing: {test}")
            result = parser.parse(test)
            print(result)
            formula, var = build_smt_formula(result,map_temp)
            print("the formula is: \n")
            print(formula)
            for element in result:
                print(element)
            print(f"Result: {result}")
        # except Exception as e:
        #     print(f"Error: {e}")

def preprocess_string(s):
    # 1. 删除换行符
    s = s.replace('\n', '')
    s = s.replace('```', '')
    if '//' in s:
        s = re.sub(r'//.*$', '', s)
    
    if '`' in s:
        s = s.replace('`', '')
    if s.lstrip().startswith('wire '):
        s = s.lstrip()[5:]
    # 2. 用冒号分割并保留后半部分
    if 'default:' in s:
        s = s.split(':', 1)[1]
        # 检查并删除开头的"begin "
        if s.lstrip().startswith('begin '):
            s = s.lstrip()[6:]  # 6是"begin "的长度
    # 3. 如果没有冒号，检查if模式并删除
    elif s.lstrip().startswith('if'):
        s = 'if' + s[2:].lstrip()
        s = s.replace(s[s.find('if('):s.find(')')+1], '')
        # 检查删除if后是否有"begin "
        if s.lstrip().startswith('begin '):
            s = s.lstrip()[6:]
        
    elif s.lstrip().startswith('else if'):
        s = 'else if' + s[7:].lstrip()
        s = s.replace(s[s.find('else if('):s.find(')')+1], '')
        # 检查删除if后是否有"begin "
        if s.lstrip().startswith('begin '):
            s = s.lstrip()[6:]        
    elif s.lstrip().startswith('else'):

        s = s.replace('else', '', 1)  # 删除第一个出现的else
        # 检查删除else if或else后是否有"begin "
        if s.lstrip().startswith('begin '):
            s = s.lstrip()[6:]   
    
    return s


def split_assignment_context(statement):
    compact = " ".join(line.strip() for line in statement.splitlines() if line.strip())
    if not compact:
        return "", "", "=", ""

    le_pos = compact.find("<=")
    eq_pos = compact.find("=")
    if le_pos != -1 and (eq_pos == -1 or le_pos <= eq_pos):
        op = "<="
        op_pos = le_pos
    elif eq_pos != -1:
        op = "="
        op_pos = eq_pos
    else:
        return "", "", "=", compact

    lhs_part = compact[:op_pos]
    rhs_part = compact[op_pos + len(op):].strip()
    if rhs_part.endswith(";"):
        rhs_part = rhs_part[:-1].rstrip()

    prefix = ""
    label_pos = lhs_part.rfind(":")
    if label_pos != -1:
        prefix = lhs_part[:label_pos + 1].rstrip() + " "
        lhs_part = lhs_part[label_pos + 1:]

    lhs_part = lhs_part.strip()
    if lhs_part.startswith("assign "):
        prefix += "assign "
        lhs_part = lhs_part[len("assign "):].strip()

    return prefix, lhs_part, op, rhs_part


def preserve_assignment_context(original_statement, model_statement):
    original_prefix, original_lhs, original_op, _ = split_assignment_context(original_statement)
    _, _, _, model_rhs = split_assignment_context(model_statement)
    if not original_lhs or not model_rhs:
        return model_statement
    return "{:s}{:s} {:s} {:s};".format(
        original_prefix,
        original_lhs,
        original_op,
        model_rhs,
    )


def check_implies(predecessor, successor, width_map, replacer, replace_input_map):
    print("Presecessor: " + predecessor + '\n')
    print("Successor: " + successor + '\n')

    precrocess_predecessor = preprocess_string(predecessor)
    precrocess_succssor = preprocess_string(successor)
    parser = VerilogAssignParser()
    tree_predecessor = parser.parse(precrocess_predecessor)
    tree_successor = parser.parse(precrocess_succssor)
    print("Presecessor: " + precrocess_predecessor + '\n')
    print("Successor: " + precrocess_succssor + '\n')
    predecessor_formula, predecessor_variables, predecessor_unknownvars, condition_assignment_predecessor = build_smt_formula(tree_predecessor, width_map, True)
    successor_formula, successor_variables, sucessor_unknownvars, condition_assignment_sucessor = build_smt_formula(tree_successor, width_map,False)
    
    
    unknown_var_list = []
    for formula, unknown_var in sucessor_unknownvars.items():
        if unknown_var in successor_variables:
            unknown_var_list.append(formula)
    
    
    assert (len(unknown_var_list) == 1 or len(unknown_var_list) == 0)
    
    if len(unknown_var_list) == 1:
        replaced_successor, replaced_input = replacer.replace(successor)
        replaced_successor = preserve_assignment_context(predecessor, replaced_successor)
        replace_input_map[replaced_input] = unknown_var_list[0].size()
    else:
        replaced_successor = preserve_assignment_context(predecessor, successor)
        replaced_input = ''
    if len(unknown_var_list) != 0:
        successor_formula = Exists(unknown_var_list, successor_formula)
            
    
    check_formula = Not(Implies(predecessor_formula, successor_formula))
    s = Solver()
    s.add(check_formula)


    
    with open("abstract_result.txt",'a') as f:
        f.write(precrocess_predecessor + '\n')
        f.write(precrocess_succssor + '\n')
        if s.check() == sat:
            m = s.model()
            f.write('sat\n')
            f.write("Solution:")
            for var in predecessor_variables:
                f.write(f" {var} = {m[predecessor_variables[var]]}")
            for var in successor_variables:
                f.write(f" {var} = {m[successor_variables[var]]}")
            f.write('\n')
            return 'sat', replaced_successor, replaced_input, replace_input_map
        else:
            # print("No solution")    
            f.write('unsat\n')
            return 'unsat', replaced_successor,  replaced_input,replace_input_map


if __name__ == "__main__":
    # s = preprocess_string("if(monitor_s1_already_enter_cond) begin monitor_s1_already <= 1'b1;")
    # print("after processing: " +s)
    predecessor = "instr_rdcycleh <= ((mem_rdata_q[6:0] == 7'b1110011 && mem_rdata_q[31:12] == 'b11001000000000000010) ||                            (mem_rdata_q[6:0] == 7'b1110011 && mem_rdata_q[31:12] == 'b11001000000100000010)) && ENABLE_COUNTERS && ENABLE_COUNTERS64;"
    successor = "instr_rdcycleh <= ((mem_rdata_q[6:0] == 7'b1110011 && mem_rdata_q[31:12] == 'b11001000000000000010) ||                            (mem_rdata_q[6:0] == 7'b1110011 && mem_rdata_q[31:12] == 'b11001000000100000010)) && ENABLE_COUNTERS && 'bx; "
    width_map = {}
    width_map['instr_rdcycleh'] =1 
    width_map['ENABLE_COUNTERS'] = 1
    width_map['ENABLE_COUNTERS64'] = 1
    width_map['mem_rdata_q'] = 32
    
    # width_map['instr_sltu'] = 1
    # width_map['arb2'] = 32
    replacer = UnknownValReplacer()
    replace_input_map = {}
    check_implies(predecessor, successor, width_map,replacer,replace_input_map)
    # test_parser()
