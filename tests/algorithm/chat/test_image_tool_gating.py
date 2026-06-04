import textwrap
from pathlib import Path

import pytest

from lazymind.chat.service.component.tool_registry import DEFAULT_TOOLS, filter_tools
from lazymind.model_config import is_model_role_available, load_model_config


def write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / 'runtime_models.yaml'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


def _active_tool_names() -> set[str]:
    return {cfg.name for cfg in filter_tools(DEFAULT_TOOLS)}


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

    names = _active_tool_names()
    assert 'image_generator' not in names
    assert 'image_editor' not in names

    mc = {
        'image_generator': {'source': 'qwen', 'model': 'wanx', 'api_key': 'k1'},
        'image_editor': {'source': 'qwen', 'model': 'wanx-edit', 'api_key': 'k2'},
    }
    import lazyllm
    from lazymind.model_config import inject_model_config

    inject_model_config(mc)
    names_with = {cfg.name for cfg in filter_tools(DEFAULT_TOOLS)}
    assert 'image_generator' in names_with
    assert 'image_editor' in names_with
    lazyllm.inject_model_config(None)


def test_static_inner_roles_always_available(tmp_path, monkeypatch):
    config_path = write_yaml(tmp_path, """
        image_generator:
          - source: siliconflow
            type: text2image
            name: test-model
    """)
    monkeypatch.setenv('LAZYMIND_MODEL_CONFIG_PATH', str(config_path))
    assert is_model_role_available('image_generator')
    assert 'image_generator' in _active_tool_names()


def test_runtime_models_declares_image_roles(tmp_path, monkeypatch):
    config_path = write_yaml(tmp_path, """
        image_generator:
          source: dynamic
          type: text2image
        image_editor:
          source: dynamic
          type: image_editing
    """)
    monkeypatch.setenv('LAZYMIND_MODEL_CONFIG_PATH', str(config_path))
    raw = load_model_config(str(config_path))
    assert raw['image_generator']['type'] == 'text2image'
    assert raw['image_editor']['type'] == 'image_editing'
