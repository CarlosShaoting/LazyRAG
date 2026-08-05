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
    )

    assert 'Explicit Workflow Selection [AUTHORITATIVE]' in contribution.runtime_context
    assert 'builtin:image-plugin' in contribution.runtime_context
    assert 'revision-1' in contribution.runtime_context
    with pytest.raises(WorkflowClientError) as error:
        _tool(contribution, 'prepare_workflow')('writer-plugin')
    assert error.value.code == 'WORKFLOW_NOT_SELECTED'


def test_enabled_workflow_without_mention_keeps_generic_discovery_tools():
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory:
        client_factory.return_value.get_workflow.return_value.result = {'workflow_id': 'any'}
        contribution = resolve_workflow_injection(None, workflow_catalog=[])

        assert contribution.runtime_context == ''
        assert _tool(contribution, 'get_workflow')('any') == {'workflow_id': 'any'}
