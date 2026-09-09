from __future__ import annotations

import json

import pytest
from lazyllm.tools.agent import ToolExecutionError

from lazymind.chat.engine.tools import multimodal
from lazymind.chat.service.component import tool_registry


def test_explicit_image_request_keeps_unconfigured_tool_visible(monkeypatch):
    image_config = next(
        item for item in tool_registry.DEFAULT_TOOLS
        if item.name == 'image_generator'
    )
    monkeypatch.setattr(tool_registry, 'tool_is_active', lambda _config: False)

    assert tool_registry.filter_tools(
        [image_config],
        user_query='生成一张小狗的照片',
    ) == [image_config]
    assert tool_registry.filter_tools(
        [image_config],
        user_query='介绍一下小狗',
    ) == []
    assert tool_registry.filter_tools(
        [image_config],
        user_query='不要生成图片，只描述一下',
    ) == []


def test_unconfigured_image_tool_returns_structured_dependency(monkeypatch):
    monkeypatch.setattr(multimodal, 'is_model_role_available', lambda _role: False)

    with pytest.raises(ToolExecutionError) as captured:
        multimodal.image_generator('一只在草地上的小狗')

    message = str(captured.value)
    marker = 'MEDIA_CAPABILITY_DEPENDENCY_MISSING '
    assert marker in message
    payload = json.loads(message.split(marker, 1)[1])
    assert payload['workflow'] == 'DIRECT_CHAT'
    assert payload['missing'][0]['id'] == 'image_generator'
    assert payload['missing'][0]['settings_url'].endswith(
        'target=image_generator'
    )
