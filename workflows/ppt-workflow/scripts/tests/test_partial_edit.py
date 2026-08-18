import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS_PATH = Path(__file__).resolve().parents[1] / 'tools.py'
SPEC = importlib.util.spec_from_file_location('ppt_workflow_tools_partial_edit_test', TOOLS_PATH)
TOOLS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TOOLS)


PAGE_HTML = """<!DOCTYPE html>
<html><head><title>Old title</title></head><body>
<div class="wrapper"><div id="bg"></div><div id="ct">
  <h1 data-el="title">Old title</h1>
  <div data-el="bullet-1"><span>repeat</span><b>repeat</b></div>
</div></div></body></html>
"""


def make_deck(root: Path) -> tuple[Path, Path]:
    deck = root / 'deck'
    pages = deck / 'pages'
    pages.mkdir(parents=True)
    (deck / 'task_pack.json').write_text('{}', encoding='utf-8')
    (deck / 'info_pack.json').write_text('{}', encoding='utf-8')
    (deck / 'outline.json').write_text(json.dumps({
        'pages': [{
            'page_no': 1,
            'title': 'Old title',
            'bullets': [{'head': 'repeat', 'detail': 'detail'}],
        }],
    }), encoding='utf-8')
    page = pages / 'page_001.html'
    page.write_text(PAGE_HTML, encoding='utf-8')
    return deck, page


class PartialEditTests(unittest.TestCase):
    def test_replacement_is_html_escaped_and_title_stays_in_sync(self):
        edited, _applied, _notes, removed = TOOLS._apply_html_ops(PAGE_HTML, [{
            'op': 'replace_text',
            'el': 'title',
            'value': 'A < B & C',
        }])
        TOOLS._validate_local_html_edit(PAGE_HTML, edited)
        self.assertIn('<h1 data-el="title">A &lt; B &amp; C</h1>', edited)
        self.assertIn('<title>A &lt; B &amp; C</title>', edited)
        self.assertNotIn('<h1 data-el="title">A < B & C</h1>', edited)
        self.assertIn('Old title', removed)

    def test_nested_ambiguous_match_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'contains 2 visible matches'):
            TOOLS._apply_html_ops(PAGE_HTML, [{
                'op': 'replace_text',
                'el': 'bullet-1',
                'match': 'repeat',
                'value': 'new',
            }])

    def test_read_hash_guards_against_stale_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck, page = make_deck(Path(tmp))
            read = TOOLS.ppt_read_page_html(str(deck), 1)
            current_hash = read['result']['html_sha256']
            self.assertEqual(current_hash, TOOLS._html_sha256(PAGE_HTML))

            result = TOOLS.ppt_edit_page_html(
                str(deck), 1,
                [{'op': 'replace_text', 'el': 'title', 'value': 'new'}],
                expected_sha256='0' * 64,
            )
            self.assertFalse(result['success'])
            self.assertEqual(page.read_text(encoding='utf-8'), PAGE_HTML)

    def test_edit_requires_hash_from_immediately_preceding_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck, page = make_deck(Path(tmp))
            result = TOOLS.ppt_edit_page_html(
                str(deck), 1,
                [{'op': 'replace_text', 'el': 'title', 'value': 'new'}],
            )
            self.assertFalse(result['success'])
            self.assertIn('expected_sha256 is required', result['error']['reason'])
            self.assertEqual(page.read_text(encoding='utf-8'), PAGE_HTML)

    def test_failed_publish_rolls_the_page_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck, page = make_deck(Path(tmp))
            failed_publish = {
                'published_count': 0,
                'failed': [{'page': 1, 'error': 'simulated'}],
            }
            with mock.patch.object(
                TOOLS, '_publish_pages_from_disk', return_value=failed_publish,
            ) as publish:
                result = TOOLS.ppt_edit_page_html(
                    str(deck), 1,
                    [{'op': 'replace_text', 'el': 'title', 'value': 'new'}],
                    expected_sha256=TOOLS._html_sha256(PAGE_HTML),
                )
            self.assertFalse(result['success'])
            self.assertEqual(page.read_text(encoding='utf-8'), PAGE_HTML)
            self.assertEqual(publish.call_count, 2)

    def test_page_publisher_propagates_artifact_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck, _page = make_deck(Path(tmp))
            with mock.patch.object(
                TOOLS,
                '_save_artifact',
                return_value={'success': False, 'error': {'reason': 'simulated'}},
            ):
                result = TOOLS._publish_one_page(deck, 1)
            self.assertFalse(result['ok'])
            self.assertIn('preview_html publish failed', result['error'])


if __name__ == '__main__':
    unittest.main()
