"""specs_s1.py <out dir>: the first screen specs for BEQ, SB and LB (one JSONL per case)."""
import json
import os
import sys

CUT_ALL = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "cut"}
CUT_CD = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "keep"}
SPECS = {
    "BEQ": [
        ("pc.split", {"states": ["pc"]}),
        ("load_en.split", {"states": ["load_en"]}),
        ("store_en.split", {"states": ["store_en"]}),
        ("mem.S", {"states": ["load_en", "pc", "store_en"], "keep_gprs": [], "units": CUT_ALL, "uf": []}),
        ("pc.S", {"states": ["pc"], "keep_gprs": [], "units": CUT_ALL, "uf": []}),
        ("pc.allgpr.cd", {"states": ["pc"], "units": CUT_CD}),
        ("pc.rs1=5.rs2=6.split", {"states": ["pc"], "case": "rs1==5&&rs2==6"}),
        ("pc.rs1=5.rs2=6.keep56.cd", {"states": ["pc"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_CD}),
    ],
    "SB": [
        ("store_en.split", {"states": ["store_en"]}),
        ("store_en.S", {"states": ["store_en"], "keep_gprs": [], "units": CUT_ALL, "uf": []}),
        ("pc.split", {"states": ["pc"]}),
    ],
    "LB": [
        ("x5.rs1=6.split", {"states": ["x5"], "case": "rd==5&&rs1==6"}),
        ("x5.rs1=6.S", {"states": ["x5"], "case": "rd==5&&rs1==6", "keep_gprs": [6], "word_gprs": [5], "units": CUT_ALL, "uf": []}),
        ("load_en.split", {"states": ["load_en"]}),
        ("load_en.S", {"states": ["load_en"], "keep_gprs": [], "units": CUT_ALL, "uf": []}),
    ],
}
for case, jobs in SPECS.items():
    with open(os.path.join(sys.argv[1], case + "-s1.jsonl"), "w") as f:
        for name, spec in jobs:
            f.write(json.dumps({"name": name, "spec": spec}) + "\n")
