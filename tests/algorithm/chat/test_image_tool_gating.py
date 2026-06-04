import textwrap
from pathlib import Path

import pytest

from chat.components.agentic.config import (
    TOOL_MODEL_ROLE,
    _filter_tools_by_model_roles,
    get_default_tools,
)
from chat.utils.load_config import is_model_role_available, load_model_config


def write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / 'runtime_models.yaml'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


def test_tool_model_role_mapping():
    assert TOOL_MODEL_ROLE['image_generator'] == 'image_generator'
    assert TOOL_MODEL_ROLE['image_editor'] == 'image_editor'


def test_dynamic_image_tools_require_model_config(tmp_path, monkeypatch):
    config_path = write_yaml(tmp_path, """
        llm:
          source: dynamic
          type: llm
        image_generator:
          source: dynamic
          type: text2image
        image_editor:
          source: dynamic
          type: image_editing
    """)
    monkeypatch.setenv('LAZYMIND_MODEL_CONFIG_PATH', str(config_path))

    assert not is_model_role_available('image_generator')
    assert not is_model_role_available('image_editor')

    tools = get_default_tools({'model_config': {}})
    assert 'image_generator' not in tools
    assert 'image_editor' not in tools

    mc = {
        'image_generator': {'source': 'qwen', 'model': 'wanx', 'api_key': 'k1'},
        'image_editor': {'source': 'qwen', 'model': 'wanx-edit', 'api_key': 'k2'},
    }
    assert is_model_role_available('image_generator', request_model_config=mc)
    tools_with = get_default_tools({'model_config': mc})
    assert 'image_generator' in tools_with
    assert 'image_editor' in tools_with

    filtered = _filter_tools_by_model_roles(
        ['image_generator', 'kb_search'],
        {'model_config': {}},
    )
    assert filtered == ['kb_search']


def test_static_inner_roles_always_available(tmp_path, monkeypatch):
    config_path = write_yaml(tmp_path, """
        image_generator:
          - source: siliconflow
            type: text2image
            name: test-model
    """)
    monkeypatch.setenv('LAZYMIND_MODEL_CONFIG_PATH', str(config_path))
    assert is_model_role_available('image_generator')
    assert 'image_generator' in get_default_tools()
