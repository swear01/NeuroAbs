import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"

UNITS = [
    {"id": "csr", "path": "RTL.csr_regfile", "module": "mkCSR_RegFile", "coi_state_bits": 480,
     "memories": [], "levels": ["keep", "cut"]},
    {"id": "gpr", "path": "RTL.gpr_regfile.regfile", "module": "RegFile", "coi_state_bits": 1024,
     "memories": [{"name": "RTL.gpr_regfile.regfile.arr", "coi_state_bits": 1024}],
     "levels": ["keep", "havoc", "cut"]},
    {"id": "icache", "path": "RTL.near_mem.icache", "module": "mkMMU_Cache", "coi_state_bits": 378,
     "memories": [], "levels": ["keep", "cut"]},
]


class ChoiceRefineTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        for name in ("choice_refine", "choice_abstraction", "choice_llm"):
            sys.modules.pop(name, None)
        self.refine = importlib.import_module("choice_refine")
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.wrapper = self.root / "wrapper.v"
        self.wrapper.write_text("  assign variable_map_assert__p1__ = a == b;\n  assign other = 1;\n")

    def tearDown(self):
        self.directory.cleanup()
        for name in ("choice_refine", "choice_abstraction", "choice_llm"):
            sys.modules.pop(name, None)
        sys.path.remove(str(SRC))

    def context(self):
        counterexample = [{"unit": "csr", "name": "choice__csr__0", "frame": 3},
                          {"unit": "csr", "name": "choice__csr__0", "frame": 5},
                          {"unit": "csr", "name": "choice__csr__1", "frame": 4},
                          {"unit": "gpr", "name": "choice__gpr__2", "frame": 7}]
        history = [{"iteration": 0, "cex_depth": 6, "counterexample_units": {"csr": 2, "gpr": 1, "icache": 3},
                    "refined_units": ["icache"]},
                   {"iteration": 1}]
        return {"wrapper": str(self.wrapper), "prop": "ila", "units": UNITS,
                "assignment": {"csr": "cut", "gpr": "cut", "icache": "keep"}, "model": str(self.root / "m.btor2"),
                "coi_state_bits": 3000, "cex_depth": 8, "counterexample": counterexample,
                "counts": {"csr": 3, "gpr": 1}, "history": history, "models_dir": str(self.root / "models"),
                "time_limit": 60, "workdir": str(self.root)}


class BmcTest(ChoiceRefineTest):
    def run_bmc(self, outcomes):
        ca = self.refine.ca

        def model(wrapper, prop, units, assignment, models_dir):
            unit = "csr" if assignment["csr"] == "keep" else "gpr"
            return {"model": unit, "coi_state_bits": {"csr": 3480, "gpr": 3100}[unit], "build_seconds": 2.0}

        def verdict(info, bound, time_limit):
            self.assertEqual(bound, 8)
            bmc, depth = outcomes[info["model"]]
            return {"bmc": bmc, "cex_depth": depth, "bmc_seconds": 1.5}

        with patch.object(ca, "abstract_model", side_effect=model), \
                patch.object(ca, "bmc_verdict", side_effect=verdict):
            return self.refine.refine_bmc(self.context())

    def test_smallest_model_without_counterexample(self):
        result = self.run_bmc({"csr": ("NONE", None), "gpr": ("NONE", None)})
        self.assertEqual(result["refined"], ["gpr"])
        self.assertEqual(result["seconds"], 1.5 * 2 + 2.0)
        self.assertEqual([c["level"] for c in result["candidates"]], ["keep", "havoc"])

    def test_removing_the_counterexample_beats_size(self):
        result = self.run_bmc({"csr": ("NONE", None), "gpr": ("SAT", 8)})
        self.assertEqual(result["refined"], ["csr"])

    def test_deepest_counterexample_when_none_is_removed(self):
        result = self.run_bmc({"csr": ("SAT", 8), "gpr": ("SAT", 6)})
        self.assertEqual(result["refined"], ["csr"])

    def test_bmc_error_stops(self):
        with self.assertRaises(RuntimeError):
            self.run_bmc({"csr": ("ERROR", None), "gpr": ("SAT", 6)})


