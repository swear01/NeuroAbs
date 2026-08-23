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

from check import preprocess_string


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
