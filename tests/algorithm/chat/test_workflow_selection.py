import inspect
import json
from unittest.mock import MagicMock, patch

import lazyllm
import pytest

from lazymind.chat.workflow.workflow_manager import (
    _approve_image_v2_meme_brief,
    _advance_image_v2_to_declared_boundary,
    _image_v2_completion_text,
    _is_approval_only_continue,
    _with_terminal_agent_control,
    enforce_startup_clarification_policy,
    resolve_workflow_injection,
    workflow_startup_clarification_already_asked,
)
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
    pending = list(contribution.tools)
    while pending:
        tool = pending.pop(0)
        if isinstance(tool, dict):
            pending.extend(tool.get('tools') or [])
        elif tool.__name__ == name:
            return tool
    raise StopIteration(name)


def _tool_names(contribution):
    names = set()
    pending = list(contribution.tools)
    while pending:
        tool = pending.pop(0)
        if isinstance(tool, dict):
            names.add(str(tool.get('name') or ''))
            pending.extend(tool.get('tools') or [])
        else:
            names.add(tool.__name__)
    return names


def test_mentioned_workflow_is_injected_as_authoritative_selection():
    catalog = [{
        'workflow_ref': 'builtin:image-workflow',
        'workflow_id': 'image-workflow',
        'revision_id': 'revision-1',
        'name': 'AI image generation',
    }]
    contribution = resolve_workflow_injection(
        None,
        current_query='run it now',
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

    assert 'builtin:image-workflow' in contribution.runtime_context
    assert 'revision-1' in contribution.runtime_context
    assert '"current_query": "run it now"' in contribution.runtime_context
    assert list(inspect.signature(
        _tool(contribution, 'trigger_image_workflow'),
    ).parameters) == ['request_context']
    assert 'prepare_workflow' not in _tool_names(contribution)
    assert 'list_workflow_attachments' not in _tool_names(contribution)
    assert 'bind_workflow_input' not in _tool_names(contribution)


def test_image_workflow_v2_host_advances_to_declared_human_boundary():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-v2', 'state_version': 1, 'ready_steps': ['classify_request'],
    }
    toolkit.advance_step.side_effect = [
        {
            'status': 'active', 'state_version': 2,
            'projection': {
                'ready': ['meme_brief'],
                'nodes': {'meme_brief': {'mode': 'human', 'requires_approval': True}},
            },
        },
        {
            # A human node may also be the graph's final node. The Host must
            # still surface its review boundary before accepted completion.
            'status': 'completed', 'state_version': 3,
            'projection': {
                'completed': True, 'ready': [],
            },
        },
    ]
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-v2', 'state_version': 2,
        'ready_steps': ['ordinary_prepare', 'edit_prepare', 'meme_brief'],
        'approval_by_step': {
            'ordinary_prepare': 'not_required',
            'edit_prepare': 'not_required',
            'meme_brief': 'required',
        },
        'projection': {
            'nodes': {
                'ordinary_prepare': {'mode': 'auto', 'requires_approval': False},
                'edit_prepare': {'mode': 'auto', 'requires_approval': False},
                'meme_brief': {'mode': 'human', 'requires_approval': True},
            },
        },
    }
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'route-1', 'slot_id': 'route_plan', 'selected': True,
        'validity': 'effective', 'revision': 1,
        'value': {'data': {'route': 'meme'}},
    }]}
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow-v2', 'revision_id': 'revision-v2',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-v2', 'state_version': 1,
            'projection': {
                'reachable': ['classify_request'], 'ready': ['classify_request'], 'blocked': [],
            },
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='生成一个蓝色圆形图标',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow-v2',
                'workflow_id': 'image-workflow-v2',
                'revision_id': 'revision-v2',
            }],
            allowed_workflow_refs=['builtin:image-workflow-v2'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow-v2',
                'workflow_id': 'image-workflow-v2',
                'revision_id': 'revision-v2',
                'tool_name': 'trigger_image_workflow_v2_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_image_workflow_v2_workflow')()

    toolkit.prepare_workflow.assert_called_once_with(
        'image-workflow-v2', input_bindings={}, request_context='生成一个蓝色圆形图标',
        workflow_mode='dynamic',
    )
    assert [
        call.args[2][0].step_id for call in toolkit.advance_step.call_args_list
    ] == ['classify_request', 'meme_brief']
    assert all(
        call.kwargs['workflow_mode'] == 'dynamic'
        for call in toolkit.advance_step.call_args_list
    )
    assert result['status'] == 'waiting'
    assert result['outcome'] == 'approval_required'
    assert result['approval_step'] == 'meme_brief'
    assert result['host_executed_steps'] == ['classify_request', 'meme_brief']
    assert result['_agent_control']['stop'] is True


def test_image_workflow_v2_host_refreshes_once_when_auto_advance_conflicts():
    toolkit = MagicMock()
    toolkit.advance_step.side_effect = [
        WorkflowClientError('STATE_VERSION_CONFLICT', 'stale'),
        {
            'status': 'completed', 'state_version': 3,
            'projection': {'completed': True, 'ready': []},
        },
    ]
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-v2', 'state_version': 2,
        'ready_steps': ['ordinary_generate'],
        'projection': {
            'nodes': {
                'ordinary_generate': {'mode': 'auto', 'requires_approval': False},
            },
        },
    }

    result = _advance_image_v2_to_declared_boundary(
        toolkit,
        'session-v2',
        {
            'session_id': 'session-v2', 'state_version': 1,
            'ready_steps': ['ordinary_generate'],
            'projection': {
                'nodes': {
                    'ordinary_generate': {'mode': 'auto', 'requires_approval': False},
                },
            },
        },
        'ordinary_generate',
        user_input='生成蓝色圆形图标',
    )

    assert [call.args[1] for call in toolkit.advance_step.call_args_list] == [1, 2]
    assert result['status'] == 'completed'
    assert result['host_executed_steps'] == ['ordinary_generate']
    assert result['state_version_refreshed'] is True


