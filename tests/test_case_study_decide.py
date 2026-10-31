import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
with mock.patch.dict(sys.modules):  # case_study stubs the `check` module; keep that stub out of the other tests
    import case_study as cs  # noqa: E402


class FakeState:
    """Just enough of case_study.State for cmd_decide: every split covers, no case is empty."""

    def __init__(self, pieces, answers):
        self.s = {"round": 3, "pieces": pieces}
        self.answers, self.prompts, self.verdicts = list(answers), [], []

    def ident_map(self):
        return {"head": {"width": 4}}

    def coverage(self, scope, cases):
        return True, ""

    def empty(self, expr):
        return False

    def validate_op(self, op):
        return op

    def event(self, *a, **kw):
        pass

    def ask(self, step, user, validate, retries=2):
        for _ in range(retries + 1):
            self.prompts.append(user)
            try:
                result, _, _ = validate(self.answers.pop(0))
                return result, None
            except ValueError as e:
                self.verdicts.append(str(e))
        raise SystemExit("stuck")


def piece():
    return {"cond": "x", "ops": [], "status": "timeout", "fixed": {}, "direction": None, "tag": "t"}


class DecideTest(unittest.TestCase):
    def setUp(self):
        for name, fn in (("lemma_summary", lambda st, p: ("TIMEOUT", "summary")), ("sig_list", lambda st: "Signals: head")):
            patcher = mock.patch.object(cs, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_auto_pieces_ignored_and_quota_is_what_is_left(self):
        st = FakeState({"r3_c0": piece(), "r3_c1": piece()}, [
            # decides the auto-split piece too, and asks for 16 pieces while only 32 - 20 = 12 are left
            {"decisions": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 4}},
                        "r3_c9": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 1}}}},
            {"decisions": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 3}},
                        "r3_c9": {"action": "abstract", "reason": "r", "ops": ["x"]}}},
        ])
        counter = [20]
        cs.cmd_decide(st, ["r3_c0"], [("r3_c0", "TIMEOUT", 20.0), ("r3_c9", "TIMEOUT", 20.0)], counter, 20, auto=["r3_c9"])
        self.assertIn("12 new pieces left", st.prompts[0])
        self.assertIn("r3_c9: TIMEOUT 20.0 s (already split by the tool", st.prompts[0])
        self.assertEqual(len(st.verdicts), 1)
        self.assertIn("only 12 are left", st.verdicts[0])
        self.assertEqual(counter[0], 28)
        self.assertEqual(st.s["pieces"]["r3_c0"]["status"], "split")

    def test_missing_piece_is_named(self):
        st = FakeState({"r3_c0": piece(), "r3_c1": piece()}, [
            {"decisions": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 1}}}}] * 3)
        with self.assertRaises(SystemExit):
            cs.cmd_decide(st, ["r3_c0", "r3_c1"], [], [0], 20)
        self.assertIn("no decision for ['r3_c1']", st.verdicts[0])

    def test_siblings_decided_once_as_a_group(self):
        ops = [{"op": "abstract_state", "target": "m_{:d}".format(i)} for i in range(5)]
        pieces = {"r2_c0": dict(piece(), status="split"), "r3_c0": dict(piece(), cond="(x) & (a)", parent="r2_c0", ops=ops),
                  "r3_c1": dict(piece(), cond="(x) & (b)", parent="r2_c0", ops=ops)}
        st = FakeState(pieces, [{"decisions": {"g1": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 1}},
                                               "r3_c1": {"action": "abstract", "reason": "r", "ops": [{"op": "drop_assume"}]}}}])
        cs.cmd_decide(st, ["r3_c0", "r3_c1"], [], [0], 20)
        self.assertIn('O1: [{"op":"abstract_state","target":"m_{0..4}"}]', st.prompts[0])
        self.assertIn("- g1: 2 pieces;", st.prompts[0])
        self.assertIn("  parent r2_c0 with case x:", st.prompts[0])
        self.assertIn("r3_c1: case parent & (b)", st.prompts[0])
        self.assertEqual(st.s["pieces"]["r3_c0"]["status"], "split")
        self.assertEqual(st.s["pieces"]["r3_c1"]["ops"], [{"op": "drop_assume"}])


class FormatTest(unittest.TestCase):
    def test_fold_and_range_targets_round_trip(self):
        self.assertEqual(cs.fold(["a_0", "a_1", "a_2", "m_1", "m_2", "x"]), ["a_{0..2}", "m_1", "m_2", "x"])
        self.assertEqual(cs.fold(["r_00", "r_01", "r_02"]), ["r_00", "r_01", "r_02"])
        ops = [{"op": "abstract_state", "target": "f_{:d}".format(i)} for i in range(15)] + [{"op": "drop_assume"}]
        self.assertEqual(cs.expand_ops(cs.json.loads(cs.fmt_ops(ops))), ops)

    def test_cex_diff_keeps_differing_registers_in_the_cone(self):
        cex = {"coi": [["m_1", 1]], "table": [{"cycle": 0, "m_1": [0, 0], "m_2": [5, 0]},
                                              {"cycle": 1, "m_1": [3, 0], "m_2": [5, 0], "push": 1}]}
        self.assertEqual(cs.cex_diff(cex), ["cycle 1: m_1 abs 3/conc 0"])
        self.assertEqual(len(cs.cex_diff(dict(cex, coi=None))), 2)


if __name__ == "__main__":
    unittest.main()
