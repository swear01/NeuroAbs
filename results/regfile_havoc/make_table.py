import json
import statistics
import sys

CASES = 'add addi and bge ori sh slti sub xor'.split()
BASE = {'add': (122.3, 127.5), 'addi': (137.7, 146.8), 'and': (121.4, 99.1), 'bge': (202.0, 187.8),
        'ori': (103.1, 105.2), 'sh': (178.6, 180.6), 'slti': (156.7, 100.2), 'sub': (142.2, 151.4),
        'xor': (106.0, 112.7)}

runs = {}
for path in sys.argv[1:]:
    for r in json.load(open(path))['runs']:
        runs.setdefault(r['label'], []).append(r)

print('| Case | H0 runs (s) | H0 median | H0 verdict | H0/B0 | H0/B1 | H1 runs (s) | H1 median | H1 verdict | H1/B0 | H1/B1 |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for c in CASES:
    b0, b1 = BASE[c]
    row = [c.upper()]
    for arm in ('H0', 'H1'):
        rs = sorted(runs.get('{:s}-{:s}'.format(c, arm), []), key=lambda r: r['repeat'])
        if not rs:
            row += ['not run'] * 5
            continue
        med = statistics.median(r['seconds'] for r in rs)
        verdicts = '/'.join(sorted({r['verdict'] for r in rs}))
        row += [', '.join('{:.1f}'.format(r['seconds']) for r in rs), '{:.1f}'.format(med), verdicts,
                '{:.2f}'.format(med / b0), '{:.2f}'.format(med / b1)]
    print('| ' + ' | '.join(row) + ' |')