@pytest.mark.parametrize(
    ('status', 'outcome'),
    [
        ('failed', 'step_failed'),
        ('cancelled', 'cancelled'),
        ('interrupted', 'interrupted'),
    ],
)
def test_image_workflow_v2_human_step_preserves_terminal_failure(status, outcome):
    toolkit = MagicMock()
    toolkit.advance_step.return_value = {
        'status': status,
        'outcome': outcome,
        'error': {'message': 'simulated media failure'},
    }
    frontier = {
        'session_id': 'session-v2',
        'state_version': 1,
        'ready_steps': ['render_keyframes'],
        'projection': {
            'nodes': {
                'render_keyframes': {'mode': 'human', 'requires_approval': True},
            },
        },
    }

    with patch(
        'lazymind.chat.workflow.workflow_manager._image_v2_completion_text',
        return_value='',
    ):
        result = _advance_image_v2_to_declared_boundary(
            toolkit,
            'session-v2',
            frontier,
            'render_keyframes',
            user_input='',
        )

    assert result['status'] == status
    assert result['outcome'] == outcome
    assert result['error']['message'] == 'simulated media failure'
    assert 'approval_step' not in result
    assert result.get('_agent_control', {}).get('reason') != 'approval_required'


def test_image_workflow_v2_continue_approves_pending_meme_brief_atomically():
    toolkit = MagicMock()
    pending = {
        'delivery_mode': 'static',
        'caption_mode': 'caption',
        'caption_source': 'proposed',
        'caption_review_status': 'pending',
        'requested_count': 2,
        'planned_count': 2,
        'count_status': 'compliant',
        'allowed_count': 12,
        'requires_count_decision': False,
        'brief_status': 'blocked',
        'states': [
            {'state_id': 'hello', 'caption': '你好呀', 'caption_review_status': 'pending'},
            {'state_id': 'thanks', 'caption': '谢谢你', 'caption_review_status': 'pending'},
        ],
    }
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'brief-1', 'slot_id': 'meme_brief_data', 'selected': True,
        'validity': 'effective', 'revision': 4, 'draft_version': 7,
        'content_type': 'json',
        'value': {'data': pending},
    }]}

    assert _approve_image_v2_meme_brief(
        toolkit, 'session-v2', ['meme_preflight'], '继续执行',
    ) is True

    args = toolkit.patch_artifact.call_args.args
    assert args[:2] == ('brief-1', 4)
    assert toolkit.patch_artifact.call_args.kwargs['base_draft_version'] == 7
    approved = args[2]
    assert approved['caption_review_status'] == 'approved'
    assert approved['brief_status'] == 'approved'
    assert [state['caption_review_status'] for state in approved['states']] == [
        'approved', 'approved',
    ]
    assert [state['caption'] for state in approved['states']] == ['你好呀', '谢谢你']
    assert pending['caption_review_status'] == 'pending'
    assert pending['states'][0]['caption_review_status'] == 'pending'


def test_image_workflow_v2_accepts_descriptive_approval_but_not_revision_text():
    assert _is_approval_only_continue('批准当前方案和全部字幕，继续执行。')
    assert _is_approval_only_continue('这些都通过，请继续')
    assert not _is_approval_only_continue('继续，但请修改第二张图片')
    assert not _is_approval_only_continue('不同意，重新调整方案')


@pytest.mark.parametrize(
    'user_input',
    [
        '先别继续',
        '还没确认',
        '先解释一下再继续',
        'do not continue',
        '继续，但把数量减到2张',
    ],
)
def test_image_workflow_v2_negative_or_conditional_text_does_not_approve(user_input):
    toolkit = MagicMock()

    assert _approve_image_v2_meme_brief(
        toolkit,
        'session-v2',
        ['meme_preflight'],
        user_input,
    ) is False
    toolkit.list_artifacts.assert_not_called()
    toolkit.patch_artifact.assert_not_called()


def test_image_workflow_v2_continue_does_not_approve_unresolved_count_decision():
    toolkit = MagicMock()
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'brief-1', 'slot': 'meme_brief_data', 'selected': True,
        'revision': 1, 'content_type': 'json',
        'value': {'data': {
            'caption_mode': 'caption',
            'caption_review_status': 'pending',
            'brief_status': 'blocked',
            'requested_count': 13,
            'planned_count': 12,
            'allowed_count': 12,
            'count_status': 'over_limit',
            'requires_count_decision': True,
            'states': [
                {'state_id': str(index), 'caption': f'文案{index}'}
                for index in range(13)
            ],
        }},
    }]}

    with pytest.raises(WorkflowClientError) as exc_info:
        _approve_image_v2_meme_brief(
            toolkit, 'session-v2', ['meme_preflight'], '继续',
        )

    assert exc_info.value.code == 'MEME_BRIEF_NOT_APPROVABLE'
    toolkit.patch_artifact.assert_not_called()


def test_image_workflow_v2_continue_redirects_stale_brief_rerun_to_preflight():
    toolkit = MagicMock()
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'brief-1', 'slot_id': 'meme_brief_data', 'selected': True,
        'revision': 2, 'draft_version': 3, 'content_type': 'json',
        'value': {'data': {
            'caption_mode': 'caption',
            'caption_review_status': 'pending',
            'brief_status': 'blocked',
            'requested_count': 1,
            'planned_count': 1,
            'allowed_count': 12,
            'count_status': 'compliant',
            'requires_count_decision': False,
            'states': [{
                'state_id': 'hello', 'caption': '你好呀',
                'caption_review_status': 'pending',
            }],
        }},
    }]}
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-v2', 'state_version': 11,
        'ready_steps': ['meme_preflight'], 'retryable_steps': [],
        'rewindable_steps': [], 'continue_steps': [],
        'projection': {
            'nodes': {
                'meme_preflight': {'mode': 'auto', 'requires_approval': False},
            },
        },
    }
    toolkit.advance_step.return_value = {
        'status': 'failed', 'state_version': 12,
        'projection': {'completed': False, 'ready': []},
    }
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'waiting', 'state_version': 10,
            'projection': {'ready': [], 'blocked': ['meme_preflight']},
        }
        contribution = resolve_workflow_injection(
            {
                'session_id': 'session-v2',
                'workflow_id': 'image-workflow-v2',
                'workflow_ref': 'builtin:image-workflow-v2',
            },
            current_query='继续',
            conversation_id='conversation-1',
        )
        lazyllm.globals['agentic_config'].update(contribution.agentic_config_patch)
        result = _tool(contribution, 'advance_step')(['meme_brief'])

    toolkit.patch_artifact.assert_called_once()
    command = toolkit.advance_step.call_args.args[2][0]
    assert command.step_id == 'meme_preflight'
    assert result['host_executed_steps'] == ['meme_preflight']


