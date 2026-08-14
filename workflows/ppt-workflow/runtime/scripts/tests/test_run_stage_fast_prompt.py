from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_stage  # noqa: E402


class PagePromptModeTest(unittest.TestCase):
    def _deck(self, root: Path) -> Path:
        deck = root / "deck"
        (deck / "pages").mkdir(parents=True)
        fixtures = {
            "task_pack.json": {"params": {"language": "zh-Hans", "page_count": 1}},
            "info_pack.json": {"user_query": "生成一页测试幻灯片", "user_assets": {}},
            "style_spec.json": {
                "palette": {"primary": "#2563EB", "accent": "#0EA5E9"},
                "typography": {"font_family": "Noto Sans SC"},
            },
            "outline.json": {
                "pages": [{
                    "page_no": 1,
                    "page_kind": "content",
                    "title": "快速生成",
                    "subtitle": "一次模型调用",
                    "bullets": [{"head": "目标", "detail": "减少等待时间"}],
                    "narrative": "保留结构化内容并直接生成 HTML。",
                    "data_points": [],
                    "visual_hints": "左右布局",
                    "use_table": None,
                    "use_image": None,
                }],
            },
            "asset_plan.json": {"pages": [{"page_no": 1, "slots": []}]},
        }
        for name, value in fixtures.items():
            (deck / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return deck

    def test_deterministic_mode_makes_one_model_call(self) -> None:
        html = "<!DOCTYPE html><html><head><title>快速生成</title></head><body><div class='wrapper'><div id='ct'>完成</div></div></body></html>"
        calls: list[tuple[str, str]] = []

        def fake_llm(system: str, user: str, **_kwargs) -> str:
            calls.append((system, user))
            return html

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"PPT_PAGE_PROMPT_MODE": "deterministic"}
        ), patch.object(run_stage, "llm", side_effect=fake_llm):
            deck = self._deck(Path(temp))
            self.assertEqual(run_stage.cmd_page_html(deck, 1), 0)
            self.assertEqual(len(calls), 1)
            self.assertIn("CONTENT BRIEF (JSON)", calls[0][1])
            self.assertEqual((deck / "pages" / "page_001.html").read_text(encoding="utf-8"), html)

    def test_legacy_mode_keeps_two_model_calls(self) -> None:
        html = "<!DOCTYPE html><html><head><title>快速生成</title></head><body><div class='wrapper'><div id='ct'>完成</div></div></body></html>"
        replies = iter(["自然语言页面要求", html])
        calls: list[tuple[str, str]] = []

        def fake_llm(system: str, user: str, **_kwargs) -> str:
            calls.append((system, user))
            return next(replies)

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"PPT_PAGE_PROMPT_MODE": "llm-rewrite"}
        ), patch.object(run_stage, "llm", side_effect=fake_llm):
            deck = self._deck(Path(temp))
            self.assertEqual(run_stage.cmd_page_html(deck, 1), 0)
            self.assertEqual(len(calls), 2)
            self.assertIn("自然语言页面要求", calls[1][1])

    def test_editable_brief_reuses_deck_wide_style(self) -> None:
        html = "<!DOCTYPE html><html><head><title>统一风格</title></head><body><div class='wrapper'><div id='ct'>完成</div></div></body></html>"
        calls: list[tuple[str, str]] = []

        def fake_llm(system: str, user: str, **_kwargs) -> str:
            calls.append((system, user))
            return html

        with tempfile.TemporaryDirectory() as temp, patch.object(
            run_stage, "llm", side_effect=fake_llm
        ):
            deck = self._deck(Path(temp))
            brief = "主题内容：端午节习俗。采用上下布局。"
            self.assertEqual(run_stage.cmd_page_html_from_brief(deck, 1, brief), 0)
            self.assertEqual(len(calls), 1)
            query = calls[0][1]
            self.assertIn("PAGE BRIEF", query)
            self.assertIn(brief, query)
            self.assertIn("VISUAL DESIGN CONTRACT (JSON)", query)
            self.assertIn("#2563EB", query)
            self.assertIn("shared by every slide", query)


if __name__ == "__main__":
    unittest.main()
