import lazyllm

from lazymind.chat.engine.subagent import tools


def test_find_user_attachment_accepts_remote_url_without_local_file():
    old_config = lazyllm.globals.get('agentic_config')
    try:
        lazyllm.globals['agentic_config'] = {
            'files': ['https://filecdn-images.xingyeai.com/tool/edit_images/image_0_bear.png'],
            'history_files_per_turn': {
                '1': ['https://filecdn-images.xingyeai.com/tool/edit_images/image_0_bear.png'],
            },
        }
        result = tools.find_user_attachment('image_0_bear.png', turn=1)
    finally:
        lazyllm.globals['agentic_config'] = old_config or {}

    assert result['success'] is True
    payload = result['result']
    assert payload['status'] == 'ok'
    assert payload['filename'] == 'image_0_bear.png'
    assert payload['url'] == 'https://filecdn-images.xingyeai.com/tool/edit_images/image_0_bear.png'
