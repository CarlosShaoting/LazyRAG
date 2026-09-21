from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _install_import_stubs() -> None:
    lazyllm = types.ModuleType('lazyllm')
    lazyllm.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor
    lazyllm_tools = types.ModuleType('lazyllm.tools')
    lazyllm_agent = types.ModuleType('lazyllm.tools.agent')
    lazyllm_agent.ToolExecutionError = RuntimeError
    lazyllm.tools = lazyllm_tools
    lazyllm_tools.agent = lazyllm_agent

    context = types.ModuleType('lazymind.chat.engine.subagent.context')
    context.require_context = lambda: None
    subagent_tools = types.ModuleType('lazymind.chat.engine.subagent.tools')
    subagent_tools._resolve_artifact_text = lambda value: str(value or '')
    subagent_tools._save_artifact = lambda **kwargs: {'ok': True, **kwargs}
    subagent_tools._workflow_client = lambda: None
    multimodal = types.ModuleType('lazymind.chat.engine.tools.multimodal')
    multimodal.image_generator = lambda *args, **kwargs: None
    static_file = types.ModuleType('lazymind.chat.service.utils.static_file_url')
    static_file._upload_root = lambda: Path(tempfile.gettempdir())
    static_file.local_path_from_static_file_url = lambda value: value
    model_config = types.ModuleType('lazymind.model_config')
    model_config.is_model_role_available = lambda _role: True

    sys.modules.update({
        'lazyllm': lazyllm,
        'lazyllm.tools': lazyllm_tools,
        'lazyllm.tools.agent': lazyllm_agent,
        'lazymind': types.ModuleType('lazymind'),
        'lazymind.chat': types.ModuleType('lazymind.chat'),
        'lazymind.chat.engine': types.ModuleType('lazymind.chat.engine'),
        'lazymind.chat.engine.subagent': types.ModuleType('lazymind.chat.engine.subagent'),
        'lazymind.chat.engine.subagent.context': context,
        'lazymind.chat.engine.subagent.tools': subagent_tools,
        'lazymind.chat.engine.tools': types.ModuleType('lazymind.chat.engine.tools'),
        'lazymind.chat.engine.tools.multimodal': multimodal,
        'lazymind.chat.service': types.ModuleType('lazymind.chat.service'),
        'lazymind.chat.service.utils': types.ModuleType('lazymind.chat.service.utils'),
        'lazymind.chat.service.utils.static_file_url': static_file,
        'lazymind.model_config': model_config,
    })


_install_import_stubs()
TOOLS_PATH = Path(__file__).resolve().parents[1] / 'tools.py'
SPEC = importlib.util.spec_from_file_location('ppt_page_receipts_test', TOOLS_PATH)
TOOLS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TOOLS)

PAGE_HTML = '<!doctype html><html><head><title>Page</title></head><body>ok</body></html>'


def _make_deck(root: Path, pages: int = 1) -> Path:
    deck = root / 'deck'
    page_dir = deck / 'pages'
    page_dir.mkdir(parents=True)
    (deck / 'outline.json').write_text(json.dumps({
        'pages': [{'page_no': page} for page in range(1, pages + 1)],
    }), encoding='utf-8')
    return deck


class PageCompletionReceiptTest(unittest.TestCase):
    def test_receipt_requires_both_generation_and_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            deck = _make_deck(Path(temp))
            (deck / 'pages' / 'page_001.html').write_text(PAGE_HTML, encoding='utf-8')
            TOOLS._record_page_execution(
                deck,
                1,
                generation_status='succeeded',
                publication_status='failed',
                error='publish failed',
            )

            issues, detail = TOOLS._ppt_completion_receipt_issues(deck, [1])

            self.assertIn('page 1 publication checkpoint is not succeeded', issues)
            self.assertEqual(detail['confirmed_pages'], [])

    def test_batch_retry_preserves_successful_pages_and_records_both_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            deck = _make_deck(Path(temp), pages=2)
            attempts = {1: 0, 2: 0}

            def capture(_command, current_deck: Path, page_no: int):
                attempts[page_no] += 1
                if page_no == 1 and attempts[page_no] == 1:
                    return 1, {'status': 'failed', 'error': 'HTTP 504'}
                (current_deck / 'pages' / f'page_{page_no:03d}.html').write_text(
                    PAGE_HTML,
                    encoding='utf-8',
                )
                return 0, {'status': 'ok'}

            runtime = mock.Mock()
            runtime._capture_cmd.side_effect = capture
            runtime.cmd_page_html = mock.Mock()
            with mock.patch.object(
                TOOLS, '_load_sn_ppt_modules', return_value=(mock.Mock(), runtime),
            ), mock.patch.object(
                TOOLS, '_load_slide_outline_briefs', return_value={},
            ), mock.patch.object(
                TOOLS, '_ui_slot_order_list', return_value=[],
            ), mock.patch.object(
                TOOLS, '_publish_one_page', side_effect=lambda _deck, page, **_kwargs: {
                    'page': page, 'ok': True, 'title_hint': f'Page {page}', 'bytes': 10,
                },
            ), mock.patch.object(
                TOOLS.time, 'sleep', return_value=None,
            ), mock.patch.dict(
                TOOLS.os.environ, {'LAZYMIND_PPT_PAGE_RETRIES': '1'}, clear=False,
            ):
                result = TOOLS._batch_page_html_publish_progressive(deck, concurrency=1)

            self.assertEqual(result['status'], 'ok')
            self.assertEqual(attempts, {1: 2, 2: 1})
            issues, detail = TOOLS._ppt_completion_receipt_issues(deck, [1, 2])
            self.assertEqual(issues, [])
            self.assertEqual(detail['confirmed_pages'], [1, 2])


if __name__ == '__main__':
    unittest.main()
