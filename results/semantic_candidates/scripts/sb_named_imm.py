"""sb_named_imm.py <SB wrapper.v> <out.v>: name the S-type immediate of the RTL store address as a wire.

alu_outputs___1_addr__h5583 = rs1_val_bypassed__h3337 + {sext imm}; the sum becomes
rs1_val_bypassed__h3337 + store_imm__uf, with store_imm__uf assigned the same expression, so that
fine_choice.operator_args accepts it as a pair for the ILA adder n110.  The model is unchanged.
"""
import sys

OLD = """  assign alu_outputs___1_addr__h5583 =
\t     rs1_val_bypassed__h3337 +
\t     { {20{near_memimem_instr_BITS_31_TO_25_CONCAT_near__ETC__q6[11]}},
\t       near_memimem_instr_BITS_31_TO_25_CONCAT_near__ETC__q6 } ;
"""
NEW = """  wire [31:0] store_imm__uf =
\t     { {20{near_memimem_instr_BITS_31_TO_25_CONCAT_near__ETC__q6[11]}},
\t       near_memimem_instr_BITS_31_TO_25_CONCAT_near__ETC__q6 } ;
  assign alu_outputs___1_addr__h5583 =
\t     rs1_val_bypassed__h3337 + store_imm__uf ;
"""
with open(sys.argv[1]) as f:
    text = f.read()
if text.count(OLD) != 1:
    raise SystemExit("expected one store address assignment")
with open(sys.argv[2], "w") as f:
    f.write(text.replace(OLD, NEW))
