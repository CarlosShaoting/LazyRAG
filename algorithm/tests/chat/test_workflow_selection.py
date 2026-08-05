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


def test_mentioned_workflow_is_injected_as_authoritative_selection():
    catalog = [{
        'workflow_ref': 'builtin:image-plugin',
        'workflow_id': 'image-plugin',
        'revision_id': 'revision-1',
        'name': 'AI image generation',
    }]
    contribution = resolve_workflow_injection(
        None,
        workflow_catalog=catalog,
        allowed_workflow_refs=['builtin:image-plugin'],
        workflow_activations=[{
            'workflow_ref': 'builtin:image-plugin',
            'workflow_id': 'image-plugin',
            'revision_id': 'revision-1',
            'tool_name': 'trigger_image_plugin_workflow',
            'tool_description': "Load the exact 'AI image generation' Workflow",
            'prompt': 'Call the bound trigger; do not call list_workflows.',
        }],
    )

    assert 'Explicit Workflow Selection [AUTHORITATIVE]' in contribution.runtime_context
    assert 'builtin:image-plugin' in contribution.runtime_context
    assert 'revision-1' in contribution.runtime_context
    assert _tool(contribution, 'trigger_image_plugin_workflow').__doc__.startswith(
        "Load the exact 'AI image generation' Workflow"
    )
    assert list(inspect.signature(
        _tool(contribution, 'trigger_image_plugin_workflow'),
    ).parameters) == ['request_context']
    with pytest.raises(WorkflowClientError) as error:
        _tool(contribution, 'prepare_workflow')('writer-plugin')
    assert error.value.code == 'WORKFLOW_NOT_SELECTED'


def test_dynamic_trigger_loads_pinned_remote_package_without_listing():
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory:
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-plugin', 'revision_id': 'revision-1',
        }
        contribution = resolve_workflow_injection(
            None,
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-plugin',
                'workflow_id': 'image-plugin',
                'revision_id': 'revision-1',
                'name': 'AI image generation',
            }],
            allowed_workflow_refs=['builtin:image-plugin'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-plugin',
                'workflow_id': 'image-plugin',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_image_plugin_workflow',
                'tool_description': 'Load selected workflow',
                'prompt': 'Call the bound trigger; do not call list_workflows.',
            }],
        )

        result = _tool(contribution, 'trigger_image_plugin_workflow')('draw a fox')

    client_factory.return_value.list_workflows.assert_not_called()
    client_factory.return_value.get_workflow.assert_called_once_with(
        'image-plugin', 'revision-1',
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