def test_image_workflow_v2_handoff_continue_approves_and_launches_preflight():
    toolkit = MagicMock()
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'brief-1', 'slot_id': 'meme_brief_data', 'selected': True,
        'revision': 5, 'draft_version': 8, 'content_type': 'json',
        'value': {'data': {
            'caption_mode': 'caption',
            'caption_review_status': 'pending',
            'brief_status': 'blocked',
            'requested_count': 1,
            'planned_count': 1,
            'allowed_count': 12,
            'count_status': 'compliant',
            'requires_count_decision': False,
            'states': [{
                'state_id': 'hello', 'caption': '你好呀',
                'caption_review_status': 'pending',
            }],
        }},
    }]}
    frontier = {
        'session_id': 'session-v2', 'state_version': 21,
        'ready_steps': ['meme_preflight'], 'retryable_steps': [],
        'rewindable_steps': [], 'continue_steps': [],
    }
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client = client_factory.return_value
        client.get_state.return_value = {
            'status': 'waiting', 'state_version': 20,
            'projection': {'ready': [], 'blocked': ['meme_preflight']},
        }
        client.get_ready_steps.return_value = frontier
        client.advance.return_value.result = {
            'status': 'active', 'state_version': 22,
            'host_executed_steps': ['meme_preflight'],
        }
        contribution = resolve_workflow_injection(
            {
                'session_id': 'session-v2',
                'workflow_id': 'image-workflow-v2',
                'workflow_ref': 'builtin:image-workflow-v2',
            },
            current_query='继续执行',
            conversation_id='conversation-1',
        )
        lazyllm.globals['agentic_config'].update(contribution.agentic_config_patch)
        result = json.loads(
            _tool(contribution, 'advance_step_and_hand_off')('meme_brief'),
        )

    assert result['host_executed_steps'] == ['meme_preflight']
    toolkit.patch_artifact.assert_called_once()
    assert toolkit.patch_artifact.call_args.kwargs['base_draft_version'] == 8
    request = client.advance.call_args.args[0]
    assert request.steps[0].step_id == 'meme_preflight'
    assert request.steps[0].user_input == '继续执行'
    assert request.handoff is True


def test_image_workflow_v2_auto_binds_the_sole_current_turn_image():
    old_image = '/safe/older.png'
    current_image = '/safe/current.jpg'
    lazyllm.globals['agentic_config'].update({
        'files': [old_image, current_image],
        'history_files_per_turn': {'1': [old_image], '3': [current_image]},
        'current_turn_seq': 3,
    })
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-v2', 'state_version': 1, 'ready_steps': [],
    }
    imported = {
        'resource_id': 'source-resource', 'revision': 1,
        'content_hash': 'sha256:source',
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ), patch(
        'lazymind.chat.workflow.workflow_manager._resolve_workflow_attachment',
        return_value=(current_image, None),
    ) as resolve_attachment, patch(
        'lazymind.chat.workflow.workflow_manager._import_attachment', return_value=imported,
    ) as import_attachment:
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow-v2', 'revision_id': 'revision-v2',
            'compiled_graph': {
                'material_types': {'source_image': 'image'},
                'material_producers': {'source_image': {'kind': 'external'}},
            },
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-v2', 'state_version': 1,
            'projection': {'reachable': [], 'ready': [], 'blocked': []},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='只把照片背景改成浅蓝色',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow-v2',
                'workflow_id': 'image-workflow-v2',
                'revision_id': 'revision-v2',
            }],
            allowed_workflow_refs=['builtin:image-workflow-v2'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow-v2',
                'workflow_id': 'image-workflow-v2',
                'revision_id': 'revision-v2',
                'tool_name': 'trigger_image_workflow_v2_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_image_workflow_v2_workflow')()

    resolve_attachment.assert_called_once_with(current_image)
    import_attachment.assert_called_once_with(current_image)
    toolkit.prepare_workflow.assert_called_once_with(
        'image-workflow-v2', input_bindings={'source_image': imported},
        request_context='只把照片背景改成浅蓝色', workflow_mode='dynamic',
    )
    assert result['input_bindings'] == {'source_image': imported}


@pytest.mark.parametrize(('delivery_mode', 'expected'), [
    ('static', 'plan_static'),
    ('dynamic', 'plan_dynamic'),
])
def test_image_workflow_v2_delivery_choice_uses_validated_brief(delivery_mode, expected):
    from lazymind.chat.workflow.workflow_manager import _select_image_v2_ready_step

    toolkit = MagicMock()
    toolkit.list_artifacts.return_value = {'artifacts': [{
        'artifact_id': 'brief-1', 'slot_id': 'meme_brief_data', 'selected': True,
        'validity': 'effective', 'revision': 1,
        'value': {'data': {'delivery_mode': delivery_mode}},
    }]}

    assert _select_image_v2_ready_step(
        toolkit, 'session-v2', ['plan_static', 'plan_dynamic'],
    ) == expected


