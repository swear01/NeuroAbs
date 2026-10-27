import importlib
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"

CHOICES = [
    {"id": "csr_regfile", "kind": "unit", "levels": ["keep", "cut"]},
    {"id": "gpr0", "kind": "gpr", "register": 0, "levels": ["keep", "word", "havoc"]},
    {"id": "gpr1", "kind": "gpr", "register": 1, "levels": ["keep", "word", "havoc"]},
    {"id": "uf0", "kind": "operator", "ila_node": "n1", "rtl_node": "r1", "levels": ["keep", "uf"]},
]
DESIGN = {"description": "", "operand_fields": ["rs1"], "choices": CHOICES, "gpr_assumptions": {"0": [], "1": []}}
SUBS = [
    {"name": "x1.frame", "states": ["x1"], "case": "rd!=1", "case_terms": [{"field": "rd", "op": "!=", "value": 1}],
     "assertion": []},
    {"name": "mem", "states": ["pc", "x0"], "case": None, "case_terms": [], "assertion": []},
]

GOOD = '''
def kept(sub):
    return {int(s[1:]) for s in sub["states"] if s.startswith("x")}

def choose(sub, design):
    keep = kept(sub)
    out = {}
    for c in design["choices"]:
        if c["kind"] == "gpr":
            out[c["id"]] = "keep" if c["register"] in keep else "havoc"
        else:
            out[c["id"]] = c["levels"][-1]
    return out
'''


class LlmRuleExecTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        self.addCleanup(sys.path.remove, str(SRC))
        self.exec = importlib.import_module("llm_rule_exec")
        self.rule = importlib.import_module("llm_rule")

    def test_accepts_plain_rule(self):
        self.assertEqual(self.exec.validate(GOOD), [])

    def test_rejects_escapes(self):
        cases = {
            "import os\ndef choose(sub, design):\n    return {}\n": "Import",
            "def choose(sub, design):\n    return ().__class__\n": "__class__",
            "def choose(sub, design):\n    return '{0.x}'.format(sub)\n": "format",
            "def choose(sub, design):\n    f = sub.get\n    return f\n": "must be called",
            "def choose(sub, design):\n    while True:\n        pass\n": "While",
            "def choose(sub, design):\n    return open('x')\n": None,
            "x = 1\ndef choose(sub, design):\n    return {}\n": "top level",
            "def choose(sub, design):\n    _x = 1\n    return {}\n": "underscore",
            "def choose(sub, design):\n    try:\n        return {}\n    except KeyError:\n        return {}\n": "Try",
            "def helper(sub):\n    return {}\n": "no top-level function choose",
            "def choose(sub, design):\n    return {}\n    (": "syntax error",
        }
        for source, reason in cases.items():
            errors = self.exec.validate(source)
            if reason is None:
                self.assertEqual(errors, [])
                results = self.rule.run_rule(source, DESIGN, SUBS)
                self.assertTrue(all(r["error"].startswith("NameError") for r in results))
            else:
                self.assertTrue(any(reason in e for e in errors), (source, errors))

    def test_load_has_no_builtins_beyond_whitelist(self):
        choose = self.exec.load("def choose(sub, design):\n    return eval('1')\n")
        with self.assertRaises(NameError):
            choose({}, {})

    def test_run_rule_in_subprocess(self):
        results = self.rule.run_rule(GOOD, DESIGN, SUBS)
        self.assertEqual(results[0], {"name": "x1.frame", "output": {"csr_regfile": "cut", "gpr0": "havoc",
                                                                     "gpr1": "keep", "uf0": "uf"}})
        self.assertEqual(results[1]["output"]["gpr0"], "keep")

    def test_rule_error_is_reported_per_sub_property(self):
        source = "def choose(sub, design):\n    return {c['id']: c['levels'][0] for c in design['choices']} " \
                 "if sub['case'] else sub['missing']\n"
        results = self.rule.run_rule(source, DESIGN, SUBS)
        self.assertIn("output", results[0])
        self.assertTrue(results[1]["error"].startswith("KeyError"))

    def test_undefined_name_is_reported_per_sub_property(self):
        source = "def choose(sub, design):\n    return isinstance(sub, dict)\n"
        self.assertEqual(self.exec.validate(source), [])
        results = self.rule.run_rule(source, DESIGN, SUBS)
        self.assertTrue(all(r["error"].startswith("NameError") for r in results))

    def test_memory_limit_rejects_rule(self):
        with self.assertRaises(RuntimeError):
            self.rule.run_rule("def choose(sub, design):\n    return [0] * (1 << 31)\n", DESIGN, SUBS)

    def test_rule_cannot_change_inputs_of_later_calls(self):
        source = "def choose(sub, design):\n    n = len(design['choices'])\n    design['choices'].append(1)\n" \
                 "    return {'n': n}\n"
        results = self.rule.run_rule(source, DESIGN, SUBS)
        self.assertEqual([r["output"]["n"] for r in results], [4, 4])

    def test_check_output(self):
        check = self.rule.check_output
        good = {"csr_regfile": "cut", "gpr0": "keep", "gpr1": "word", "uf0": "uf"}
        self.assertEqual(check(good, CHOICES), [])
        self.assertTrue(check(dict(good, gpr1="cut"), CHOICES))
        self.assertTrue(check({k: v for k, v in good.items() if k != "uf0"}, CHOICES))
        self.assertTrue(check(dict(good, gpr2="keep"), CHOICES))
        self.assertTrue(check([], CHOICES))

    def test_check_output_rejects_two_pairings_of_one_node(self):
        choices = [{"id": "uf0", "kind": "operator", "ila_node": "n1", "rtl_node": "r1", "levels": ["keep", "uf"]},
                   {"id": "uf1", "kind": "operator", "ila_node": "n1", "rtl_node": "r2", "levels": ["keep", "uf"]},
                   {"id": "uf2", "kind": "operator", "ila_node": "n2", "rtl_node": "r2", "levels": ["keep", "uf"]}]
        check = self.rule.check_output
        self.assertEqual(check({"uf0": "uf", "uf1": "keep", "uf2": "uf"}, choices), [])
        self.assertEqual(check({"uf0": "uf", "uf1": "uf", "uf2": "keep"}, choices),
                         ["more than one operator choice at level uf has ila_node n1"])
        self.assertEqual(check({"uf0": "keep", "uf1": "uf", "uf2": "uf"}, choices),
                         ["more than one operator choice at level uf has rtl_node r2"])

    def test_operand_sources(self):
        text = ("module ila(a);\nassign n3 = ( n1 ) + ( n2 ) ;\nassign n1 = inst[19:15] ;\n"
                "assign n2 = { {20{n4[11]} }, n4} ;\nassign n4 = inst[31:20] ;\nendmodule\n"
                "module wrapper(clk);\n ila ILA(.a(clk));\nendmodule\n")
        self.assertEqual(self.rule.operand_sources(text, "ILA", ["n1", "n2"]),
                         ["n1 = inst[19:15]", "n2 = { {20{n4[11]} }, n4}", "n4 = inst[31:20]"])

    def test_apply_rule_rejects_invalid_output(self):
        source = "def choose(sub, design):\n    return {'csr_regfile': 'cut'}\n"
        specs, errors = self.rule.apply_rule(source, DESIGN, SUBS, SUBS, [])
        self.assertEqual(specs, {})
        self.assertEqual(sorted(errors), ["mem", "x1.frame"])

    def test_apply_rule_spec(self):
        ufs = [{"ila": "n1", "rtl": "r1"}]
        subs = [dict(SUBS[0], rd_guard=True), SUBS[1]]
        specs, errors = self.rule.apply_rule(GOOD, DESIGN, SUBS, subs, ufs)
        self.assertEqual(errors, {})
        self.assertTrue(specs["x1.frame"]["rd_guard"])
        self.assertFalse(specs["mem"]["rd_guard"])
        with self.assertRaises(ValueError):
            self.rule.apply_rule(GOOD, DESIGN, SUBS, subs[::-1], ufs)
        self.assertEqual(specs["x1.frame"]["keep_gprs"], list(range(1, 32)))
        self.assertEqual(specs["x1.frame"]["units"], {"csr_regfile": "cut"})
        self.assertEqual(specs["x1.frame"]["uf"], ufs)

    def test_extract_rule(self):
        self.assertEqual(self.rule.extract_rule("text\n```python\ndef choose(s, d):\n    return {}\n```\n"),
                         "def choose(s, d):\n    return {}\n")
        with self.assertRaises(ValueError):
            self.rule.extract_rule("```python\na\n```\n```python\nb\n```")
        with self.assertRaises(ValueError):
            self.rule.extract_rule("no code")

    def test_normal_ignores_order(self):
        a = {"keep_gprs": [2, 1], "word_gprs": [], "units": {"b": "cut", "a": "keep"}, "uf": []}
        b = {"keep_gprs": [1, 2], "units": {"a": "keep", "b": "cut"}, "uf": [], "states": ["x1"]}
        self.assertEqual(self.rule.normal(a), self.rule.normal(b))


class ClaudeCliTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        self.addCleanup(sys.path.remove, str(SRC))
        self.cli = importlib.import_module("claude_cli")

    def events(self, tools=(), content=({"type": "text", "text": "ok"},), result=None):
        import json
        return [json.dumps(e) for e in (
            {"type": "system", "subtype": "init", "model": "m", "tools": list(tools), "mcp_servers": []},
            {"type": "assistant", "message": {"model": "m", "content": list(content)}},
            result or {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1})]

    def test_parse_answer(self):
        init, answer, models, result = self.cli.parse_events(self.events())
        self.assertEqual((answer, models), ("ok", ["m"]))

    def test_rejects_tools(self):
        with self.assertRaises(RuntimeError):
            self.cli.parse_events(self.events(tools=["Read"]))
        with self.assertRaises(RuntimeError):
            self.cli.parse_events(self.events(content=[{"type": "tool_use", "name": "Read"}]))
        with self.assertRaises(RuntimeError):
            self.cli.parse_events(self.events(result={"type": "result", "subtype": "error_max_turns",
                                                      "is_error": True, "num_turns": 2}))

    def test_clean_command(self):
        args = self.cli.command("sys", "id", False)
        for flag in ("--tools", "--safe-mode", "--strict-mcp-config", "--system-prompt", "--session-id"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--resume", self.cli.command("sys", "id", True))


if __name__ == "__main__":
    unittest.main()
