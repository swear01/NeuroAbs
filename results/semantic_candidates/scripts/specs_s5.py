"""specs_s5.py <out dir>: repeats of rule+UF on (rs1, rs2) = (5, 6), and SB with the structurally matched adder.

The structural matcher (same operator, an operand named rs1_val*) finds eaddr__h5553, the load address adder
(I-type immediate), in the SB RTL; the store address adder has a concatenation as operand.
"""
import json
import os
import sys

CUT_ALL = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "cut"}
CASE = "rs1==5&&rs2==6"
BEQ_UF = [{"ila": "n166", "rtl": "IF_near_mem_imem_instr__59_BITS_19_TO_15_60_EQ_ETC___d216"}]
SB_UF = [{"ila": "n110", "rtl": "alu_outputs___1_addr__h5583"}]
SB_EADDR = [{"ila": "n110", "rtl": "eaddr__h5553"}]
OUT = {
    "BEQ-rep": [("pc.rs1=5.rs2=6.S+uf.r{:d}".format(i), {"states": ["pc"], "case": CASE, "keep_gprs": [5, 6],
                                                        "units": CUT_ALL, "uf": BEQ_UF}) for i in (1, 2, 3)],
    "SB-named-rep": [("store_en.rs1=5.rs2=6.S+uf.r{:d}".format(i), {"states": ["store_en"], "case": CASE,
                                                                    "keep_gprs": [5, 6], "units": CUT_ALL, "uf": SB_UF})
                     for i in (1, 2, 3)],
    "SB-eaddr": [("store_en.rs1=5.rs2=6.S+uf-eaddr", {"states": ["store_en"], "case": CASE, "keep_gprs": [5, 6],
                                                      "units": CUT_ALL, "uf": SB_EADDR})],
}
for name, jobs in OUT.items():
    with open(os.path.join(sys.argv[1], name + ".jsonl"), "w") as f:
        for n, spec in jobs:
            f.write(json.dumps({"name": n, "spec": spec}) + "\n")