def test_image_workflow_v2_completion_text_is_deterministic_and_counts_final_artifacts():
    toolkit = MagicMock()
    toolkit.list_artifacts.return_value = {'artifacts': [
        {
            'artifact_id': 'route-1', 'slot_id': 'route_plan', 'selected': True,
            'validity': 'effective', 'revision': 1,
            'value': {'data': {'route': 'meme'}},
        },
        {
            'artifact_id': 'brief-1', 'slot_id': 'meme_brief_data', 'selected': True,
            'validity': 'effective', 'revision': 1,
            'value': {'data': {'delivery_mode': 'static'}},
        },
        {
            'artifact_id': 'image-1', 'slot_id': 'static_final', 'selected': True,
            'validity': 'effective', 'revision': 2, 'value': {'path': 'one.png'},
        },
        {
            'artifact_id': 'image-2', 'slot_id': 'static_final', 'selected': True,
            'validity': 'effective', 'revision': 1, 'value': {'path': 'two.png'},
        },
        {
            'artifact_id': 'old-image', 'slot_id': 'static_final', 'selected': False,
            'validity': 'effective', 'revision': 1, 'value': {'path': 'old.png'},
        },
        {
            'artifact_id': 'review-1', 'slot_id': 'pack_review', 'selected': True,
            'validity': 'effective', 'revision': 1,
            'value': {'data': {'overall_status': 'approved'}},
        },
    ]}

    text = _image_v2_completion_text(toolkit, 'session-v2')

    assert '静态表情包工作流已完成' in text
    assert '已生成 2 个当前有效的最终产物' in text
    assert '整包检查' not in text
    assert '一键下载全部' in text


def test_terminal_completion_does_not_override_a_human_approval_handoff():
    result = {
        'status': 'waiting',
        'outcome': 'approval_required',
        'projection': {'completed': True},
        '_agent_control': {
            'stop': True,
            'reason': 'approval_required',
            'final_text': '请确认当前产物。',
        },
    }

    assert _with_terminal_agent_control(result, '不应覆盖') == result


def test_image_workflow_v2_completion_summary_failure_never_breaks_completion():
    toolkit = MagicMock()
    toolkit.list_artifacts.side_effect = RuntimeError('temporary artifact read failure')

    text = _image_v2_completion_text(toolkit, 'session-v2')

    assert '图片任务工作流已完成' in text
    assert '未找到可下载的最终产物' in text


def test_image_workflow_v2_correction_reruns_human_step_and_stops_again():
    toolkit = MagicMock()
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-v2', 'state_version': 8,
        'ready_steps': [], 'retryable_steps': [],
        'rewindable_steps': ['edit_candidate'],
        'approval_by_step': {'edit_candidate': 'required'},
        'projection': {
            'nodes': {
                'edit_candidate': {'mode': 'human', 'requires_approval': True},
            },
        },
    }
    toolkit.advance_step.return_value = {
        'status': 'completed', 'state_version': 9,
        'projection': {'completed': True, 'ready': []},
    }
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'completed', 'state_version': 8,
            'projection': {'completed': True},
        }
        contribution = resolve_workflow_injection(
            {
                'session_id': 'session-v2',
                'workflow_id': 'image-workflow-v2',
                'workflow_ref': 'builtin:image-workflow-v2',
            },
            current_query='背景不要浅蓝色，改成浅灰色，其余保持不变。',
            conversation_id='conversation-1',
        )
        # ChatService applies this patch before tool execution.
        lazyllm.globals['agentic_config'].update(contribution.agentic_config_patch)
        result = _tool(contribution, 'advance_step')(['edit_candidate'])

    assert toolkit.advance_step.call_count == 1
    command = toolkit.advance_step.call_args.args[2][0]
    assert command.step_id == 'edit_candidate'
    assert command.user_input == '背景不要浅蓝色，改成浅灰色，其余保持不变。'
    assert toolkit.advance_step.call_args.kwargs['retry_origin'] == 'automatic'
    assert toolkit.advance_step.call_args.kwargs['workflow_mode'] == 'dynamic'
    assert result['status'] == 'waiting'
    assert result['outcome'] == 'approval_required'
    assert result['approval_step'] == 'edit_candidate'
    assert result['host_executed_steps'] == ['edit_candidate']


def test_dynamic_trigger_loads_pinned_remote_package_without_listing():
    lazyllm.globals['agentic_config']['files'] = ['/safe/report.pdf']
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1, 'ready_steps': ['prompt'],
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ), patch('lazymind.chat.workflow.workflow_manager._resolve_workflow_attachment', return_value=(
        '/safe/report.pdf', None,
    )), patch('lazymind.chat.workflow.workflow_manager._import_attachment', return_value={
        'resource_id': 'resource-1', 'revision': 1, 'content_hash': 'sha256:test',
    }):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['prompt'], 'ready': ['prompt'], 'blocked': []},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='original workflow request',
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

        result = _tool(contribution, 'trigger_image_workflow')(
            {'source': 'report.pdf'},
        )

    client_factory.return_value.list_workflows.assert_not_called()
    client_factory.return_value.get_workflow.assert_called_once_with(
        'image-workflow', 'revision-1',
    )
    assert result['status'] == 'prepared'
    assert result['outcome'] == 'ready'
    assert result['request_context'] == 'original workflow request'
    assert result['revision_id'] == 'revision-1'
    assert result['reachable_steps'] == ['prompt']
    assert result['ready_steps'] == ['prompt']
    toolkit.prepare_workflow.assert_called_once_with(
        'image-workflow', input_bindings={
            'source': {'resource_id': 'resource-1', 'revision': 1,
                       'content_hash': 'sha256:test'},
        }, request_context='original workflow request', workflow_mode='dynamic',
    )
    toolkit.advance_step.assert_not_called()


