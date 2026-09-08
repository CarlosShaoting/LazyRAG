import base64
from pathlib import Path

import pytest
from lazyllm.tools.agent import ToolExecutionError

from lazymind.chat.engine.tools import browser_vision


def _png_header(width: int, height: int) -> bytes:
    return (
        b'\x89PNG\r\n\x1a\n'
        + b'\x00\x00\x00\x0dIHDR'
        + width.to_bytes(4, 'big')
        + height.to_bytes(4, 'big')
    )


def _screenshot_result(width: int = 1000, height: int = 500) -> str:
    encoded = base64.b64encode(_png_header(width, height)).decode()
    return (
        'Tool call result:\nReceived text message:\n'
        '{"result":{"session_id":"bs_1","mime_type":"image/png",'
        f'"data_base64":"{encoded}","viewport":{{"width":500,"height":250}}}}}}'
        '\n\n[Internal runtime notice] ignored'
    )


def test_browser_visual_locate_calls_vlm_and_scales_to_css_viewport(tmp_path, monkeypatch):
    observed = {}

    def screenshot_tool(**kwargs):
        observed['screenshot_args'] = kwargs
        return _screenshot_result()

    def fake_vision(path, instruction=None):
        observed['path'] = path
        observed['instruction'] = instruction
        assert Path(path).is_file()
        return {
            'description': (
                '```json\n'
                '{"found":true,"target":"blank editor","x":250,"y":100,'
                '"confidence":0.9,"reason":"placeholder"}\n```'
            )
        }

    monkeypatch.setattr(browser_vision, '_upload_root', lambda: str(tmp_path))
    monkeypatch.setattr(browser_vision, 'vision_extractor', fake_vision)
    locate = browser_vision.build_browser_visual_locate_tool(screenshot_tool)

    result = locate(session_id='bs_1', instruction='Locate the blank editor')

    assert observed['screenshot_args'] == {'session_id': 'bs_1'}
    assert 'untrusted page content' in observed['instruction']
    assert result['found'] is True
    assert result['x'] == 125
    assert result['y'] == 50
    assert result['image'] == {'width': 1000, 'height': 500}
    assert result['viewport'] == {'width': 500.0, 'height': 250.0}
    assert not Path(observed['path']).exists()


def test_browser_visual_locate_returns_not_found_without_coordinates(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_vision, '_upload_root', lambda: str(tmp_path))
    monkeypatch.setattr(
        browser_vision,
        'vision_extractor',
        lambda *_args, **_kwargs: {
            'description': '{"found":false,"target":"editor","reason":"not visible"}'
        },
    )
    locate = browser_vision.build_browser_visual_locate_tool(
        lambda **_kwargs: _screenshot_result()
    )

    result = locate(session_id='bs_1', instruction='editor')

    assert result['found'] is False
    assert 'x' not in result
    assert result['reason'] == 'not visible'


def test_browser_visual_locate_rejects_out_of_image_coordinates(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_vision, '_upload_root', lambda: str(tmp_path))
    monkeypatch.setattr(
        browser_vision,
        'vision_extractor',
        lambda *_args, **_kwargs: {
            'description': '{"found":true,"x":1000,"y":20,"confidence":1}'
        },
    )
    locate = browser_vision.build_browser_visual_locate_tool(
        lambda **_kwargs: _screenshot_result()
    )

    with pytest.raises(ToolExecutionError, match='outside screenshot'):
        locate(session_id='bs_1', instruction='editor')

