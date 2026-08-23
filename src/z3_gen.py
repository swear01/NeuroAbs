from z3 import *
from functools import reduce  



class Assignment2SMT():
    def __init__(self):
        self.assignments = []
        # 存储Z3变量的字典
        self.z3_vars = {}
        self.unknown_vars = {}
        # 创建Z3求解器
        self.solver = Solver()

    def get_or_create_z3_var(self, var_name, width_map, is_unknown = False):
        """获取或创建Z3变量"""
        width = width_map[var_name]
        if var_name not in self.z3_vars:
            self.z3_vars[var_name] = BitVec(var_name, width)
            if is_unknown:
                self.unknown_vars[self.z3_vars[var_name]] = var_name

        return self.z3_vars[var_name]

    def parse_constant(self, const_str,width_map):
        # 处理不同格式的常量
        if "'" in const_str:
            # 处理带位宽的常量，如 8'b1010_1011, 16'hABCD
            width, value = const_str.split("'")
            
            # width = 32 #统一使用32位
            
                # 为这个不确定值创建一个新的符号变量
            if 'x' in value.lower() or 'z' in value.lower():  # 处理含x或z的情况
                var_name = f"unknown_{len(self.z3_vars)}"
                if width !='':
                    width_map[var_name] = int(width)
                    return self.get_or_create_z3_var(var_name, width_map,True) 
                else:
                    width_map[var_name] = 32 ##先随机设定为32
                    return self.get_or_create_z3_var(var_name, width_map, True)           
            if width != '':
                width = int(width)
            else:
                width = len(value) - 1
            if value.startswith('b'):  # 二进制
                value = value[1:].replace('_', '')
                return BitVecVal(int(value, 2), width)
            elif value.startswith('h'):  # 十六进制
                value = value[1:].replace('_', '')
                return BitVecVal(int(value, 16), width)
            elif value.startswith('d'):  # 十进制
                value = value[1:].replace('_', '')
                return BitVecVal(int(value, 10), width)
        else:
            # 普通十进制数    
            value = int(const_str)
            bits_needed = max(value.bit_length(), 1)
            return BitVecVal(value, bits_needed)

    def to_bitvec(self, expr, width):
        """将不同类型转换为BitVec"""
        if isinstance(expr, BitVecRef):
            return expr
        elif isinstance(expr, BoolRef):
            return If(expr, BitVecVal(1, width), BitVecVal(0, width))
        # elif isinstance(expr, IntNumRef):
        #     return BitVecVal(expr.as_long(), width)
        # elif isinstance(expr, int):
        #     return BitVecVal(expr, width)
        else:
            raise TypeError(f"无法将类型 {type(expr)} 转换为BitVec")

    def refine_unknown_width(self,unknown_var,width):
        var = self.unknown_vars[unknown_var] ##在一次处理
        del self.unknown_vars[unknown_var]
        del self.z3_vars[var]

        new_unknown_var = BitVec(var, width)        
        self.unknown_vars[new_unknown_var] = var
        self.z3_vars[var] = new_unknown_var
        return new_unknown_var
    
    def traverse(self, node, width_map):
        # 处理叶子节点
        if not isinstance(node, tuple):
            return node
            
        node_type = node[0]
 
        if node_type == 'ID':
            return self.get_or_create_z3_var(node[1], width_map)
            
        if node_type == 'CONST':
            return self.parse_constant(node[1], width_map)
        if node_type == 'CONDITION':
           formula = self.traverse(node[2],width_map)     
           return formula
        # 处理赋值语句
        if node_type in ['CONTINUOUS_ASSIGN', 'BLOCKING_ASSIGN']:
            lhs = self.traverse(node[1],width_map)
            if node[2][0] == 'ID' and node[2][1] not in width_map:
                width_map[node[2][1]] = lhs.size()
            rhs = self.traverse(node[2],width_map)
            if rhs in self.unknown_vars: ## 我们对unknown val进行修改
                width = lhs.size()
                var = self.unknown_vars[rhs] ##在一次处理
                del self.unknown_vars[rhs]
                del self.z3_vars[var]
                new_rhs = BitVec(var, width)
                self.z3_vars[var] = new_rhs
                self.unknown_vars[new_rhs] = var
                return lhs == new_rhs
            elif lhs in self.unknown_vars:
                width = rhs.size()
                var = self.unknown_vars[lhs] ##在一次处理
                del self.unknown_vars[lhs]
                del self.z3_vars[var]
                new_lhs = BitVec(var, width)
                self.z3_vars[var] = new_lhs
                self.unknown_vars[new_lhs] = var
                return new_lhs == rhs            
            elif (not isinstance(lhs, BoolRef)) and (not isinstance(rhs, BoolRef)) and lhs.size() != rhs.size():
                if rhs.size() < lhs.size():
                    rhs = ZeroExt(lhs.size() - rhs.size(), rhs)
                else:
                    rhs = Extract(lhs.size() - 1, 0, rhs)
                return lhs == rhs
            else:    
                if isinstance(rhs, BoolRef):
                    return lhs == If(rhs, BitVecVal(1, 1), BitVecVal(0, 1))
                else:
                    return lhs == rhs
            
            # 处理二元操作
        if node_type == 'BINOP':
            op = node[1]
            if node[2][0] == 'ID' and node[2][1] not in width_map and node[3][0] == 'ID' and node[3][1] in width_map:
                width_map[node[2][1]] = width_map[node[3][1]]
            if node[3][0] == 'ID' and node[3][1] not in width_map and node[2][0] == 'ID' and node[2][1] in width_map:
                width_map[node[3][1]] = width_map[node[2][1]]
            left = self.traverse(node[2], width_map)
            right = self.traverse(node[3], width_map)
            if left in self.unknown_vars and right in self.unknown_vars:
                final_var = self.get_or_create_z3_var(var_false,width_map,True)
                return final_var
            elif left in self.unknown_vars:
                if isinstance(right, BoolRef):
                    left = self.refine_unknown_width(left,1)
                else:
                    left = self.refine_unknown_width(left,right.size())
            elif right in self.unknown_vars:
                if isinstance(left, BoolRef):
                    right = self.refine_unknown_width(right ,1)
                else:    
                    right = self.refine_unknown_width(right ,left.size())
            elif (not isinstance(left, BoolRef)) and (not isinstance(right, BoolRef))  and left.size() != right.size():
                assert isinstance(left, BitVecNumRef) and isinstance(right, BitVecNumRef)
                if isinstance(right, BitVecNumRef):
                    right = BitVecVal(int(right.as_string()), left.size())
                else:
                    left = BitVecVal(int(left.as_string()), right.size())
            # 对于逻辑运算符，保持Bool类型
            if op in ['&&', '||']:
                # 如果操作数是BitVec，转换为Bool
                if isinstance(left, BitVecRef):
                    left = left != 0
                if isinstance(right, BitVecRef):
                    right = right != 0
                
                if op == '&&':
                    return And(left, right)
                else:  # op == '||'
                    return Or(left, right)
            
            # 对于比较运算符，保持Bool类型
            elif op in ['==', '!=']:
                # 确保操作数类型一致
                if isinstance(left, BoolRef) != isinstance(right, BoolRef):
                    if isinstance(left, BoolRef):
                        left = If(left, BitVecVal(1, 1), BitVecVal(0, 1))
                    if isinstance(right, BoolRef):
                        right = If(right, BitVecVal(1, 1), BitVecVal(0, 1))
                
                if op == '==':
                    return left == right
                else:  # op == '!='
                    return left != right
            
            # 对于其他运算符，使用BitVec类型
            else:
                # 转换Bool为BitVec
                if isinstance(left, BoolRef):
                    left = If(left, BitVecVal(1, 1), BitVecVal(0, 1))
                if isinstance(right, BoolRef):
                    right = If(right, BitVecVal(1, 1), BitVecVal(0, 1))
                
                # 确保位宽匹配
                
                
                if op == '+':
                    assert left.size() == right.size()
                    return left + right
                elif op == '-':
                    assert left.size() == right.size()
                    return left - right
                elif op == '*':
                    assert left.size() == right.size()
                    return left * right
                elif op == '&':
                    assert left.size() == right.size()
                    return left & right
                elif op == '|':
                    assert left.size() == right.size()
                    return left | right
                elif op == '^':
                    assert left.size() == right.size()
                    return left ^ right
                elif op == '>>':
                    if left.size() > right.size():
                        right = z3.ZeroExt(left.size() - right.size(), right)
                    else:
                        left = z3.ZeroExt(right.size() - left.size(), left)
                    return left >> right
                elif op == '>>>':
                    if left.size() > right.size():
                        right = z3.ZeroExt(left.size() - right.size(), right)
                    else:
                        left = z3.ZeroExt(right.size() - left.size(), left)
                    return LShR(left, right)
                elif op == '<<':
                    if left.size() > right.size():
                        right = z3.ZeroExt(left.size() - right.size(), right)
                    else:
                        left = z3.ZeroExt(right.size() - left.size(), left)
                    return left << right
                else:
                    raise ValueError(f"Unknown operator: {op}")

            
        # 处理一元操作
        if node_type == 'UNOP':
            op = node[1]
            operand = self.traverse(node[2],width_map)
            
            if op == '~': return ~operand
            if op == '!': 
                if isinstance(operand, BitVecRef):
                    operand = operand == 1
                return Not(operand)
            elif op == '&':
                width = operand.size()  # 获取位宽
                bits = [Extract(i, i, operand) for i in range(width)]  # 从0到width-1提取每一位
                return reduce(lambda x, y: x & y, bits)  # 对所有位进行OR运算
            elif op == '|':
                width = operand.size()  # 获取位宽
                bits = [Extract(i, i, operand) for i in range(width)]  # 从0到width-1提取每一位
                return reduce(lambda x, y: x | y, bits)  # 对所有位进行OR运算
            
        # 处理条件操作
        if node_type == 'CONDITIONAL':
            cond = self.traverse(node[1],width_map)
            if isinstance(cond, BitVecRef):
                cond = (cond == 1)
            true_value = self.traverse(node[2],width_map)
            false_value = self.traverse(node[3],width_map)
            
            if false_value in self.unknown_vars and true_value in self.unknown_vars:
                var_false = self.unknown_vars[false_value] ##在一次处理
                var_true = self.unknown_vars[true_value] ##在一次处理
                del self.unknown_vars[false_value]
                del self.unknown_vars[true_value]
                del self.z3_vars[var_true]
                del self.z3_vars[var_false]
                
                final_var = self.get_or_create_z3_var(var_false,width_map,True)
                return final_var
            elif false_value in self.unknown_vars: ## 我们对unknown val进行修改 
                if isinstance(true_value, BoolRef):
                    true_value = If(true_value, BitVecVal(1, 1), BitVecVal(0, 1))
                
                width = true_value.size()
                var = self.unknown_vars[false_value] ##在一次处理
                del self.unknown_vars[false_value]
                del self.z3_vars[var]

                new_false_value = BitVec(var, width)
                self.z3_vars[var] = new_false_value
                self.unknown_vars[new_false_value] = var
                return If(cond, true_value, new_false_value)
            elif true_value in self.unknown_vars:  
                if isinstance(false_value, BoolRef):
                    false_value = If(false_value, BitVecVal(1, 1), BitVecVal(0, 1))

                width = false_value.size()
                var = self.unknown_vars[true_value] ##在一次处理
                del self.unknown_vars[true_value]
                del self.z3_vars[var]
                new_true_value = BitVec(var, width)
                self.z3_vars[var] = new_true_value
                self.unknown_vars[new_true_value] = var
                return If(cond, new_true_value, false_value)
            else:
                if isinstance(true_value, BoolRef):
                    true_value = If(true_value, BitVecVal(1, 1), BitVecVal(0, 1))
                if isinstance(false_value, BoolRef):
                    false_value = If(false_value, BitVecVal(1, 1), BitVecVal(0, 1))
                return If(cond, true_value, false_value)
            
        # 处理部分选择
        if node_type == 'PART_SELECT':
            var = self.get_or_create_z3_var(node[1],width_map)
            high = self.traverse(node[2],width_map)
            low = self.traverse(node[3],width_map)
            if type(high) == z3.z3.BitVecNumRef:
                return Extract(high.as_long(), low.as_long(), var)
            else:
                return Extract(high, low, var)            
         # 处理位选择
        if node_type == 'BIT_SELECT':
            var = self.get_or_create_z3_var(node[1],width_map)
            bit = self.traverse(node[2],width_map)
            if type(bit) == z3.z3.BitVecNumRef:
                return Extract(bit.as_long(), bit.as_long(), var)
            else:
                return Extract(bit, bit, var)            
 
        # 处理连接操作
        if node_type == 'CONCAT':
            elements = [self.traverse(elem,width_map) for elem in node[1]]
            return Concat(*elements)
 
        if node_type == 'REPLICATION':
            count = self.traverse(node[1], width_map)  # 获取重复次数
            value = self.traverse(node[2], width_map)  # 获取要重复的值
            assert isinstance(count, BitVecNumRef)
            # 如果count是常量
            # if isinstance(count, BitVecNumRef):
            count = count.as_long()
            # 创建重复的值
            if isinstance(value, BitVecRef):
                # 如果value是位向量，直接重复连接
                return Concat(*[value for _ in range(count)])
            elif isinstance(value, BoolRef):
                # 如果value是布尔值，先转换为位向量
                bit_value = If(value, BitVecVal(1, 1), BitVecVal(0, 1))
                return Concat(*[bit_value for _ in range(count)])
            # else:
            #     # 如果count不是常量，可能需要创建一个新的符号变量
            #     var_name = f"replication_{len(self.z3_vars)}"
            #     # 假设结果位宽为value的位宽乘以count
            #     result_width = value.size() * count if isinstance(count, int) else 32
            #     width_map[var_name] = result_width
            #     return self.get_or_create_z3_var(var_name, width_map)
            
        return None

    def visitNet_assignment(self, ctx):
        # 获取赋值的左右两边
        lvalue = ctx.net_lvalue().getText()
        expression = ctx.expression().getText()
        
        # 存储原始赋值
        self.assignments.append({
            'target': lvalue,
            'expression': expression
        })

        # 创建Z3约束
        lhs_var = self.get_or_create_z3_var(lvalue)
        rhs_expr = self.parse_expression(expression)
        self.solver.add(lhs_var == rhs_expr)
        
        return super().visitNet_assignment(ctx)
    
    
    def get_condition_for_unknown_val(self, predecessor):
        assert is_eq(predecessor)
        return predecessor.arg(1)
        
        
    def analyze_constraints(self):
        """分析约束并检查可满足性"""
        print("\nZ3 Constraints:")
        for c in self.solver.assertions():
            print(c)
            
        result = self.solver.check()
        if result == sat:
            print("\nFound satisfiable assignment:")
            model = self.solver.model()
            for var_name, z3_var in self.z3_vars.items():
                print(f"{var_name} = {model[z3_var]}")
        else:
            print("\nConstraints are unsatisfiable")

