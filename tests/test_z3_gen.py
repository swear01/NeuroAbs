import sys
import unittest
from pathlib import Path

from z3 import BitVec, Solver, ZeroExt, unsat


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from z3_gen import Assignment2SMT


class Assignment2SMTTest(unittest.TestCase):
    def test_assignment_fits_symbolic_rhs_to_lhs_width(self):
        formula = Assignment2SMT().traverse(
            ("BLOCKING_ASSIGN", ("ID", "c_state"), ("ID", "idle")),
            {"c_state": 5, "idle": 1},
        )

        solver = Solver()
        solver.add(formula)
        solver.add(BitVec("c_state", 5) != ZeroExt(4, BitVec("idle", 1)))
        self.assertEqual(solver.check(), unsat)

    def test_binary_expression_infers_symbolic_macro_width(self):
        builder = Assignment2SMT()
        builder.traverse(
            (
                "BLOCKING_ASSIGN",
                ("ID", "cmd_stop"),
                ("BINOP", "==", ("ID", "cmd"), ("ID", "I2C_CMD_STOP")),
            ),
            {"cmd_stop": 1, "cmd": 4},
        )

        self.assertEqual(builder.z3_vars["I2C_CMD_STOP"].size(), 4)

    def test_assignment_infers_symbolic_macro_width_from_lhs(self):
        builder = Assignment2SMT()
        builder.traverse(
            ("BLOCKING_ASSIGN", ("ID", "core_cmd"), ("ID", "I2C_CMD_STOP")),
            {"core_cmd": 4},
        )

        self.assertEqual(builder.z3_vars["I2C_CMD_STOP"].size(), 4)


if __name__ == "__main__":
    unittest.main()