def test_dynamic_trigger_imports_scalar_binding_without_conversation_attachments():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1, 'ready_steps': ['draft'],
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ), patch('lazymind.chat.workflow.workflow_manager._import_text_binding', return_value={
        'resource_id': 'text-resource', 'revision': 1, 'content_hash': 'sha256:text',
    }) as import_text:
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'report', 'revision_id': 'revision-1',
            'compiled_graph': {
                'material_types': {'target_length': 'text'},
                'material_producers': {'target_length': {'kind': 'external'}},
            },
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['draft'], 'ready': ['draft'], 'blocked': []},
        }
        contribution = resolve_workflow_injection(
            None, current_query='write about 3000 words',
            workflow_catalog=[{
                'workflow_ref': 'builtin:report', 'workflow_id': 'report',
                'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:report'],
            workflow_activations=[{
                'workflow_ref': 'builtin:report', 'workflow_id': 'report',
                'revision_id': 'revision-1', 'tool_name': 'trigger_report_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_report_workflow')({
            'target_length': '3000',
        })

    import_text.assert_called_once_with('target_length', '3000')
    assert result['session_id'] == 'session-1'
    toolkit.prepare_workflow.assert_called_once_with(
        'report', input_bindings={
            'target_length': {
                'resource_id': 'text-resource', 'revision': 1,
                'content_hash': 'sha256:text',
            },
        }, request_context='write about 3000 words', workflow_mode='dynamic',
    )


def test_selected_workflow_declares_missing_only_startup_clarification():
    runtime = {
        'clarification_fields': [
            {'id': 'topic', 'label': '主题', 'question': '主题是什么？', 'type': 'text'},
            {'id': 'slide_count', 'label': '页数', 'question': '生成多少页？',
             'type': 'single', 'choices': ['3 页', '5 页'], 'allow_other': False},
        ],
    }
    contribution = resolve_workflow_injection(
        None,
        current_query='给协和医院做一份科技风 PPT',
        workflow_catalog=[{
            'workflow_ref': 'builtin:ppt-workflow',
            'workflow_id': 'ppt-workflow',
            'revision_id': 'revision-1',
            'runtime': runtime,
        }],
        allowed_workflow_refs=['builtin:ppt-workflow'],
        workflow_activations=[{
            'workflow_ref': 'builtin:ppt-workflow',
            'workflow_id': 'ppt-workflow',
            'revision_id': 'revision-1',
            'tool_name': 'trigger_ppt_workflow',
        }],
    )

    assert contribution.runtime_policy == runtime
    assert 'startup_clarification_fields' in contribution.runtime_context
    assert '主题是什么？' in contribution.runtime_context
    assert '生成多少页？' in contribution.runtime_context
    assert '"allow_other": false' in contribution.runtime_context


def test_fixed_startup_choice_policy_overrides_model_other_option():
    runtime = {
        'clarification_fields': [{
            'id': 'generate_background_images',
            'question': '是否为每一页启用 AI 生成底图？',
            'type': 'single',
            'choice_policy': 'fixed',
            'choices': ['启用｜为每页生成独立 AI 底图', '不启用｜使用纯色、渐变和矢量装饰'],
        }],
    }

    questions = enforce_startup_clarification_policy([{
        'id': 'generate_background_images',
        'text': '是否为这份 PPT 启用 AI 底图？',
        'type': 'single',
        'choices': ['启用', '不启用', '其他'],
    }], runtime)

    assert questions == [{
        'id': 'generate_background_images',
        'text': '是否为这份 PPT 启用 AI 底图？',
        'type': 'single',
        'choices': ['启用｜为每页生成独立 AI 底图', '不启用｜使用纯色、渐变和矢量装饰'],
        'allow_other': False,
    }]


def test_seed_startup_choice_policy_remains_open_ended():
    questions = [{
        'id': 'slide_count',
        'text': '希望生成多少页？',
        'type': 'single',
        'choices': ['3 页', '5 页'],
    }]
    runtime = {
        'clarification_fields': [{
            **questions[0],
            'choice_policy': 'seed',
        }],
    }

    assert enforce_startup_clarification_policy(questions, runtime) == questions


def test_startup_clarification_is_single_shot_and_default_trigger_merges_context():
    runtime = {
        'clarification_fields': [
            {'id': 'topic', 'question': '主题是什么？', 'type': 'text'},
            {'id': 'target_customer', 'question': '面向哪类客户？', 'type': 'text'},
        ],
    }
    history = [
        {'role': 'user', 'content': '根据知识库生成两页企业招标准则 PPT'},
        {
            'role': 'assistant',
            'content': '',
            'tool_calls': [{
                'id': 'ask-1',
                'type': 'function',
                'function': {
                    'name': 'ask_user',
                    'arguments': '{"questions":[{"id":"target_customer",'
                                 '"text":"面向哪类客户？","type":"single",'
                                 '"choices":["公司负责人","采购部门"]}]}',
                },
            }],
        },
        {'role': 'tool', 'name': 'ask_user', 'tool_call_id': 'ask-1',
         'content': 'The user submitted the form.'},
    ]
    assert workflow_startup_clarification_already_asked(history, runtime)

    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_requirements'],
    }
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_requirements'],
        'retryable_steps': [], 'rewindable_steps': [],
    }
    toolkit.advance_step.return_value = {'status': 'succeeded'}
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'ppt-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'ready': ['analyze_requirements']},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='面向哪类客户？: 公司负责人',
            conversation_history=history,
            workflow_catalog=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
                'runtime': runtime,
            }],
            allowed_workflow_refs=['builtin:ppt-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_ppt_workflow',
            }],
        )
        # Even if the model supplies only this turn's answer, Host preserves
        # the original request and all of its already-known fields.
        result = _tool(contribution, 'trigger_ppt_workflow')(
            request_context='面向哪类客户？: 公司负责人',
        )
        _tool(contribution, 'advance_step')(['analyze_requirements'])

    assert '根据知识库生成两页企业招标准则 PPT' in result['request_context']
    assert '面向哪类客户？: 公司负责人' in result['request_context']
    toolkit.prepare_workflow.assert_called_once_with(
        'ppt-workflow', input_bindings={}, request_context=result['request_context'],
        workflow_mode='dynamic',
    )
    command = toolkit.advance_step.call_args.args[2][0]
    assert command.user_input == result['request_context']


