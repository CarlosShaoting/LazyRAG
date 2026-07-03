from unittest.mock import patch

from lazymind.chat.plugin.kb_prefetch import (
    _format_kb_items,
    clear_plugin_kb_prefetch_cache,
    inject_plugin_kb_prefetch,
)


def test_format_kb_items_text_and_image():
    block = _format_kb_items([
        {'group': 'block', 'file_name': 'style.pdf', 'text': 'warm sunset palette'},
        {'group': 'image', 'file_name': 'ref.png', 'local_path': '/var/lib/lazymind/uploads/ref.png',
         'metadata': {'image_url': 'https://example.com/ref.png'}},
    ])
    assert 'Knowledge base prefetch' in block
    assert 'warm sunset palette' in block
    assert 'ref.png' in block
    assert 'Do NOT call kb_search' in block


def test_inject_plugin_kb_prefetch_skips_duplicate_header():
    existing = '## Knowledge base prefetch (authoritative)\nalready here'
    with patch('lazymind.chat.plugin.kb_prefetch.plugin_loader.kb_prefetch_enabled', return_value=True):
        assert inject_plugin_kb_prefetch(
            plugin_id='image-plugin',
            session_id='sess-1',
            query='q',
            filters={'kb_id': 'kb-1'},
            user_id='u1',
            runtime_instruction=existing,
        ) == existing


def test_inject_plugin_kb_prefetch_noop_without_flag():
    clear_plugin_kb_prefetch_cache()
    with patch('lazymind.chat.plugin.kb_prefetch.plugin_loader.kb_prefetch_enabled', return_value=False):
        assert inject_plugin_kb_prefetch(
            plugin_id='other-plugin',
            session_id='sess-2',
            query='q',
            filters={'kb_id': 'kb-1'},
            user_id='u1',
            runtime_instruction='base',
        ) == 'base'
