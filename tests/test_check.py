import sys
import types
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
sys.modules["pyverilog"] = types.ModuleType("pyverilog")
sys.modules["pyverilog.vparser"] = types.ModuleType("pyverilog.vparser")
lexer = types.ModuleType("pyverilog.vparser.lexer")
lexer.VerilogLexer = object
sys.modules["pyverilog.vparser.lexer"] = lexer
ply = types.ModuleType("ply")
ply.yacc = object()
sys.modules["ply"] = ply

from check import preprocess_string, preserve_assignment_context


class PreserveAssignmentContextTest(unittest.TestCase):
    def test_keeps_condition_containing_comparison(self):
        self.assertEqual(
            preserve_assignment_context("if (a == b) q <= c + 1;", "x = 'bx;"),
            "if (a == b) q <= 'bx;",
        )

    def test_keeps_condition_containing_less_equal(self):
        self.assertEqual(
            preserve_assignment_context("if (a <= b) begin q <= c;", "x = 'bx;"),
            "if (a <= b) begin q <= 'bx;",
        )

    def test_continuous_assignment_with_comparison_rhs(self):
        self.assertEqual(
            preserve_assignment_context("assign f = a >= b;", "x = 'bx;"),
            "assign f = 'bx;",
        )

    def test_case_label(self):
        self.assertEqual(
            preserve_assignment_context("2'b01: q = d;", "x = 'bx;"),
            "2'b01: q = 'bx;",
        )


class PreprocessStringTest(unittest.TestCase):
    def test_preserves_preprocessor_macro_as_identifier(self):
        self.assertEqual(
            preprocess_string("cmd_stop <= cmd == `I2C_CMD_STOP;"),
            "cmd_stop <= cmd == I2C_CMD_STOP;",
        )

    def test_removes_wire_declaration_for_assignment_parser(self):
        self.assertEqual(preprocess_string("wire rd = cr[5];"), "rd = cr[5];")


if __name__ == "__main__":
    unittest.main()
