import importlib
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"

MODEL = """1 sort bitvec 1
2 sort bitvec 2
3 input 1 a
4 input 1 b
5 state 1 free_s
6 state 2 cnt
7 zero 2
8 init 2 6 7
9 one 2
10 add 2 6 9
11 next 2 6 10
12 ite 1 3 4 5
13 constd 2 2
14 eq 1 6 13
15 and 1 14 12
16 bad 15
"""

WITNESS = """SAT
sat
b0
#0
0 0 free_s
1 00 cnt
@0
0 0
1 0
@1
0 0
1 0
#2
0 1
@2
0 0
1 1
.
"""


class BtorWitnessTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        sys.modules.pop("btor_witness", None)
        self.witness = importlib.import_module("btor_witness")
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "m.btor2").write_text(MODEL)

    def tearDown(self):
        self.directory.cleanup()
        sys.modules.pop("btor_witness", None)
        sys.path.remove(str(SRC))

    def test_cone_follows_the_taken_branch(self):
        (self.root / "w.txt").write_text(WITNESS)
        names = self.witness.free_names(str(self.root / "m.btor2"), str(self.root / "w.txt"))
        self.assertEqual(names, {"a", "free_s"})

    def test_free_values_carry_their_frame(self):
        (self.root / "w.txt").write_text(WITNESS)
        values = self.witness.free_values(str(self.root / "m.btor2"), str(self.root / "w.txt"))
        self.assertEqual(values, [("a", 2), ("free_s", 2)])

    def test_an_uninitialized_state_is_free_in_frame_0(self):
        (self.root / "u.btor2").write_text("1 sort bitvec 1\n2 state 1 u\n3 next 1 2 2\n4 bad 2\n")
        (self.root / "w.txt").write_text("sat\nb0\n#0\n0 1 u\n@0\n.\n")
        names = self.witness.free_names(str(self.root / "u.btor2"), str(self.root / "w.txt"))
        self.assertEqual(names, {"u"})

    def test_a_witness_that_does_not_violate_is_rejected(self):
        (self.root / "w.txt").write_text(WITNESS.replace("#2\n0 1\n", "#2\n0 0\n"))
        with self.assertRaises(ValueError):
            self.witness.free_names(str(self.root / "m.btor2"), str(self.root / "w.txt"))


if __name__ == "__main__":
    unittest.main()
