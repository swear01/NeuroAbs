import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"

UNITS = [
    {"id": "csr", "path": "RTL.csr_regfile", "module": "mkCSR_RegFile", "coi_state_bits": 480,
     "memories": [], "levels": ["keep", "cut"]},
    {"id": "icache", "path": "RTL.near_mem.icache", "module": "mkMMU_Cache", "coi_state_bits": 68782,
     "memories": [{"name": "RTL.near_mem.icache.ram_cword_set___RAM", "coi_state_bits": 65536},
                  {"name": "RTL.near_mem.icache.ram_state_and_ctag_cset___RAM", "coi_state_bits": 2688}],
     "levels": ["keep", "havoc", "cut"]},
]


class ChoiceModuleTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        sys.modules.pop("choice_abstraction", None)
        sys.modules.pop("choice_llm", None)
        self.abstraction = importlib.import_module("choice_abstraction")
        self.llm = importlib.import_module("choice_llm")

    def tearDown(self):
        self.directory.cleanup()
        sys.modules.pop("choice_abstraction", None)
        sys.modules.pop("choice_llm", None)
        sys.path.remove(str(SRC))


class AssignmentTest(ChoiceModuleTest):
    def test_levels_become_cutpoints(self):
        choices = self.abstraction.assignment_choices(UNITS, {"csr": "cut", "icache": "havoc"})
        self.assertEqual([(c["id"], c["kind"], c["unit"]) for c in choices],
                         [("csr", "module", "csr"), ("icache_m0", "memory", "icache"),
                          ("icache_m1", "memory", "icache")])
        self.assertEqual(self.abstraction.assignment_choices(UNITS, {}), [])

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            self.abstraction.assignment_choices(UNITS, {"csr": "havoc"})

    def test_memory_inside_a_cut_module_is_not_cut_again(self):
        choices = [{"id": "icache", "kind": "module", "target": "RTL.near_mem.icache"},
                   {"id": "icache_m0", "kind": "memory", "target": "RTL.near_mem.icache.ram_cword_set___RAM"},
                   {"id": "gpr_m0", "kind": "memory", "target": "RTL.gpr_regfile.regfile.arr"}]
        table = {"RTL.near_mem.icache": ("mkNear_Mem", "icache", "mkMMU_Cache")}
        renames = {os.path.join("sel", "icache.txt"): [("mkNear_Mem", "$auto$1", "choice__icache__0")]}
        lines = self.abstraction.cut_lines(choices, table, "sel", renames)
        self.assertIn("cutpoint mkNear_Mem/icache", lines)
        self.assertIn("cutpoint wrapper/RTL.gpr_regfile.regfile.arr", lines)
        self.assertNotIn("cutpoint wrapper/RTL.near_mem.icache.ram_cword_set___RAM", lines)
        self.assertIn("rename $auto$1 choice__icache__0", lines)
        self.assertLess(lines.index("cutpoint mkNear_Mem/icache"), lines.index("flatten"))

    def test_under_matches_hierarchy_boundaries(self):
        under = self.abstraction.under
        self.assertTrue(under("RTL.near_mem.icache.rg_state", "RTL.near_mem.icache"))
        self.assertTrue(under("RTL.near_mem.icache$valid", "RTL.near_mem.icache"))
        self.assertTrue(under("RTL.gpr_regfile.regfile.arr[3]", "RTL.gpr_regfile.regfile.arr"))
        self.assertFalse(under("RTL.near_mem.icache2.rg_state", "RTL.near_mem.icache"))


class Ric3CheckTest(ChoiceModuleTest):
    def fake_ric3(self, body):
        path = self.root / "ric3"
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        os.environ["RIC3_BIN"] = str(path)
        self.addCleanup(os.environ.pop, "RIC3_BIN")

    def test_unsat(self):
        self.fake_ric3("echo info\necho UNSAT\n")
        verdict, depth, _ = self.abstraction.ric3_check("m.btor2", 10, str(self.root / "log"))
        self.assertEqual((verdict, depth), ("UNSAT", None))

    def test_sat_reports_the_last_frame(self):
        self.fake_ric3("echo SAT\necho sat\necho b0\necho '#0'\necho '@0'\necho '0 1'\necho '@1'\necho '@2'\necho .\n")
        verdict, depth, _ = self.abstraction.ric3_check("m.btor2", 10, str(self.root / "log"))
        self.assertEqual((verdict, depth), ("SAT", 2))

    def test_panic_at_the_time_limit_is_a_timeout(self):
        self.fake_ric3("sleep 2\necho panicked\nexit 101\n")
        self.assertEqual(self.abstraction.ric3_check("m.btor2", 1, str(self.root / "log"))[0], "TIMEOUT")

    def test_failure_is_an_error(self):
        self.fake_ric3("echo UNSAT\nexit 3\n")
        self.assertEqual(self.abstraction.ric3_check("m.btor2", 10, str(self.root / "log"))[0], "ERROR")


