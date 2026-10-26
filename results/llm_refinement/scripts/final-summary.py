"""final-summary.py: deepest bound per rIC3 engine in the 1800 s final-model runs."""
import glob, os, re, sys
sys.path.insert(0, os.path.expanduser("~/.agent-worktrees/NeuroAbs-llm-refine/src"))
import choice_abstraction as ca
RUN = "/var/tmp/neuroabs-runtime/runs/llm-refine-20261026"
ENGINES = ["bmc_kissat_dyn", "bmc_kissat_65", "bmc_kissat_10", "bmc", "ic3", "kind"]
for log in sorted(glob.glob(os.path.join(RUN, "final", "*", "*.log"))):
    case, name = log.split("/")[-2], os.path.basename(log)[:-4]
    depth = {}
    for line in open(log):
        m = re.search(r"\] (\S+) proved at depth (\d+)", line)
        if m:
            depth[m.group(1)] = max(depth.get(m.group(1), 0), int(m.group(2)))
    verdict = next((l.strip() for l in open(log) if l.strip() in ("SAT", "UNSAT", "UNKNOWN")), "none")
    bits = sum(ca.coi_state_bits(os.path.join(RUN, "piccolo", case, "models", name, "model.btor2")).values())
    print(case, name, bits, verdict, " ".join("{}={}".format(e, depth.get(e, "-")) for e in ENGINES))