class MessageTest(ChoiceRefineTest):
    def test_message_summarises_the_counterexample(self):
        signals = {"choice__csr__0": "RTL.csr_regfile$read_mstatus", "choice__gpr__2": "RTL.gpr_regfile$read_rs1"}
        message = self.refine.build_message("ADDI check", ["assign variable_map_assert__p1__ = a == b;"],
                                            self.context(), signals)
        self.assertIn("ADDI check", message)
        self.assertIn("assign variable_map_assert__p1__ = a == b;", message)
        self.assertIn("The counterexample has 9 cycles, 0 to 8; the property fails in cycle 8.", message)
        self.assertIn("level: cut; refining moves it to havoc", message)
        self.assertIn("unconstrained values in the counterexample: 3", message)
        self.assertIn("RTL.csr_regfile$read_mstatus (cycles 3, 5); choice__csr__1 (cycle 4)", message)
        self.assertIn("Candidate units: csr, gpr", message)
        self.assertIn("- iteration 0: counterexample of 7 cycles with unconstrained values from csr (2), gpr (1), "
                      "icache (3); refined icache.", message)
        self.assertNotIn("icache\n  level: keep;", message)

    def test_signals_are_limited(self):
        values = [{"unit": "csr", "name": "choice__csr__{:d}".format(i), "frame": i} for i in range(10)]
        text = self.refine.unit_signals(values, {})
        self.assertEqual(text.count("choice__csr__"), self.refine.MAX_SIGNALS)
        self.assertTrue(text.endswith("and 2 more signals"))


class ParseTest(ChoiceRefineTest):
    def test_valid(self):
        text = json.dumps({"refine": "gpr", "probabilities": {"gpr": 0.8, "csr": 0.2}, "reason": "GPRs"})
        self.assertEqual(self.refine.parse_refinement(text, {"csr", "gpr"}), ("gpr", {"gpr": 0.8, "csr": 0.2}, "GPRs"))

    def test_invalid(self):
        for answer in ["```{}```",
                       json.dumps({"refine": "icache", "probabilities": {"gpr": 0.5, "csr": 0.5}, "reason": ""}),
                       json.dumps({"refine": "gpr", "probabilities": {"gpr": 0.5}, "reason": ""}),
                       json.dumps({"refine": "gpr", "probabilities": {"gpr": 0.5, "csr": 0.1}, "reason": ""}),
                       json.dumps({"refine": "gpr", "probabilities": {"gpr": 0.5, "csr": 0.5}}),
                       json.dumps({"refine": ["gpr"], "probabilities": {"gpr": 0.5, "csr": 0.5}, "reason": ""})]:
            with self.assertRaises(ValueError):
                self.refine.parse_refinement(answer, {"csr", "gpr"})


class LlmTest(ChoiceRefineTest):
    def run_llm(self, answer):
        calls = []

        def call(instructions, message, request_id):
            calls.append((instructions, message))
            return {"model": "deepseek/x", "usage": {"prompt_tokens": 10}}, 0.7

        signals = {"signals": {"choice__csr__0": "RTL.csr_regfile$read_mstatus"}, "seconds": 1.0}
        with patch.object(self.refine, "model_signals", return_value=signals):
            result = self.refine.refine_llm(self.context(), "ADDI check", call, lambda response: answer,
                                            lambda usage: 0.001)
        return result, calls

    def test_answer_is_applied_and_stored(self):
        answer = json.dumps({"refine": "gpr", "probabilities": {"gpr": 0.9, "csr": 0.1}, "reason": "GPRs"})
        result, calls = self.run_llm(answer)
        self.assertEqual(result["refined"], ["gpr"])
        self.assertEqual(result["seconds"], 1.7)
        self.assertEqual(result["llm_seconds"], 0.7)
        self.assertEqual(calls[0][0], self.refine.refine_context)
        self.assertIn("RTL.csr_regfile$read_mstatus", calls[0][1])
        stored = json.loads((self.root / "refine-iter1.json").read_text())
        self.assertEqual(stored["refine"], "gpr")
        self.assertEqual(stored["cost_usd"], 0.001)

    def test_invalid_answer_stops(self):
        with self.assertRaises(RuntimeError):
            self.run_llm("gpr")
        self.assertIn("error", json.loads((self.root / "refine-iter1.json").read_text()))


if __name__ == "__main__":
    unittest.main()
