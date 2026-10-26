import sys; sys.path.insert(0, sys.argv[1])
from check import check_implies
from replacer import UnknownValReplacer
for rs in ('decoded_rs1', 'decoded_rs2', 'decoded_rs'):
    lhs = 'cpuregs_rs2' if rs == 'decoded_rs2' else 'cpuregs_rs1'
    rd = 'cpuregs_read_' + rs.split('_')[1]
    w = {lhs: 32, rs: 5, rd: 32}
    pred = "{:s} = {:s} ? {:s} : 32'h0;".format(lhs, rs, rd)
    r = check_implies(pred, "{:s} = {:s} ? 'bx : 32'h0;".format(lhs, rs), w, UnknownValReplacer(), {})
    print('RESULT', rs, r[0], r[1])
    r = check_implies(pred, "{:s} = {:s} ? 'bx : 32'h1;".format(lhs, rs), w, UnknownValReplacer(), {})
    print('NEGCTRL', rs, r[0])
