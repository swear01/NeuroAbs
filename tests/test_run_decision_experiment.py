import importlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"


class RunRic3Test(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        sys.modules.pop("run_decision_experiment", None)
        self.experiment = importlib.import_module("run_decision_experiment")
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()
        sys.modules.pop("run_decision_experiment", None)
        sys.path.remove(str(SRC))

    def fake_ric3(self, body):
        path = self.root / "ric3"
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return str(path)

    def run_ric3(self, body, time_limit=5):
        return self.experiment.run_ric3(self.fake_ric3(body), "model.btor2", time_limit, str(self.root / "log"))

    def test_passes_check_portfolio_arguments(self):
        result = self.run_ric3('echo "$@"\necho UNSAT\n')
        self.assertEqual("UNSAT", result["verdict"])
        self.assertEqual("check --ui false model.btor2 portfolio --time-limit 5",
                         (self.root / "log").read_text().splitlines()[0])

    def test_reads_verdict_from_last_line(self):
        self.assertEqual("SAT", self.run_ric3("echo '[INFO] bmc proved at depth 3'\necho SAT\n")["verdict"])
        self.assertEqual("UNKNOWN", self.run_ric3("echo UNKNOWN\n")["verdict"])

    def test_nonzero_exit_or_missing_verdict_is_error(self):
        self.assertEqual("ERROR", self.run_ric3("echo UNSAT\nexit 101\n")["verdict"])
        self.assertEqual("ERROR", self.run_ric3("echo UNSAT\necho trailing\n")["verdict"])

    def test_kills_process_group_after_cap(self):
        self.experiment.RIC3_KILL_GRACE = 0
        result = self.run_ric3("sleep 30 &\nsleep 30\n", time_limit=1)
        self.assertEqual("TIMEOUT", result["verdict"])
        self.assertLess(result["seconds"], 10)

    def test_rejects_duplicate_model_labels(self):
        argv = ["run_decision_experiment.py", "time", "--ric3", "ric3", "--repeats", "1", "--time-limit", "1",
                "--parallel", "1", "--output", str(self.root / "t.json"), "--model", "a=x.btor2", "--model", "a=y.btor2"]
        with patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()), \
                patch.object(self.experiment, "time_models") as time_models:
            with self.assertRaises(SystemExit):
                self.experiment.main()
        time_models.assert_not_called()

    def test_usage_summary_skips_unparsable_responses(self):
        records = [{"status": 200, "response_raw": "", "elapsed_seconds": 1.0},
                   {"status": 200, "response_raw": '{"usage": {"prompt_tokens": 10}}', "elapsed_seconds": 2.0}]
        self.assertEqual(self.experiment.deepseek_usage_summary(records)["prompt_tokens"], 10)
        self.assertEqual(self.experiment.usage_summary(records)["successful_calls"], 1)


if __name__ == "__main__":
    unittest.main()
