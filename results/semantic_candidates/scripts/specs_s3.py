"""specs_s3.py <out dir>: third screen, the comparator UF for BEQ pc and the address adder UF for SB store_en."""
import json
import os
import sys

CUT_ALL = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "cut"}
CUT_CD = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "keep"}
BEQ_UF = [{"ila": "n166", "rtl": "IF_near_mem_imem_instr__59_BITS_19_TO_15_60_EQ_ETC___d216"}]
SB_UF = [{"ila": "n110", "rtl": "alu_outputs___1_addr__h5583"}]
SPECS = {
    "BEQ": [
        ("pc.rs1=5.rs2=6.keep56.cd.uf", {"states": ["pc"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_CD, "uf": BEQ_UF}),
        ("pc.rs1=5.rs2=6.S+uf", {"states": ["pc"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_ALL, "uf": BEQ_UF}),
        ("pc.rs1=12.rs2=3.keep.cd.uf", {"states": ["pc"], "case": "rs1==12&&rs2==3", "keep_gprs": [3, 12], "units": CUT_CD, "uf": BEQ_UF}),
        ("pc.allgpr.cd.uf", {"states": ["pc"], "units": CUT_CD, "uf": BEQ_UF}),
    ],
    "SB-named": [
        ("store_en.rs1=5.rs2=6.keep56.cd.uf", {"states": ["store_en"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_CD, "uf": SB_UF}),
        ("store_en.rs1=5.rs2=6.S+uf", {"states": ["store_en"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_ALL, "uf": SB_UF}),
    ],
}
for case, jobs in SPECS.items():
    with open(os.path.join(sys.argv[1], case + "-s3.jsonl"), "w") as f:
        for name, spec in jobs:
            f.write(json.dumps({"name": name, "spec": spec}) + "\n")
