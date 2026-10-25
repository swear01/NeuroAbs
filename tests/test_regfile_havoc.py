import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from regfile_havoc import havoc

RTL = (
    "\treg [31:0] cpuregs [0:regfile_size-1];\n"
    "`ifdef DEBUGREGS\n\twire [31:0] dbg_reg_x1  = cpuregs[1];\n`endif\n"
    "\talways @(posedge clk) begin\n\t\tif (resetn && cpuregs_write && latched_rd)\n"
    "`ifdef PICORV32_TESTBUG_001\n\t\t\tcpuregs[latched_rd ^ 1] <= cpuregs_wrdata;\n`else\n"
    "\t\t\tcpuregs[latched_rd] <= cpuregs_wrdata;\n`endif\n\tend\n"
    "\t\t\tcpuregs_rs1 = decoded_rs1 ? cpuregs[decoded_rs1] : 0;\n"
    "\t\t\tcpuregs_rs2 = decoded_rs2 ? cpuregs[decoded_rs2] : 0;\n"
    "\t\t\tcpuregs_rs1 = decoded_rs ? cpuregs[decoded_rs] : 0;\n"
)


class HavocTest(unittest.TestCase):
    def test_k0_replaces_every_read_port(self):
        out = havoc(RTL, 0)
        self.assertIn("cpuregs_rs2 = decoded_rs2 ? $anyseq : 0;", out)
        self.assertNotIn("cpuregs[decoded_rs", out)
        self.assertIn("cpuregs[latched_rd] <= cpuregs_wrdata;", out)

    def test_k1_tracks_one_address(self):
        out = havoc(RTL, 1)
        self.assertIn("regfile_havoc_addr0 = $anyconst;", out)
        self.assertIn("regfile_havoc_data0 <= cpuregs_wrdata;", out)
        self.assertIn("decoded_rs1 == regfile_havoc_addr0 ? regfile_havoc_data0 : $anyseq", out)

    def test_unhandled_read_is_rejected(self):
        with self.assertRaises(ValueError):
            havoc(RTL + "\tassign x = cpuregs[5];\n", 0)


if __name__ == "__main__":
    unittest.main()
