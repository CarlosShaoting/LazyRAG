from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lazymind.chat.workflow.client import (
    AdvanceRequest, StepCommand, WorkflowClient, WorkflowClientError,
    sanitize_attempt_context,
)
from lazymind.chat.workflow.file_adapter import LazyMindHostFileAdapter


def response(status, body):
    value = MagicMock(status_code=status)
    value.json.return_value = body
    return value


def test_advance_uses_typed_facade_payload_without_retry():
    transport = MagicMock()
    transport.post.return_value = response(200, {
        'ok': True, 'request_id': 'r1', 'result': {'accepted': True},
    })
    client = WorkflowClient('http://core/api/core', 'u1', transport=transport)
    result = client.advance(AdvanceRequest(
        session_id='ws1', expected_state_version=2,
        steps=[StepCommand(step_id='draft', user_input='write')], command_id='cmd1',
    ))
    assert result.result['accepted'] is True
    call = transport.post.call_args
    assert call.args[0].endswith('/workflow-sessions/ws1:advance-step')
    assert call.kwargs['json']['contract_version'] == 'workflow.v1'
    assert call.kwargs['json']['steps'][0]['step_id'] == 'draft'


def test_structured_error_mapping():
    transport = MagicMock()
    transport.post.return_value = response(409, {'ok': False, 'error': {
        'code': 'STATE_VERSION_CONFLICT', 'message': 'stale', 'retryable': False,
        'details': {'actual': 3},
    }})
    with pytest.raises(WorkflowClientError) as caught:
        WorkflowClient('http://core', transport=transport).advance(AdvanceRequest(
            session_id='ws1', expected_state_version=2,
            steps=[StepCommand(step_id='draft')],
        ))
    assert caught.value.code == 'STATE_VERSION_CONFLICT'
    assert caught.value.details == {'actual': 3}
    assert transport.post.call_count == 1


def test_host_file_adapter_returns_only_stable_resource_fields(tmp_path: Path):
    source = tmp_path / 'requirements.txt'
    source.write_text('stable input')
    transport = MagicMock()
    transport.post.return_value = response(200, {'ok': True, 'result': {
        'resource_id': 'res1', 'name': source.name, 'mime_type': 'text/plain',
        'size': 12, 'content_hash': 'sha256:abc', 'revision': 1,
    }})
    resource = LazyMindHostFileAdapter('http://core', 'u1', transport=transport).import_attachment(str(source))
    assert resource.resource_id == 'res1'
    assert not hasattr(resource, 'path')
    assert not hasattr(resource, 'url')
    assert str(tmp_path) not in repr(resource)


@pytest.mark.parametrize('private', [
    {'llm_config': {'model': 'private'}},
    {'inputs': [{'local_path': '/tmp/private.pdf'}]},
    {'inputs': [{'temporary_url': 'https://host.invalid/signed'}]},
    {'token': 'secret'},
])
def test_attempt_context_rejects_host_private_fields(private):
    with pytest.raises(WorkflowClientError) as caught:
        sanitize_attempt_context({'contract_version': 'workflow.v1', **private})
    assert caught.value.code == 'ATTEMPT_CONTEXT_PRIVATE_DATA'


def test_attempt_context_accepts_stable_input_binding():
    context = sanitize_attempt_context({'inputs': [{
        'material_id': 'requirements', 'resource_id': 'res1', 'revision': 1,
        'content_hash': 'sha256:abc', 'read_capability': 'capability-id',
    }]})
    assert context['inputs'][0]['resource_id'] == 'res1'
