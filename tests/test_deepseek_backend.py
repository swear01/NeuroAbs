import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"


class FakeCompletions:
    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = types.SimpleNamespace(content="abstracted RTL")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class FakeOpenAI:
    calls = []
    completions = FakeCompletions()

    def __new__(cls, **kwargs):
        cls.calls.append(kwargs)
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=cls.completions)
        )


class DeepSeekBackendTest(unittest.TestCase):
    def setUp(self):
        FakeOpenAI.calls.clear()
        FakeOpenAI.completions.requests.clear()
        sys.path.insert(0, str(SRC))
        sys.modules["openai"] = types.SimpleNamespace(OpenAI=FakeOpenAI)
        check_module = types.ModuleType("check")
        check_module.check_implies = lambda *args: ("unsat", "replacement", "", {})
        sys.modules["check"] = check_module
        sys.modules.pop("deepseek_api", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        self.backend = importlib.import_module("deepseek_api")

    def tearDown(self):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        sys.modules.pop("deepseek_api", None)
        sys.modules.pop("openai", None)
        sys.modules.pop("check", None)
        sys.path.remove(str(SRC))

    def test_client_is_created_lazily(self):
        self.assertEqual(FakeOpenAI.calls, [])

    def test_request_uses_local_gateway_without_external_key(self):
        with patch.object(
            self.backend,
            "check_implies",
            return_value=("unsat", "replacement", "", {}),
        ):
            result = self.backend.run_api(
                "bot", "message", "statement", {}, None, {}
            )

        self.assertEqual(result, ("replacement", "unsat", "", {}))
        self.assertEqual(
            FakeOpenAI.calls,
            [
                {
                    "api_key": "local-gateway",
                    "base_url": "http://127.0.0.1:35001/v1",
                }
            ],
        )

    def test_request_uses_v4_flash_without_thinking(self):
        os.environ["DEEPSEEK_API_KEY"] = "secret"
        with patch.object(
            self.backend,
            "check_implies",
            return_value=("unsat", "replacement", "", {}),
        ):
            result = self.backend.run_api(
                "bot", "message", "statement", {}, None, {}
            )

        self.assertEqual(result, ("replacement", "unsat", "", {}))
        self.assertEqual(
            FakeOpenAI.calls,
            [
                {
                    "api_key": "local-gateway",
                    "base_url": "http://127.0.0.1:35001/v1",
                }
            ],
        )
        request = FakeOpenAI.completions.requests[0]
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})

    def test_deepseek_sources_do_not_bypass_gateway(self):
        for filename in ("deepseek.py", "deepseek_api.py"):
            self.assertNotIn("api.deepseek.com", (SRC / filename).read_text())


if __name__ == "__main__":
    unittest.main()
