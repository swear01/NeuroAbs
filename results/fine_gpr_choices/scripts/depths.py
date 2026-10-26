"""depths.py <ric3.log>...: deepest bound of any BMC worker and highest IC3 frame in each rIC3 log."""
import re
import sys

for path in sys.argv[1:]:
    bmc, ic3 = 0, 0
    for m in re.finditer(r"INFO\] (\w+) proved at depth (\d+)", open(path, errors="replace").read()):
        if m.group(1).startswith("bmc"):
            bmc = max(bmc, int(m.group(2)))
        elif m.group(1).startswith("ic3"):
            ic3 = max(ic3, int(m.group(2)))
    print("{:s} bmc={:d} ic3={:d}".format(path, bmc, ic3))
