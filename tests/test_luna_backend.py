import http.client
import importlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"


def luna_response(text, reasoning_tokens=3):
    return {
        "reasoning": {"effort": "low"},
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


def deepseek_response(text, prompt_tokens=100):
    return {
        "model": "deepseek/deepseek-v4-flash",
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 10,
                  "completion_tokens_details": {"reasoning_tokens": 3}},
    }


class FakeHandle:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
        self.status = 200

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class LunaBackendTest(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.workdir.name)
        self.key_file = os.path.join(self.workdir.name, "key")
        with open(self.key_file, "w") as f:
            f.write("secret-key\n")
        sys.path.insert(0, str(SRC))
        check_module = types.ModuleType("check")
        check_module.check_implies = lambda *args: ("unsat", "a <= input1;", "input1", {"input1": 1})
        check_module.preserve_assignment_context = lambda original, model: "a <= 'bx;"
        sys.modules["check"] = check_module
        os.environ["LUNA_SESSION_ID"] = "test-session"
        self.luna = importlib.import_module("luna_api")
        self.luna.LUNA_KEY_FILE = self.key_file
        self.decision = importlib.import_module("luna_decision_api")
        self.requests = []

    def tearDown(self):
        os.chdir(self.cwd)
        self.workdir.cleanup()
        os.environ.pop("LUNA_SESSION_ID", None)
        os.environ.pop("LLM_BUDGET_USD", None)
        for name in ("luna_api", "luna_decision_api", "all_x_api", "check", "deepseek_chat",
                     "deepseek_decision_api", "deepseek_generate_api"):
            sys.modules.pop(name, None)
        sys.path.remove(str(SRC))

    def fake_urlopen(self, payloads):
        def urlopen(request, timeout):
            self.requests.append(request)
            payload = payloads.pop(0)
            if isinstance(payload, Exception):
                raise payload
            return FakeHandle(payload)
        return urlopen

    def records(self, name):
        with open(name) as f:
            return [json.loads(line) for line in f]

    def test_generate_mode_uses_responses_api_and_logs_without_key(self):
        with patch("urllib.request.urlopen", self.fake_urlopen([luna_response("a <= 'bx;")])):
            result = self.luna.run_api("bot", "message", "a <= b;", {}, None, {})

        self.assertEqual(result, ("a <= input1;", "unsat", "input1", {"input1": 1}))
        request = self.requests[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://opencode.ai/zen/go/v1/responses")
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["reasoning"], {"effort": "low"})
        self.assertEqual(body["input"], self.luna.initial_context + "message")
        self.assertEqual(request.get_header("X-opencode-session"), "test-session")
        self.assertEqual(request.get_header("User-agent"), "neuroabs-experiment/1.0")
        with open("luna_calls.jsonl") as f:
            self.assertNotIn("secret-key", f.read())
        record = self.records("rewrite_records.jsonl")[0]
        self.assertEqual(record["model_output"], "a <= 'bx;")
        self.assertEqual(record["usage"]["output_tokens_details"]["reasoning_tokens"], 3)

    def test_generate_mode_records_check_failure_without_rewrite(self):
        def broken(*args):
            raise Exception("Syntax error at 'x'")

        with patch("urllib.request.urlopen", self.fake_urlopen([luna_response("not rtl")])), \
                patch.object(self.luna, "check_implies", broken):
            result = self.luna.run_api("bot", "message", "a <= b;", {}, None, {})

        self.assertEqual(result, ("", "error", "", {}))
        self.assertEqual(self.records("rewrite_records.jsonl")[0]["check_error"], "Exception: Syntax error at 'x'")

    def test_rate_limit_pauses_and_retries_same_request(self):
        limited = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b"limit"))
        with patch("urllib.request.urlopen", self.fake_urlopen([limited, luna_response("a <= 'bx;")])), \
                patch("time.sleep") as sleep:
            self.luna.run_api("bot", "message", "a <= b;", {}, None, {})

        sleep.assert_called_once_with(self.luna.RATE_LIMIT_PAUSE)
        self.assertEqual([r["status"] for r in self.records("luna_calls.jsonl")], [429, 200])
        self.assertEqual(self.requests[0].data, self.requests[1].data)

    def test_long_rate_limit_stops_instead_of_waiting(self):
        limited = urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": "321631"}, io.BytesIO(b"weekly"))
        with patch("urllib.request.urlopen", self.fake_urlopen([limited])), patch("time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                self.luna.run_api("bot", "message", "a <= b;", {}, None, {})
        sleep.assert_not_called()

    def test_server_errors_are_retried_a_bounded_number_of_times(self):
        failures = [urllib.error.HTTPError("u", 503, "Unavailable", {}, io.BytesIO(b"busy"))
                    for _ in range(self.luna.TRANSIENT_RETRIES + 1)]
        with patch("urllib.request.urlopen", self.fake_urlopen(failures)), patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.luna.run_api("bot", "message", "a <= b;", {}, None, {})
        self.assertEqual(len(self.requests), self.luna.TRANSIENT_RETRIES + 1)

    def test_dropped_connection_is_retried(self):
        dropped = http.client.RemoteDisconnected("closed")
        with patch("urllib.request.urlopen", self.fake_urlopen([dropped, luna_response("a <= 'bx;")])), \
                patch("time.sleep"):
            self.luna.run_api("bot", "message", "a <= b;", {}, None, {})
        self.assertEqual([r["status"] for r in self.records("luna_calls.jsonl")], [None, 200])

    def test_client_error_is_not_retried(self):
        denied = urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(b"bad"))
        with patch("urllib.request.urlopen", self.fake_urlopen([denied])):
            with self.assertRaises(RuntimeError):
                self.luna.run_api("bot", "message", "a <= b;", {}, None, {})

    def test_decision_x_uses_trusted_rewrite(self):
        answer = json.dumps({"answer": "x", "probabilities": {"keep": 0.2, "x": 0.8}})
        with patch("urllib.request.urlopen", self.fake_urlopen([luna_response(answer)])), \
                patch.object(self.decision, "checked_rewrite", return_value=(("unsat", "a <= input1;", "input1", {}), None)) as checked:
            result = self.decision.run_api("bot", "message", "a <= b;", {}, None, {})

        self.assertEqual(result, ("a <= input1;", "unsat", "input1", {}))
        self.assertEqual(checked.call_args[0][:2], ("a <= b;", "a <= 'bx;"))
        body = json.loads(self.requests[0].data)
        self.assertEqual(body["instructions"], self.decision.decision_context)
        self.assertEqual(body["input"], "message")

    def test_decision_keep_does_not_rewrite(self):
        answer = json.dumps({"answer": "keep", "probabilities": {"keep": 0.7, "x": 0.3}})
        with patch("urllib.request.urlopen", self.fake_urlopen([luna_response(answer)])):
            result = self.decision.run_api("bot", "message", "a <= b;", {}, None, {})

        self.assertEqual(result, ("", "keep", "", {}))

    def test_malformed_decision_is_a_failure(self):
        cases = [
            "```json\n{\"answer\": \"x\", \"probabilities\": {\"keep\": 0.2, \"x\": 0.8}}\n```",
            json.dumps({"answer": "x"}),
            json.dumps({"answer": "drop", "probabilities": {"keep": 0.2, "x": 0.8}}),
            json.dumps({"answer": "x", "probabilities": {"keep": 0.5, "x": 0.8}}),
            json.dumps({"answer": "x", "probabilities": {"keep": True, "x": 0.0}}),
            json.dumps({"answer": "x", "probabilities": {"keep": 0.2, "x": 0.8}, "reason": "r"}),
        ]
        for text in cases:
            decision, error = self.decision.parse_decision(text)
            self.assertIsNone(decision, text)
            self.assertIsNotNone(error)
        with patch("urllib.request.urlopen", self.fake_urlopen([luna_response(cases[0])])):
            result = self.decision.run_api("bot", "message", "a <= b;", {}, None, {})
        self.assertEqual(result, ("", "invalid", "", {}))
        self.assertIsNotNone(self.records("rewrite_records.jsonl")[0]["parse_error"])

    def test_deepseek_decision_uses_gateway_chat_completions(self):
        answer = json.dumps({"answer": "keep", "probabilities": {"keep": 0.9, "x": 0.1}})
        backend = importlib.import_module("deepseek_decision_api")
        with patch("urllib.request.urlopen", self.fake_urlopen([deepseek_response(answer)])):
            result = backend.run_api("bot", "message", "a <= b;", {}, None, {})

        self.assertEqual(result, ("", "keep", "", {}))
        request = self.requests[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:35001/v1/chat/completions")
        self.assertNotIn("Authorization", request.headers)
        body = json.loads(request.data)
        self.assertEqual((body["model"], body["reasoning_effort"]), ("deepseek-v4-flash", "low"))
        self.assertEqual(body["messages"], [{"role": "system", "content": self.decision.decision_context},
                                            {"role": "user", "content": "message"}])
        self.assertEqual(len(self.records("deepseek_calls.jsonl")), 1)

    def test_deepseek_stops_at_budget(self):
        os.environ["LLM_BUDGET_USD"] = "0.0001"
        backend = importlib.import_module("deepseek_generate_api")
        with patch("urllib.request.urlopen", self.fake_urlopen([deepseek_response("a <= 'bx;", 1000)])):
            backend.run_api("bot", "message", "a <= b;", {}, None, {})
            with self.assertRaises(RuntimeError):
                backend.run_api("bot", "message", "a <= b;", {}, None, {})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.records("rewrite_records.jsonl")[0]["mode"], "generate")

    def test_all_x_backend_makes_no_api_call(self):
        backend = importlib.import_module("all_x_api")
        with patch("urllib.request.urlopen") as urlopen, \
                patch.object(self.decision, "checked_rewrite", return_value=(("unsat", "a <= input1;", "input1", {}), None)):
            result = backend.run_api("bot", "message", "a <= b;", {}, None, {})

        urlopen.assert_not_called()
        self.assertEqual(result, ("a <= input1;", "unsat", "input1", {}))
        self.assertEqual(self.records("rewrite_records.jsonl")[0]["mode"], "all_x")


if __name__ == "__main__":
    unittest.main()