def build_smt_formula(ast, width_map,is_predecessor):
    builder = Assignment2SMT()
    formula = builder.traverse(ast, width_map)
    print(formula)
    
    condition_assign = builder.get_condition_for_unknown_val(formula) if(is_predecessor) else None
    
    return formula, builder.z3_vars, builder.unknown_vars, condition_assign



# if __name__ == "__main__":
#     # 测试几个示例
#     tests = [
#         # 简单赋值
#         ('CONTINUOUS_ASSIGN', ('ID', 'a'), ('CONST', '42')),
        
#         # 位宽常量赋值
#         ('CONTINUOUS_ASSIGN', ('ID', 'b'), ('PART_SELECT', 'near_mem$imem_instr', ('CONST', '6'), ('CONST', '0'))),
        
#         # reduction AND操作
#         ('CONTINUOUS_ASSIGN', ('ID', 'f'), ('UNOP', '&', ('ID', 'b'))),
        
#         # 复杂表达式
#         ('CONTINUOUS_ASSIGN', 
#          ('ID', 'result'), 
#          ('BINOP', '*', 
#           ('BINOP', '+', 
#            ('CONST', "8'b1010_1011"), 
#            ('CONST', "16'hFFFF")), 
#           ('CONST', '42')))
#     ]
    
#     for test_ast in tests:
#         print("\nTesting AST:", test_ast)
#         formula, variables = build_smt_formula(test_ast)
#         print("Formula:", formula)
        
#         s = Solver()
#         s.add(formula)
        
#         if s.check() == sat:
#             m = s.model()
#             print("Solution:")
#             for var in variables:
#                 print(f"{var} = {m[variables[var]]}")
#         else:
#             print("No solution")
