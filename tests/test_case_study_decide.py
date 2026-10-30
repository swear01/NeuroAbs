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
            {"pieces": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 4}},
                        "r3_c9": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 1}}}},
            {"pieces": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 3}},
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
            {"pieces": {"r3_c0": {"action": "resplit", "reason": "r", "split": {"index": "head", "bits": 1}}}}] * 3)
        with self.assertRaises(SystemExit):
            cs.cmd_decide(st, ["r3_c0", "r3_c1"], [], [0], 20)
        self.assertIn("no decision for ['r3_c1']", st.verdicts[0])


if __name__ == "__main__":
    unittest.main()
