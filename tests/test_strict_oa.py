import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from strict_oa import read_results


class ReadResultsTest(unittest.TestCase):
    def test_sat_records_carry_a_solution_line(self):
        lines = ["a <= b;", "a <= 'bx;", "unsat", "c <= d;", "c <= 0;", "sat", "Solution: c = 0 d = 1", "e <= f;", "e <= 'bx;", "unsat"]
        self.assertEqual(
            [("a <= b;", "a <= 'bx;", "unsat"), ("c <= d;", "c <= 0;", "sat"), ("e <= f;", "e <= 'bx;", "unsat")],
            read_results(lines),
        )

    def test_malformed_results_are_rejected(self):
        for lines in (["a <= b;", "a <= 'bx;"], ["a <= b;", "a <= 0;", "sat"], ["a <= b;", "a <= 0;", "maybe"]):
            with self.assertRaises(RuntimeError):
                read_results(lines)


if __name__ == "__main__":
    unittest.main()
