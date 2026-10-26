"""repeats.py <case dir>: the three alternating split-only / S rounds of repeat.sh, per sub-property and per round."""
import json
import statistics
import sys


def load(path):
    with open(path) as f:
        return {r["name"]: r for r in map(json.loads, f)}


d = sys.argv[1]
split = [load(f"{d}/arm-rep-split-{i}.jsonl") for i in (1, 2, 3)]
s = [load(f"{d}/arm-rep-s-{i}.jsonl") for i in (1, 2, 3)]
for i in range(3):
    print(f"round {i + 1}: split {sum(r['status'] == 'UNSAT' for r in split[i].values())} UNSAT "
          f"{sum(r['total_seconds'] for r in split[i].values()):.0f} s, "
          f"S {sum(r['status'] == 'UNSAT' for r in s[i].values())} UNSAT "
          f"{sum(r['total_seconds'] for r in s[i].values()):.0f} s")
ratios = []
for n in sorted(split[0]):
    a = [r[n]["total_seconds"] for r in split]
    b = [r[n]["total_seconds"] for r in s]
    st = {r[n]["status"] for r in split} | {r[n]["status"] for r in s}
    ratio = statistics.median(a) / statistics.median(b)
    ratios.append(ratio)
    print(f"{n:10} split {min(a):4.0f}-{max(a):4.0f} med {statistics.median(a):4.0f}  "
          f"S {min(b):3.0f}-{max(b):3.0f} med {statistics.median(b):3.0f}  x{ratio:4.1f}  {'/'.join(sorted(st))}")
print(f"median speed-up x{statistics.median(ratios):.1f}, range x{min(ratios):.1f}-x{max(ratios):.1f}")
