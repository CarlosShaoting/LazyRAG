import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyllm.tools.agent import ToolExecutionError


TOOLS_PATH = Path(__file__).resolve().parents[1] / 'tools.py'
SPEC = importlib.util.spec_from_file_location('ppt_workflow_background_test', TOOLS_PATH)
TOOLS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TOOLS)


class BackgroundImageGenerationTest(unittest.TestCase):
    def _deck(self, root: Path) -> Path:
        deck = root / 'deck'
        (deck / 'images').mkdir(parents=True)
        (deck / 'outline.json').write_text(json.dumps({
            'pages': [
                {'page_no': 1, 'page_kind': 'cover', 'title': '年度总结'},
                {'page_no': 2, 'page_kind': 'content', 'title': '关键进展'},
            ],
        }, ensure_ascii=False), encoding='utf-8')
        (deck / 'style_spec.json').write_text(json.dumps({
            'design_style': {'name_zh': '科技感'},
            'primary_color': '#126BFF',
        }, ensure_ascii=False), encoding='utf-8')
        return deck

    def test_generates_and_publishes_one_background_per_outline_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deck = self._deck(root)
            generated = []
            for page in (1, 2):
                path = root / f'generated_{page}.png'
                path.write_bytes(f'image-{page}'.encode())
                generated.append(path)

            calls = []

            def fake_image_generator(**kwargs):
                calls.append(kwargs)
                return {'local_path': str(generated[len(calls) - 1])}

            with mock.patch.object(
                TOOLS, '_resolve_deck_dir', return_value=deck,
            ), mock.patch.object(
                TOOLS, 'image_generator', side_effect=fake_image_generator,
            ), mock.patch.object(
                TOOLS, '_save_artifact', return_value={'stored': True},
            ) as save:
                result = TOOLS.ppt_generate_background_images(str(deck))

            self.assertEqual(result['count'], 2)
            self.assertEqual(result['published_count'], 2)
            self.assertEqual(len(calls), 2)
            self.assertIn('No words, no letters, no numbers', calls[0]['prompt'])
            self.assertIn('年度总结', calls[0]['prompt'])
            self.assertIn('关键进展', calls[1]['prompt'])
            self.assertTrue((deck / 'images/page_001_background.png').is_file())
            self.assertTrue((deck / 'images/page_002_background.png').is_file())
            manifest = json.loads(
                (deck / 'background_images.json').read_text(encoding='utf-8'),
            )
            self.assertTrue(manifest['enabled'])
            self.assertEqual([item['page_no'] for item in manifest['pages']], [1, 2])
            self.assertEqual(save.call_count, 2)
            self.assertEqual(save.call_args_list[0].kwargs['key'], 'background_images')

    def test_surfaces_image_model_failure_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            deck = self._deck(Path(temp))
            with mock.patch.object(
                TOOLS, '_resolve_deck_dir', return_value=deck,
            ), mock.patch.object(
                TOOLS,
                'image_generator',
                return_value={
                    'success': False,
                    'error': {'reason': 'image_generator model is not configured'},
                },
            ):
                with self.assertRaisesRegex(
                    ToolExecutionError,
                    'page 1 background generation failed: image_generator model is not configured',
                ):
                    TOOLS.ppt_generate_background_images(str(deck))


class PptCapabilityCheckTest(unittest.TestCase):
    def test_disabled_backgrounds_skip_image_model_check(self) -> None:
        with mock.patch.object(
            TOOLS,
            'is_model_role_available',
            side_effect=AssertionError('disabled backgrounds must not inspect models'),
        ):
            result = TOOLS.check_ppt_workflow_capabilities(
                'AI_BACKGROUND_IMAGES: disabled',
            )

        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['required'], [])
        self.assertEqual(result['checks'], [])

    def test_enabled_backgrounds_return_settings_card_when_model_is_missing(self) -> None:
        with mock.patch.object(
            TOOLS, 'is_model_role_available', return_value=False,
        ), self.assertRaisesRegex(
            ToolExecutionError, 'MEDIA_CAPABILITY_DEPENDENCY_MISSING',
        ) as captured:
            TOOLS.check_ppt_workflow_capabilities(
                'AI_BACKGROUND_IMAGES: enabled',
            )

        message = str(captured.exception)
        self.assertIn('image_generator', message)
        self.assertIn('/settings?section=models', message)
        self.assertIn('尚未配置可用的文生图模型', message)


if __name__ == '__main__':
    unittest.main()
