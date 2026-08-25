import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"


class FakeOpenAI:
    calls = []
    requests = []

    def __new__(cls, **kwargs):
        cls.calls.append(kwargs)

        def create(**request):
            cls.requests.append(request)
            message = types.SimpleNamespace(content="abstracted RTL")
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message)]
            )

        return types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=create)
            )
        )


class MetaBackendTest(unittest.TestCase):
    def setUp(self):
        FakeOpenAI.calls.clear()
        FakeOpenAI.requests.clear()
        sys.path.insert(0, str(SRC))
        sys.modules["openai"] = types.SimpleNamespace(OpenAI=FakeOpenAI)
        check_module = types.ModuleType("check")
        check_module.check_implies = lambda *args: ("unsat", "replacement", "", {})
        sys.modules["check"] = check_module
        os.environ["META_API_KEY"] = "meta-secret"

    def tearDown(self):
        os.environ.pop("META_API_KEY", None)
        sys.modules.pop("meta_api", None)
        sys.modules.pop("openai", None)
        sys.modules.pop("check", None)
        sys.path.remove(str(SRC))

    def test_uses_meta_model_api_and_contributor_model(self):
        backend = importlib.import_module("meta_api")
        with patch.object(
            backend,
            "check_implies",
            return_value=("unsat", "replacement", "", {}),
        ):
            result = backend.run_api(
                "bot", "message", "statement", {}, None, {}
            )

        self.assertEqual(result, ("replacement", "unsat", "", {}))
        self.assertEqual(
            FakeOpenAI.calls,
            [
                {
                    "api_key": "meta-secret",
                    "base_url": "https://api.meta.ai/v1",
                }
            ],
        )
        request = FakeOpenAI.requests[0]
        self.assertEqual(request["model"], "muse-spark-1.2-contributor")
        self.assertEqual(
            request["messages"][1]["content"],
            backend.initial_context + "message",
        )


if __name__ == "__main__":
    unittest.main()