def test_completed_historical_clarification_does_not_block_a_new_workflow_request():
    runtime = {'clarification_fields': [{
        'id': 'topic', 'question': '这份 PPT 的主题是什么？', 'type': 'text',
    }]}
    history = [
        {'role': 'user', 'content': '做一个 PPT'},
        {
            'role': 'assistant',
            'tool_calls': [{
                'id': 'ask-old',
                'type': 'function',
                'function': {
                    'name': 'ask_user',
                    'arguments': json.dumps({'questions': [{
                        'id': 'topic', 'text': '这份 PPT 的主题是什么？', 'type': 'text',
                    }]}, ensure_ascii=False),
                },
            }],
        },
        {'role': 'tool', 'name': 'ask_user', 'tool_call_id': 'ask-old', 'content': '产品介绍'},
        {'role': 'assistant', 'content': 'PPT 已生成完成。'},
        {'role': 'user', 'content': '再做一份 PPT'},
    ]

    assert not workflow_startup_clarification_already_asked(history, runtime)


def test_interrupted_historical_clarification_does_not_block_a_new_request():
    runtime = {'clarification_fields': [{
        'id': 'generate_background_images',
        'question': '是否启用 AI 底图？',
        'type': 'single',
        'choices': ['启用', '不启用'],
    }]}
    history = [
        {'role': 'user', 'content': '做一个春节 PPT'},
        {
            'role': 'assistant',
            'tool_calls': [{
                'id': 'ask-interrupted',
                'type': 'function',
                'function': {
                    'name': 'ask_user',
                    'arguments': json.dumps({'questions': [{
                        'id': 'generate_background_images',
                        'text': '是否启用 AI 底图？',
                        'type': 'single',
                        'choices': ['启用', '不启用'],
                    }]}, ensure_ascii=False),
                },
            }],
        },
        {'role': 'tool', 'name': 'ask_user', 'tool_call_id': 'ask-interrupted',
         'content': 'The user submitted the form.'},
        {'role': 'user', 'content': '不启用'},
        # The workflow crashed here, before an assistant completion was saved.
    ]

    assert not workflow_startup_clarification_already_asked(
        history,
        runtime,
        current_query='重新做一个春节 PPT',
    )
    assert workflow_startup_clarification_already_asked(
        history,
        runtime,
        current_query='不启用',
    )


def test_clarification_answer_turn_can_pass_merged_request_context_to_trigger():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_requirements'],
    }
    merged = (
        '原始需求：制作医院智算应用技术方案。'
        '补充：8页；客户是协和医院；科技未来风格。'
    )
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'ppt-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'ready': ['analyze_requirements']},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='8页，协和医院，科技未来风格',
            workflow_catalog=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:ppt-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_ppt_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_ppt_workflow')(request_context=merged)

    assert result['request_context'] == merged
    toolkit.prepare_workflow.assert_called_once_with(
        'ppt-workflow', input_bindings={}, request_context=merged, workflow_mode='dynamic',
    )


def test_dynamic_trigger_activates_advance_step_in_the_same_agent_turn():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1, 'ready_steps': ['prompt'],
    }
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['prompt'], 'retryable_steps': [], 'rewindable_steps': [],
    }
    toolkit.advance_step.return_value = {'status': 'succeeded'}
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['prompt'], 'ready': ['prompt']},
        }
        contribution = resolve_workflow_injection(
            {'workflow_mode': 'dynamic'},
            current_query='run it', conversation_id='conversation-1',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
            }],
        )

        assert 'advance_step' in _tool_names(contribution)
        assert 'advance_step_and_hand_off' in _tool_names(contribution)
        assert contribution.stop_tools == []
        _tool(contribution, 'trigger_image_workflow')()
        result = _tool(contribution, 'advance_step')(['prompt'])

    assert result == {'status': 'succeeded'}
    assert toolkit.advance_step.call_args.args[0] == 'session-1'
    assert toolkit.advance_step.call_args.args[1] == 1


def test_selected_workflow_session_tool_auto_initializes_without_attachments():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_requirements'],
    }
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_requirements'],
        'retryable_steps': [], 'rewindable_steps': [],
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'ppt-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {
                'reachable': ['analyze_requirements'],
                'ready': ['analyze_requirements'],
            },
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='生成三页关于加减法数学题的PPT',
            conversation_id='conversation-1',
            workflow_catalog=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:ppt-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:ppt-workflow',
                'workflow_id': 'ppt-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_ppt_workflow',
            }],
        )

        result = _tool(contribution, 'get_ready_steps')()
        repeated_trigger = _tool(contribution, 'trigger_ppt_workflow')()

    assert result['ready_steps'] == ['analyze_requirements']
    assert repeated_trigger['outcome'] == 'already_initialized'
    assert repeated_trigger['session_id'] == 'session-1'
    toolkit.prepare_workflow.assert_called_once_with(
        'ppt-workflow', input_bindings={},
        request_context='生成三页关于加减法数学题的PPT',
        workflow_mode='dynamic',
    )


def test_dynamic_trigger_exposes_handoff_after_session_is_created_in_same_turn():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1, 'ready_steps': ['prompt'],
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client = client_factory.return_value
        client.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        client.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['prompt'], 'ready': ['prompt']},
        }
        client.get_ready_steps.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'ready_steps': ['review'], 'retryable_steps': [], 'rewindable_steps': [],
        }
        client.advance.return_value.result = {'status': 'queued'}
        contribution = resolve_workflow_injection(
            {'workflow_mode': 'dynamic'},
            current_query='run it', conversation_id='conversation-1',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
            }],
        )

        _tool(contribution, 'trigger_image_workflow')()
        result = _tool(contribution, 'advance_step_and_hand_off')('review')

    assert result == '{"status": "queued"}'
    request = client.advance.call_args.args[0]
    assert request.session_id == 'session-1'
    assert request.handoff is True
    assert request.steps[0].step_id == 'review'
    assert request.steps[0].user_input == 'run it'