class CegarTest(ChoiceModuleTest):
    def run_cegar(self, refine):
        from unittest.mock import patch
        verdicts = iter([("SAT", 3, 1.0), ("SAT", 3, 1.0), ("UNSAT", None, 1.0)])
        free = {"RTL.choice__csr__0", "RTL.near_mem.choice__icache__0", "RTL.near_mem.choice__icache__1"}
        a = self.abstraction
        with patch.object(a, "build", return_value=[]), \
                patch.object(a, "ric3_check", side_effect=lambda *args: next(verdicts)), \
                patch.object(a, "coi_state_bits", return_value={}), \
                patch.object(a.btor_witness, "free_names", return_value=free):
            return a.cegar("w.v", "ila", UNITS, {"csr": "cut", "icache": "cut"}, str(self.root), 10, 5, refine)

    def test_refine_all_moves_every_unit_in_the_counterexample(self):
        result = self.run_cegar("all")
        self.assertEqual(result["history"][0]["refined_units"], ["csr", "icache"])
        self.assertEqual(result["history"][1]["assignment"], {"csr": "keep", "icache": "havoc"})

    def test_refine_one_moves_the_unit_with_most_free_values(self):
        result = self.run_cegar("one")
        self.assertEqual(result["history"][0]["counterexample_units"], {"csr": 1, "icache": 2})
        self.assertEqual(result["history"][1]["assignment"], {"csr": "cut", "icache": "havoc"})
        self.assertEqual(result["status"], "UNSAT")


class ParseChoicesTest(ChoiceModuleTest):
    def answer(self, choices):
        return json.dumps({"choices": choices})

    def test_valid_answer(self):
        text = self.answer({"csr": {"answer": "keep", "probabilities": {"keep": 0.7, "cut": 0.3}},
                            "icache": {"answer": "cut", "probabilities": {"keep": 0.1, "havoc": 0.3, "cut": 0.6}}})
        assignment, probabilities, errors = self.llm.parse_choices(text, UNITS)
        self.assertEqual(assignment, {"csr": "keep", "icache": "cut"})
        self.assertEqual(errors, {})
        self.assertEqual(probabilities["icache"]["cut"], 0.6)

    def test_invalid_units_are_reported_and_left_out(self):
        text = self.answer({"csr": {"answer": "havoc", "probabilities": {"keep": 0.5, "cut": 0.5}},
                            "icache": {"answer": "cut", "probabilities": {"keep": 0.5, "havoc": 0.5, "cut": 0.5}},
                            "bpred": {"answer": "cut", "probabilities": {"keep": 0.5, "cut": 0.5}}})
        assignment, _, errors = self.llm.parse_choices(text, UNITS)
        self.assertEqual(assignment, {})
        self.assertEqual(set(errors), {"csr", "icache", "*"})

    def test_markdown_is_invalid(self):
        assignment, _, errors = self.llm.parse_choices("```json\n{}\n```", UNITS)
        self.assertEqual(assignment, {})
        self.assertIn("*", errors)

    def test_message_lists_units_and_assertions(self):
        ports = {"csr": ["read_csr[33]"], "icache": ["valid[1]", "cword[64]"]}
        message = self.llm.build_message(UNITS, ports, "ADD check", ["assign variable_map_assert__p1__ = a;"])
        self.assertIn("- id: icache", message)
        self.assertIn("memories: ram_cword_set___RAM (65536 bits)", message)
        self.assertIn("assign variable_map_assert__p1__ = a;", message)
        self.assertIn("levels: keep, havoc, cut", message)


if __name__ == "__main__":
    unittest.main()
