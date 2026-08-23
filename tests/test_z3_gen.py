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


if __name__ == "__main__":
    unittest.main()