def test_active_workflow_forwards_current_edit_request_and_focus_to_step():
    toolkit = MagicMock()
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-1', 'state_version': 7,
        'ready_steps': [], 'retryable_steps': [], 'rewindable_steps': ['generate_ppt'],
    }
    toolkit.advance_step.return_value = {'status': 'succeeded'}
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'completed', 'state_version': 7,
            'projection': {
                'completed': True,
                'rewindable': ['generate_ppt'],
            },
        }
        contribution = resolve_workflow_injection(
            {
                'session_id': 'session-1',
                'workflow_id': 'deck-workflow',
                'focused_tab': 'composite_preview',
                'focused_sort_order': 2,
            },
            conversation_id='conversation-1',
            current_query='把这一页标题改成期末练习',
            workflow_catalog=[
                {
                    'workflow_ref': 'builtin:writer-workflow',
                    'workflow_id': 'writer-workflow',
                    'runtime': {'completed_edit_step': 'draft'},
                },
                {
                    'workflow_ref': 'builtin:deck-workflow',
                    'workflow_id': 'deck-workflow',
                    'runtime': {
                        'completed_edit_step': 'generate_ppt',
                        'completed_edit_routing': (
                            'For whole-slide insertions, rewind to build_outline.'
                        ),
                    },
                },
            ],
            allowed_workflow_refs=[
                'builtin:writer-workflow', 'builtin:deck-workflow',
            ],
        )
        # resolve_workflow_injection's patch is applied to agentic_config by ChatService.
        lazyllm.globals['agentic_config'].update(contribution.agentic_config_patch)
        result = _tool(contribution, 'advance_step')(['generate_ppt'])

    assert result == {'status': 'succeeded'}
    command = toolkit.advance_step.call_args.args[2][0]
    assert command.user_input == '把这一页标题改成期末练习'
    assert 'sort order 2' in command.runtime_instruction


def test_only_ppt_workflow_treats_continue_message_as_approval_control():
    toolkit = MagicMock()
    toolkit.get_ready_steps.return_value = {
        'session_id': 'session-1', 'state_version': 7,
        'ready_steps': ['analyze_requirements'],
        'retryable_steps': [], 'rewindable_steps': [], 'continue_steps': [],
    }
    toolkit.advance_step.return_value = {'status': 'succeeded'}
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'waiting', 'state_version': 7,
            'projection': {'ready': ['analyze_requirements']},
        }
        ppt = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'ppt-workflow'},
            conversation_id='conversation-1', current_query='继续',
        )
        lazyllm.globals['agentic_config'].update(ppt.agentic_config_patch)
        _tool(ppt, 'advance_step')(['analyze_requirements'])

        writer = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'writer'},
            conversation_id='conversation-1', current_query='继续',
        )
        lazyllm.globals['agentic_config'].update(writer.agentic_config_patch)
        _tool(writer, 'advance_step')(['analyze_requirements'])

    assert toolkit.advance_step.call_args_list[0].args[2][0].user_input == ''
    assert toolkit.advance_step.call_args_list[1].args[2][0].user_input == '继续'


def test_dynamic_trigger_defaults_request_context_to_current_query():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1, 'ready_steps': ['prompt'],
    }
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['prompt'], 'ready': ['prompt']},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query='run the selected workflow',
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_image_workflow')()

    assert result['request_context'] == 'run the selected workflow'
    toolkit.advance_step.assert_not_called()


def test_dynamic_trigger_preserves_exact_query_instead_of_model_paraphrase():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {
        'session_id': 'session-1', 'state_version': 1,
        'ready_steps': ['analyze_subject'],
    }
    original = '搜索一张哈兰德的照片，然后给他球衣画上必胜两个字'
    paraphrase = '生成一张哈兰德在球场上的写实照片，球衣印有必胜'
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        client_factory.return_value.get_state.return_value = {
            'session_id': 'session-1', 'state_version': 1,
            'projection': {'reachable': ['analyze_subject'], 'ready': ['analyze_subject']},
        }
        contribution = resolve_workflow_injection(
            None,
            current_query=original,
            workflow_catalog=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
            }],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{
                'workflow_ref': 'builtin:image-workflow',
                'workflow_id': 'image-workflow',
                'revision_id': 'revision-1',
                'tool_name': 'trigger_image_workflow',
            }],
        )

        result = _tool(contribution, 'trigger_image_workflow')(
            request_context=paraphrase,
        )

    assert result['request_context'] == original
    toolkit.prepare_workflow.assert_called_once_with(
        'image-workflow', input_bindings={}, request_context=original,
        workflow_mode='dynamic',
    )


def test_dynamic_trigger_returns_waiting_without_advancing_when_no_step_is_ready():
    toolkit = MagicMock()
    toolkit.prepare_workflow.return_value = {'status': 'missing_inputs'}
    with patch('lazymind.chat.workflow.workflow_manager._client') as client_factory, patch(
        'lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit', return_value=toolkit,
    ):
        client_factory.return_value.get_workflow.return_value.result = {
            'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
        }
        contribution = resolve_workflow_injection(
            None, current_query='run it', conversation_id='conversation-1',
            workflow_catalog=[{'workflow_ref': 'builtin:image-workflow',
                               'workflow_id': 'image-workflow', 'revision_id': 'revision-1'}],
            allowed_workflow_refs=['builtin:image-workflow'],
            workflow_activations=[{'workflow_ref': 'builtin:image-workflow',
                                   'workflow_id': 'image-workflow', 'revision_id': 'revision-1',
                                   'tool_name': 'trigger_image_workflow'}],
        )

        result = _tool(contribution, 'trigger_image_workflow')()

    assert result['status'] == 'waiting'
    assert result['outcome'] == 'waiting_for_input'
    toolkit.advance_step.assert_not_called()


def test_enabled_workflow_without_catalog_exposes_only_lazy_authoring_group():
    contribution = resolve_workflow_injection(None, workflow_catalog=[])

    assert contribution.runtime_context == ''
    assert _tool_names(contribution) >= {'workflow_authoring', 'create_workflow_draft'}
    assert 'get_workflow' not in _tool_names(contribution)


def test_model_tool_projection_hides_controller_lifecycle_tools_without_session():
    contribution = resolve_workflow_injection(None, workflow_catalog=[])

    names = _tool_names(contribution)
    assert 'prepare_workflow' not in names
    assert 'start_workflow' not in names
    assert 'stop_workflow' not in names
    assert 'resume_workflow' not in names


@pytest.mark.parametrize('status', ['active', 'waiting', 'failed', 'completed', 'stopped'])
def test_existing_session_hides_controller_lifecycle_tools(status):
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
    assert 'resume_workflow' not in names


