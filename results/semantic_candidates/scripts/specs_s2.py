"""specs_s2.py <out dir>: second screen, which part of the BEQ pc and SB store_en proofs is hard."""
import json
import os
import sys

CUT_CD = {"csr_regfile": "cut", "near_mem_dcache": "cut", "near_mem_icache": "keep"}
SPECS = {
    "BEQ": [
        ("pc.rs1=0.rs2=0.keep0.cd", {"states": ["pc"], "case": "rs1==0&&rs2==0", "keep_gprs": [0], "units": CUT_CD}),
        ("pc.rs1=5.rs2=5.keep5.cd", {"states": ["pc"], "case": "rs1==5&&rs2==5", "keep_gprs": [5], "units": CUT_CD}),
        ("pc.rs1=5.rs2=0.keep5.cd", {"states": ["pc"], "case": "rs1==5&&rs2==0", "keep_gprs": [0, 5], "units": CUT_CD}),
    ],
    "SB": [
        ("store_en.rs1=5.rs2=6.split", {"states": ["store_en"], "case": "rs1==5&&rs2==6"}),
        ("store_en.rs1=5.rs2=6.keep56.cd", {"states": ["store_en"], "case": "rs1==5&&rs2==6", "keep_gprs": [5, 6], "units": CUT_CD}),
        ("store_en.rs1=0.rs2=6.keep6.cd", {"states": ["store_en"], "case": "rs1==0&&rs2==6", "keep_gprs": [0, 6], "units": CUT_CD}),
    ],
}
for case, jobs in SPECS.items():
    with open(os.path.join(sys.argv[1], case + "-s2.jsonl"), "w") as f:
        for name, spec in jobs:
            f.write(json.dumps({"name": name, "spec": spec}) + "\n")
