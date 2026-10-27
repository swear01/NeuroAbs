"""specs_s4.py <out dir>: more (rs1, rs2) samples, split-only against the rule-with-UF abstraction.

For each pair: split-only (no abstraction) and "S+uf" (keep rs1 and rs2, every unit cut, the operator UF,
CEGAR); the pair (5, 6) also gets split-only with a long limit (separate file, 1200 s).
"""
import json
import os
import sys

CUT_ALL = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "cut"}
UF = {"BEQ": [{"ila": "n166", "rtl": "IF_near_mem_imem_instr__59_BITS_19_TO_15_60_EQ_ETC___d216"}],
      "SB-named": [{"ila": "n110", "rtl": "alu_outputs___1_addr__h5583"}]}
STATE = {"BEQ": "pc", "SB-named": "store_en"}
PAIRS = [(12, 3), (31, 1), (20, 9), (7, 26)]
for case in ("BEQ", "SB-named"):
    s = STATE[case]
    with open(os.path.join(sys.argv[1], case + "-s4.jsonl"), "w") as f:
        for a, b in PAIRS:
            c = "rs1=={:d}&&rs2=={:d}".format(a, b)
            n = "{:s}.rs1={:d}.rs2={:d}".format(s, a, b)
            f.write(json.dumps({"name": n + ".split", "spec": {"states": [s], "case": c}}) + "\n")
            f.write(json.dumps({"name": n + ".S+uf", "spec": {"states": [s], "case": c, "keep_gprs": sorted({a, b}),
                                                             "units": CUT_ALL, "uf": UF[case]}}) + "\n")
    with open(os.path.join(sys.argv[1], case + "-long.jsonl"), "w") as f:
        f.write(json.dumps({"name": s + ".rs1=5.rs2=6.split", "spec": {"states": [s], "case": "rs1==5&&rs2==6"}}) + "\n")
