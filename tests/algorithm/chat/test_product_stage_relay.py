from unittest.mock import MagicMock

import pytest

from lazymind.chat.workflow import workflow_manager
from lazymind.workflow_sdk import WorkflowClient, WorkflowClientError


def test_sdk_relay_keeps_authorization_and_idempotency_explicit():
    transport = MagicMock()
    transport.post.return_value.status_code = 200
    transport.post.return_value.json.return_value = {'ok': True, 'result': {'session_id': 'next'}}
    client = WorkflowClient('http://localhost/api/core', 'owner', transport=transport)
    result = client.relay_product_stage(
        'source', action='continue', selected_stage='prototype', expected_state_version=12,
        command_id='stable-key', request_context='继续原型', user_message='继续原型',
    )
    assert result == {'session_id': 'next'}
    request = transport.post.call_args
    assert request.args[0].endswith('/workflow-sessions/source/product-stage-relay')
    assert request.kwargs['headers']['X-User-Id'] == 'owner'
    assert request.kwargs['headers']['Idempotency-Key'] == 'stable-key'
    assert request.kwargs['json']['user_message'] == '继续原型'
    assert request.kwargs['json']['expected_state_version'] == 12


def test_chat_relay_binds_successor_and_replays_original_version_after_timeout(monkeypatch):
    cfg = {'query': '继续做交互原型', 'workflow_session_id': 'source'}
    client = MagicMock()
    client.get_product_stage_relay.return_value = {'can_relay': True, 'state_version': 8}
    client.relay_product_stage.side_effect = [
        WorkflowClientError('WORKFLOW_TIMEOUT', 'unknown outcome'),
        {'session_id': 'next', 'source_session_id': 'source', 'ready_steps': ['route_product_stage']},
    ]
    monkeypatch.setattr(workflow_manager, '_agentic_config', lambda: cfg)
    monkeypatch.setattr(workflow_manager, '_client', lambda: client)
    tools = {tool.__name__: tool for tool in workflow_manager._safe_session_tools(MagicMock(), 'source')}
    with pytest.raises(WorkflowClientError):
        tools['relay_product_stage']('continue', 'prototype')
    result = tools['relay_product_stage']('continue', 'prototype')
    calls = client.relay_product_stage.call_args_list
    assert calls[0] == calls[1]
    assert client.get_product_stage_relay.call_count == 1
    assert result['session_id'] == 'next'
    assert cfg['workflow_session_id'] == 'next'
    assert workflow_manager._relayed_session_id('source') == 'next'
    assert workflow_manager._relayed_session_id('unrelated') == 'unrelated'


def test_chat_relay_requires_current_user_message(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(workflow_manager, '_agentic_config', lambda: {})
    monkeypatch.setattr(workflow_manager, '_client', lambda: client)
    tools = {tool.__name__: tool for tool in workflow_manager._safe_session_tools(MagicMock(), 'source')}
    with pytest.raises(WorkflowClientError, match='current user message'):
        tools['relay_product_stage']('continue', 'design')
    client.relay_product_stage.assert_not_called()


def test_sdk_shared_view_is_authorized_read_only():
    transport = MagicMock()
    transport.get.return_value.status_code = 200
    transport.get.return_value.json.return_value = {
        'ok': True, 'result': {'stage': 'design', 'content': '# Same project design'},
    }
    client = WorkflowClient('http://localhost/api/core', 'owner', transport=transport)
    result = client.get_product_project_artifact('source', 'design')
    request = transport.get.call_args
    assert request.args[0].endswith('/workflow-sessions/source/product-artifacts/design')
    assert request.kwargs['headers']['X-User-Id'] == 'owner'
    assert result['stage'] == 'design'
    transport.post.assert_not_called()


def test_chat_reads_shared_view_using_current_successor_without_relay(monkeypatch):
    client = MagicMock()
    cfg = {'workflow_session_id': 'next', 'product_stage_relay': {
        'source_session_id': 'source', 'session_id': 'next',
    }}
    monkeypatch.setattr(workflow_manager, '_agentic_config', lambda: cfg)
    monkeypatch.setattr(workflow_manager, '_client', lambda: client)
    tools = {tool.__name__: tool for tool in workflow_manager._safe_session_tools(MagicMock(), 'source')}
    tools['read_product_project_artifact']('design')
    client.get_product_project_artifact.assert_called_once_with('next', 'design')
    client.relay_product_stage.assert_not_called()
