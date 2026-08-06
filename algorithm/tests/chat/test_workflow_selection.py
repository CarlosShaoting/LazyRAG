import inspect
from unittest.mock import patch

import lazyllm
import pytest

from lazymind.chat.workflow.workflow_manager import resolve_workflow_injection
from lazymind.workflow_sdk import WorkflowClientError


@pytest.fixture(autouse=True)
def workflow_enabled():
    previous = lazyllm.globals.get('agentic_config')
    lazyllm.globals['agentic_config'] = {'enable_workflow': True}
    yield
    if previous is None:
        lazyllm.globals.pop('agentic_config', None)
    else:
        lazyllm.globals['agentic_config'] = previous


def _tool(contribution, name):
    return next(tool for tool in contribution.tools if tool.__name__ == name)


def _tool_names(contribution):
    return {tool.__name__ for tool in contribution.tools}


def test_mentioned_workflow_is_injected_as_authoritative_selection():
    catalog = [{
        'workflow_ref': 'builtin:image-workflow',
        'workflow_id': 'image-workflow',
        'revision_id': 'revision-1',
        'name': 'AI image generation',
    }]
    contribution = resolve_workflow_injection(
        None,
        workflow_catalog=catalog,
        allowed_workflow_refs=['builtin:image-workflow'],
        workflow_activations=[{
            'workflow_ref': 'builtin:image-workflow',
            'workflow_id': 'image-workflow',
            'revision_id': 'revision-1',
            'tool_name': 'trigger_image_workflow',
            'tool_description': "Load the exact 'AI image generation' Workflow",
            'prompt': 'Call the bound trigger; do not call list_workflows.',
        }],
    )

    assert 'Explicit Workflow Selection [AUTHORITATIVE]' in contribution.runtime_context
    assert 'builtin:image-workflow' in contribution.runtime_context
    assert 'revision-1' in contribution.runtime_context
    assert _tool(contribution, 'trigger_image_workflow').__doc__.startswith(
        "Load the exact 'AI image generation' Workflow"
    )
    assert list(inspect.signature(
        _tool(contribution, 'trigger_image_workflow'),
    ).parameters) == ['request_context']
    with pytest.raises(WorkflowClientError) as error:
        _tool(contribution, 'prepare_workflow')('writer-workflow')
    assert error.value.code == 'WORKFLOW_NOT_SELECTED'


def test_dynamic_trigger_loads_pinned_remote_package_without_listing():
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory:
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        contribution = resolve_workflow_injection(
            None,
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
                'name': 'AI image generation',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
                'tool_description': 'Load selected workflow',
                'prompt': 'Call the bound trigger; do not call list_workflows.',
            }],
        )

        result = _tool(contribution, 'trigger_image_workflow')('draw a fox')

    client_factory.return_value.list_workflows.assert_not_called()
    client_factory.return_value.get_workflow.assert_called_once_with(
        'image-workflow', 'revision-1',
    )
    assert result['status'] == 'loaded'
    assert result['request_context'] == 'draw a fox'
    assert result['workflow']['revision_id'] == 'revision-1'


def test_enabled_workflow_without_mention_keeps_generic_discovery_tools():
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory:
        client_factory.return_value.get_workflow.return_value.result = {'workflow_id': 'any'}
        contribution = resolve_workflow_injection(None, workflow_catalog=[])

        assert contribution.runtime_context == ''
        assert _tool(contribution, 'get_workflow')('any') == {'workflow_id': 'any'}


def test_model_tool_projection_hides_controller_lifecycle_tools_without_session():
    contribution = resolve_workflow_injection(None, workflow_catalog=[])

    names = _tool_names(contribution)
    assert 'prepare_workflow' in names
    assert 'start_workflow' not in names
    assert 'stop_workflow' not in names
    assert 'resume_workflow' not in names


@pytest.mark.parametrize(
    ('status', 'expects_resume'),
    [('active', False), ('waiting', False), ('failed', False),
     ('completed', False), ('stopped', True)],
)
def test_existing_session_hides_creation_and_only_stopped_session_exposes_resume(
        status, expects_resume):
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory:
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'status': status, 'state_version': 3,
        }
        contribution = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'image-workflow'},
            conversation_id='conversation-1',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
                'tool_description': 'Load selected workflow',
            }],
        )

    names = _tool_names(contribution)
    assert 'trigger_image_workflow' not in names
    assert 'prepare_workflow' not in names
    assert 'start_workflow' not in names
    assert 'stop_workflow' not in names
    assert ('resume_workflow' in names) is expects_resume
