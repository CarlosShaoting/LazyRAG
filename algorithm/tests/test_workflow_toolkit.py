from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lazymind.workflow_toolkit import HostWorkflowToolkit, WORKFLOW_SKILL_NAME, workflow_skills_dir
from lazymind.workflow_sdk import WorkflowClientError


def test_common_toolkit_exposes_complete_skill_capabilities():
    names = {tool.__name__ for tool in HostWorkflowToolkit(MagicMock()).tools()}
    assert {
        'workflow_connection_status', 'list_workflows', 'get_workflow', 'list_skills',
        'get_skill_conversion_context', 'create_workflow_draft',
        'validate_workflow_draft', 'publish_workflow',
        'prepare_workflow', 'start_workflow', 'get_workflow_state',
        'get_ready_steps', 'advance_step', 'stop_workflow', 'resume_workflow',
        'import_input_resource', 'read_input_resource', 'bind_workflow_input',
        'list_artifacts', 'read_artifact', 'patch_artifact', 'delete_artifact',
    } <= names


def test_advance_step_exposes_strict_step_command_schema_and_accepts_it():
    from lazyllm.tools.agent import ToolManager
    from lazymind.workflow_toolkit import StepCommandInput

    client = MagicMock()
    client.advance.return_value.result = {'accepted': True}
    toolkit = HostWorkflowToolkit(lambda: client)
    manager = ToolManager([toolkit.advance_step])
    schema = manager.tools_description[0]['function']['parameters']
    step_schema = schema['$defs']['StepCommandInput']
    assert set(step_schema['properties']) == {
        'step_id', 'task_id', 'objective', 'user_input',
        'runtime_instruction', 'partial_indices',
    }
    assert step_schema['additionalProperties'] is False
    assert step_schema['required'] == ['step_id']

    toolkit.advance_step('session-1', 1, [StepCommandInput(step_id='prompt')], 'command-1')
    request = client.advance.call_args.args[0]
    assert request.command_id == 'command-1'
    assert request.steps[0].step_id == 'prompt'


def test_prepare_workflow_binds_host_origin_reference():
    client = MagicMock()
    client.prepare_workflow.return_value.result = {'status': 'ready'}
    toolkit = HostWorkflowToolkit(lambda: client, origin_ref='conversation-1')
    assert toolkit.prepare_workflow('writer') == {'status': 'ready'}
    assert client.prepare_workflow.call_args.kwargs['fields'] == {
        'origin_ref': 'conversation-1',
    }


def test_common_toolkit_contains_no_model_dependency():
    source = (Path(__file__).parents[1] / 'lazymind/workflow_toolkit.py').read_text()
    assert 'AutoModel' not in source
    assert 'lazyllm' not in source
    assert 'llm_config' not in source


def test_explicit_workflow_selection_filters_discovery_and_guards_reads_and_prepare():
    client = MagicMock()
    client.list_workflows.return_value.result = {'workflows': [
        {'workflow_id': 'selected', 'workflow_ref': 'builtin:selected'},
        {'workflow_id': 'other', 'workflow_ref': 'builtin:other'},
    ]}
    toolkit = HostWorkflowToolkit(lambda: client, allowed_workflow_ids=['selected'])

    assert toolkit.list_workflows() == {'workflows': [
        {'workflow_id': 'selected', 'workflow_ref': 'builtin:selected'},
    ]}
    with pytest.raises(WorkflowClientError, match='not selected') as read_error:
        toolkit.get_workflow('other')
    assert read_error.value.code == 'WORKFLOW_NOT_SELECTED'
    with pytest.raises(WorkflowClientError, match='not selected'):
        toolkit.prepare_workflow('other')
    client.get_workflow.assert_not_called()
    client.prepare_workflow.assert_not_called()


def test_shared_skill_is_discoverable_by_in_process_hosts():
    root = Path(workflow_skills_dir())
    assert (root / WORKFLOW_SKILL_NAME / 'SKILL.md').is_file()


def test_lazyllm_skill_manager_discovers_shared_workflow_skill():
    from lazyllm.tools.agent.skill_manager import SkillManager
    prompt = SkillManager(
        dir=workflow_skills_dir(), skills=[WORKFLOW_SKILL_NAME],
    ).build_prompt()
    assert 'workflow-agent-kit:' in prompt
    assert 'Skill-to-Workflow conversion' in prompt
