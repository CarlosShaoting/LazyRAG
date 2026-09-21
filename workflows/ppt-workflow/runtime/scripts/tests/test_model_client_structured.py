from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import model_client  # noqa: E402


class ModelClientStructuredToolTest(unittest.TestCase):
    def setUp(self) -> None:
        model_client.set_llm_impl(None)
        self.tool = {
            "type": "function",
            "function": {
                "name": "submit_deck_outline",
                "description": "Submit an outline",
                "parameters": {
                    "type": "object",
                    "properties": {"pages": {"type": "array"}},
                    "required": ["pages"],
                },
            },
        }

    def test_forces_named_tool_and_returns_its_arguments(self) -> None:
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "submit_deck_outline",
                            "arguments": '{"pages":[{"page_no":1}]}',
                        },
                    }],
                },
            }],
        }
        config = model_client.LLMConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )

        with mock.patch.object(
            model_client.LLMConfig, "from_env", return_value=config,
        ), mock.patch.object(model_client.httpx, "post", return_value=response) as post:
            raw = model_client.llm("system", "user", output_tool=self.tool)

        self.assertEqual(json.loads(raw), {"pages": [{"page_no": 1}]})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["tools"], [self.tool])
        self.assertEqual(payload["tool_choice"], {
            "type": "function",
            "function": {"name": "submit_deck_outline"},
        })

    def test_rejects_plain_text_when_tool_was_required(self) -> None:
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"pages": []}'}}],
        }
        config = model_client.LLMConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )

        with mock.patch.object(
            model_client.LLMConfig, "from_env", return_value=config,
        ), mock.patch.object(model_client.httpx, "post", return_value=response):
            with self.assertRaisesRegex(
                model_client.ModelClientError,
                "did not call submit_deck_outline",
            ):
                model_client.llm("system", "user", output_tool=self.tool)


if __name__ == "__main__":
    unittest.main()
