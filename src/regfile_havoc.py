"""Havoc the PicoRV32 register file of a riscv-formal case and rebuild its BTOR2.

k=0: every active cpuregs read returns a fresh $anyseq value each cycle.
k=1: one $anyconst address is tracked; reads of it return a shadow register
     updated by the real write port, every other read is $anyseq.
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
READS = ('decoded_rs1', 'decoded_rs2', 'decoded_rs')
WRITE = '\t\t\tcpuregs[latched_rd] <= cpuregs_wrdata;\n`endif\n\tend\n'
DECL = '\treg [31:0] cpuregs [0:regfile_size-1];\n'
K1_DECL = (
    '\t(* keep *) wire [regindex_bits-1:0] regfile_havoc_addr0 = $anyconst;\n'
    '\t(* keep *) reg [31:0] regfile_havoc_data0;\n'
)
K1_WRITE = (
    '\n\talways @(posedge clk) begin\n'
    '\t\tif (resetn && cpuregs_write && latched_rd && latched_rd == regfile_havoc_addr0)\n'
    '\t\t\tregfile_havoc_data0 <= cpuregs_wrdata;\n'
    '\tend\n'
)


def havoc(text, k):
    for name in READS:
        old = '{0:s} ? cpuregs[{0:s}] : 0;'.format(name)
        if k == 0:
            new = '{:s} ? $anyseq : 0;'.format(name)
        else:
            new = '{0:s} ? ({0:s} == regfile_havoc_addr0 ? regfile_havoc_data0 : $anyseq) : 0;'.format(name)
        if text.count(old) != 1:
            raise ValueError('expected one read {!r}, found {:d}'.format(old, text.count(old)))
        text = text.replace(old, new)
    if k == 1:
        for anchor, extra in ((DECL, K1_DECL), (WRITE, K1_WRITE)):
            if text.count(anchor) != 1:
                raise ValueError('expected one anchor {!r}'.format(anchor))
            text = text.replace(anchor, anchor + extra)
    # Any remaining cpuregs read must be inactive (DEBUGREGS / BLACKBOX branches) or a write/init.
    active = [m for m in re.finditer(r'cpuregs\[[^\]]+\]', text)
              if not re.match(r'\s*(<=|=)', text[m.end():]) and 'dbg_reg_x' not in text[text.rfind('\n', 0, m.start()) + 1:m.start()]]
    if active:
        raise ValueError('unhandled cpuregs reads: {}'.format([m.group(0) for m in active]))
    if re.search(r'^\s*`define\s+(DEBUGREGS|PICORV32_REGS|RISCV_FORMAL_BLACKBOX_REGS)\b', text, re.M):
        raise ValueError('unexpected regfile define')
    return text


def build(src_dir, verilog, out_dir, k):
    os.makedirs(out_dir)
    for name in os.listdir(src_dir):
        path = os.path.join(src_dir, name)
        if os.path.isfile(path) and not name.endswith(('.btor2', '.aig', '.aag', '.log')):
            shutil.copy2(path, out_dir)
    with open(verilog) as f:
        text = havoc(f.read(), k)
    rtl = os.path.join(out_dir, 'picorv32_input.v')
    with open(rtl, 'w') as f:
        f.write(text)
    code = ('import sys, os; sys.path.insert(0, {!r}); os.chdir({!r}); from cegar import run_yosys_init; '
            'print(run_yosys_init({!r}, {!r}))').format(SRC_DIR, out_dir, os.path.join(out_dir, 'design.ys'), rtl)
    with open(os.path.join(out_dir, 'havoc_yosys.log'), 'w') as log:
        rc = subprocess.run([sys.executable, '-c', code], cwd=out_dir, stdout=log, stderr=subprocess.STDOUT).returncode
    model = os.path.join(out_dir, 'picorv32_input.btor2')
    if rc != 0 or not os.path.exists(model):
        raise RuntimeError('yosys failed (rc={:d}), see {:s}/havoc_yosys.log'.format(rc, out_dir))
    summary = {'source_dir': src_dir, 'source_verilog': verilog, 'k': k, 'final_model': model, 'stats': stats(model)}
    with open(os.path.join(out_dir, 'havoc_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    return summary


def stats(path):
    """State bits (states with a next function, i.e. registers) and the cone of bad/constraint nodes."""
    nodes, nexts, sorts, roots = {}, collections.defaultdict(list), {}, []
    for line in open(path):
        t = line.split(';')[0].split()
        if len(t) < 2 or not t[0].isdigit():
            continue
        i, op = int(t[0]), t[1]
        nodes[i] = (op, t)
        if op == 'sort':
            sorts[i] = int(t[3]) if t[2] == 'bitvec' else None
        if op in ('bad', 'constraint'):
            roots.append(i)
        if op in ('next', 'init'):
            nexts[int(t[3])].append(i)

    def args(i):
        op, t = nodes[i]
        if op in ('sort', 'input', 'state', 'const', 'constd', 'consth', 'zero', 'one', 'ones'):
            return []
        if op in ('slice', 'sext', 'uext'):
            rng = t[3:4]
        else:
            rng = t[2:] if op in ('bad', 'constraint', 'output') else t[3:]
        out = []
        for a in rng:
            try:
                v = abs(int(a))
            except ValueError:
                continue
            if v in nodes and nodes[v][0] != 'sort':
                out.append(v)
        return out

    seen, todo = set(), list(roots)
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        todo.extend(args(i))
        if nodes[i][0] == 'state':
            todo.extend(nexts[i])

    def has_next(i):
        return any(nodes[n][0] == 'next' for n in nexts[i])

    def regs(ids):
        r = [i for i in ids if nodes[i][0] == 'state' and has_next(i)]
        return len(r), sum(sorts[int(nodes[i][1][2])] for i in r)

    def names(ids, pat):
        return sum(sorts[int(nodes[i][1][2])] for i in ids
                   if nodes[i][0] == 'state' and len(nodes[i][1]) > 3 and re.search(pat, nodes[i][1][3]))

    reg_n, reg_bits = regs(nodes)
    coi_n, coi_bits = regs(seen)
    return {'nodes': len(nodes), 'registers': reg_n, 'register_bits': reg_bits,
            'cpuregs_bits': names(nodes, r'\.cpuregs\['),
            'coi_nodes': len(seen), 'coi_registers': coi_n, 'coi_register_bits': coi_bits,
            'coi_cpuregs_bits': names(seen, r'\.cpuregs\['),
            'coi_inputs': sum(1 for i in seen if nodes[i][0] == 'input'),
            'coi_free_states': sum(1 for i in seen if nodes[i][0] == 'state' and not has_next(i))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--src-dir', required=True, help='arm dir with design.ys and the testbench sources')
    b.add_argument('--verilog', required=True, help='PicoRV32 Verilog to havoc')
    b.add_argument('--out-dir', required=True)
    b.add_argument('--k', type=int, choices=[0, 1], default=0)
    s = sub.add_parser('stats')
    s.add_argument('btor2', nargs='+')
    a = p.parse_args()
    if a.cmd == 'build':
        print(json.dumps(build(os.path.abspath(a.src_dir), os.path.abspath(a.verilog), os.path.abspath(a.out_dir), a.k)))
    else:
        for path in a.btor2:
            print(path, json.dumps(stats(path)))


if __name__ == '__main__':
    main()
