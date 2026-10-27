"""table.py <run dir>: one Markdown row per record of every <case>/<batch>.jsonl, with depths of the last model.

Columns: case, batch, name, status, refinements, total s, rIC3 s, final COI bits, deepest BMC bound and IC3 frame
of the last rIC3 run (from its log), counterexample depth of each SAT iteration.
"""
import glob
import json
import os
import re
import sys


def depths(log):
    bmc, ic3 = 0, 0
    with open(log, errors="replace") as f:
        for m in re.finditer(r"INFO\] (\w+) proved at depth (\d+)", f.read()):
            if m.group(1).startswith("bmc"):
                bmc = max(bmc, int(m.group(2)))
            elif m.group(1).startswith("ic3"):
                ic3 = max(ic3, int(m.group(2)))
    return bmc, ic3


run = sys.argv[1]
print("| Case | Batch | Sub-property / arm | Status | Ref. | Time s | rIC3 s | Final COI bits | BMC / IC3 (last) | CEX depths |")
print("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
for path in sorted(glob.glob(os.path.join(run, "piccolo-*", "*.jsonl"))):
    case = os.path.basename(os.path.dirname(path))[len("piccolo-"):]
    batch = os.path.basename(path)[:-len(".jsonl")]
    with open(path) as f:
        for line in filter(str.strip, f):
            r = json.loads(line)
            if r["status"] == "ERROR":
                raise SystemExit("ERROR record in " + path + ": " + r["name"])
            last = len(r["iterations"]) - 1
            log = os.path.join(run, "piccolo-" + case, batch, r["name"], "iter{:d}".format(last), "model.btor2.ric3.log")
            bmc, ic3 = depths(log)
            cex = ",".join(str(i["cex_depth"]) for i in r["iterations"] if i["ric3"] == "SAT") or "-"
            print("| {} | {} | `{}` | {} | {} | {:.0f} | {:.0f} | {:,} | {} / {} | {} |".format(
                case, batch, r["name"], r["status"], r["refinements"], r["total_seconds"], r["ric3_seconds"],
                r["final_coi_state_bits"], bmc, ic3, cex))