def test_existing_session_tools_inject_protocol_and_concurrency_fields():
    toolkit = MagicMock()
    toolkit.get_ready_steps.return_value = {
        'state_version': 7, 'ready_steps': ['draft'],
        'retryable_steps': [], 'rewindable_steps': [],
    }
    toolkit.advance_step.return_value = {'status': 'succeeded'}
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'active', 'state_version': 7,
        }
        contribution = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'writer'},
            conversation_id='conversation-1',
        )

    advance = _tool(contribution, 'advance_step')
    assert list(inspect.signature(advance).parameters) == ['step_ids']
    assert list(inspect.signature(_tool(contribution, 'get_workflow_state')).parameters) == []
    assert advance(['draft']) == {'status': 'succeeded'}
    args = toolkit.advance_step.call_args.args
    assert args[0] == 'session-1'
    assert args[1] == 7
    assert args[2][0].step_id == 'draft'
    assert args[2][0].objective == ''
    assert args[2][0].task_id == ''


def test_advance_step_refreshes_state_version_once_on_conflict():
    toolkit = MagicMock()
    toolkit.get_ready_steps.side_effect = [
        {'state_version': 7, 'ready_steps': ['draft']},
        {'state_version': 8, 'ready_steps': ['draft']},
    ]
    toolkit.advance_step.side_effect = [
        WorkflowClientError('STATE_VERSION_CONFLICT', 'stale'),
        {'status': 'succeeded'},
    ]
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'active', 'state_version': 7,
        }
        contribution = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'writer'},
            conversation_id='conversation-1',
        )

    result = _tool(contribution, 'advance_step')(['draft'])

    assert result['status'] == 'succeeded'
    assert result['state_version_refreshed'] is True
    assert [call.args[1] for call in toolkit.advance_step.call_args_list] == [7, 8]


def test_only_handoff_advance_stops_an_active_workflow_turn():
    toolkit = MagicMock()
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'active', 'state_version': 7,
        }
        contribution = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'writer'},
            conversation_id='conversation-1',
        )

    assert contribution.stop_tools == ['advance_step_and_hand_off']


def test_advance_step_returns_user_notice_when_target_changes_after_conflict():
    toolkit = MagicMock()
    toolkit.get_ready_steps.side_effect = [
        {'state_version': 7, 'ready_steps': ['draft']},
        {'state_version': 8, 'ready_steps': ['review']},
    ]
    toolkit.advance_step.side_effect = WorkflowClientError(
        'STATE_VERSION_CONFLICT', 'stale',
    )
    with patch('lazymind.chat.workflow.workflow_manager.HostWorkflowToolkit',
               return_value=toolkit), patch(
        'lazymind.chat.workflow.workflow_manager._client',
    ) as client_factory:
        client_factory.return_value.get_state.return_value = {
            'status': 'active', 'state_version': 7,
        }
        contribution = resolve_workflow_injection(
            {'session_id': 'session-1', 'workflow_id': 'writer'},
            conversation_id='conversation-1',
        )

    result = _tool(contribution, 'advance_step')(['draft'])

    assert result['outcome'] == 'workflow_state_changed'
    assert result['ready_steps'] == ['review']
    assert toolkit.advance_step.call_count == 1


def test_model_frontier_omits_package_prompts_but_preserves_routing_and_approval():
    from lazymind.chat.workflow.workflow_manager import _compact_model_frontier
    projection = {'ready': ['review'], 'edges': [{'when': 'user requested images'}],
                  'nodes': {'review': {'requires_approval': True}}}
    state = {'graph': {'prompt': 'large package prompt' * 5000}, 'projection': projection,
             'state_version': 7, 'status': 'active'}
    payload = {'projection': projection, 'workflow_state': state,
               'ready_steps': ['review'], 'retryable_steps': ['draft'],
               'ready_step_details': [{'step_id': 'review', 'requires_approval': True}]}
    result = _compact_model_frontier(payload)
    assert 'graph' not in result['workflow_state']
    assert 'graph' in payload['workflow_state']
    assert result['projection'] == projection
    assert result['ready_step_details'] == payload['ready_step_details']
    assert result['retryable_steps'] == ['draft']
    frontier = _compact_model_frontier({'projection': state, 'ready_steps': ['review']})
    assert frontier['projection']['projection'] == projection
    assert 'graph' not in frontier['projection']


@pytest.mark.parametrize('query', [
    '请重新执行步骤 outline',
    'Please re-run step outline',
    '把第一章缩短到 500 字',
])
@pytest.mark.parametrize('handoff', [False, True])
def test_rerun_turn_preserves_session_intent_for_downstream_steps(query, handoff):
    from lazymind.chat.workflow import workflow_manager as workflows

    lazyllm.globals['agentic_config'].update({
        'workflow_current_query': query,
        'query': query,
        'focused_tab': 'result',
    })
    frontier = {
        'session_id': 'session-1', 'state_version': 7,
        'ready_steps': ['write_document'], 'retryable_steps': [],
        'rewindable_steps': ['outline'],
    }
    toolkit = MagicMock()
    toolkit.get_ready_steps.return_value = frontier
    toolkit.advance_step.return_value = {'status': 'active'}
    with patch.object(workflows, '_client') as client_factory:
        client = client_factory.return_value
        client.get_ready_steps.return_value = frontier
        client.advance.return_value.result = {'status': 'active'}
        if handoff:
            tool = workflows._handoff_tool('session-1')
        else:
            tool = next(tool for tool in workflows._safe_session_tools(toolkit, 'session-1')
                        if tool.__name__ == 'advance_step')
        for step_id in ['outline', 'write_document']:
            tool(step_id if handoff else [step_id])
            command = (client.advance.call_args.args[0].steps[0] if handoff
                       else toolkit.advance_step.call_args.args[2][0])
            is_rerun = query != '把第一章缩短到 500 字'
            assert command.user_input == ('' if is_rerun else query)
            assert 'result' in command.runtime_instruction
            if is_rerun:
                assert query in command.runtime_instruction
