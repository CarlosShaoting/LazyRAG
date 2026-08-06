"""LazyMind Chat adapter for the public Workflow runtime.

This module deliberately owns no Workflow definition loading, graph policy,
transition state, input binding, or Artifact persistence.  It only turns the
public Workflow SDK into ChatAgent tools and applies LazyMind's handoff rule.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import httpx
import lazyllm

from lazymind.chat.engine.tools.intent_writer import enable_workflow_intent_scopes
from lazymind.workflow_sdk import AdvanceRequest, StepCommand, WorkflowClient, WorkflowClientError
from lazymind.workflow_toolkit import (
    AgentWorkflowToolProjection, HostWorkflowToolkit, StepCommandInput,
)

LOG = logging.getLogger(__name__)


@dataclass
class WorkflowAgentContribution:
    tools: List[Any]
    stop_tools: List[str]
    agentic_config_patch: Dict[str, Any]
    runtime_context: str


def _agentic_config() -> Dict[str, Any]:
    return lazyllm.globals.get('agentic_config', {}) or {}


def _client() -> WorkflowClient:
    from lazymind.config import config
    cfg = _agentic_config()
    return WorkflowClient(
        str(config['core_api_url']).rstrip('/'),
        str(cfg.get('user_id') or ''),
        host='lazymind',
        transport=httpx,
    )


def _result_text(value: Any) -> str:
    if hasattr(value, 'result'):
        value = value.result
    return json.dumps(value, ensure_ascii=False, default=str)


def _workflow_definition(workflow_id: str, revision_id: str = '') -> Dict[str, Any]:
    try:
        return _client().get_workflow(workflow_id, revision_id).result
    except WorkflowClientError:
        LOG.exception('public Workflow definition read failed id=%s', workflow_id)
        return {}


def _step_ids(workflow_id: str, revision_id: str = '') -> List[str]:
    package = _workflow_definition(workflow_id, revision_id)
    graph = package.get('compiled_graph') if isinstance(package.get('compiled_graph'), dict) else {}
    nodes = graph.get('nodes') if isinstance(graph.get('nodes'), dict) else {}
    return list(nodes)


def _state(session_id: str) -> Dict[str, Any]:
    try:
        return _client().get_state(session_id)
    except WorkflowClientError as exc:
        return {'error': {'code': exc.code, 'message': exc.message}}


def _handoff_tool(session_id: str) -> Any:
    def advance_step_and_hand_off(step_id: str) -> str:
        """Advance one Ready Workflow step through the public runtime."""
        client = _client()
        frontier = client.get_ready_steps(session_id)
        allowed = set(frontier.get('ready_steps') or [])
        allowed.update(frontier.get('retryable_steps') or [])
        allowed.update(frontier.get('rewindable_steps') or [])
        if step_id not in allowed:
            raise WorkflowClientError(
                'WORKFLOW_TARGET_NOT_PROJECTED', 'Handoff target is not currently actionable.',
                details={'step_id': step_id, 'allowed': sorted(allowed)},
            )
        response = client.advance(AdvanceRequest(
            session_id=session_id,
            expected_state_version=int(frontier.get('state_version') or 0),
            steps=[StepCommand(step_id=step_id)],
            handoff=True,
        ))
        return _result_text(response)

    advance_step_and_hand_off.__doc__ = (
        'Submit a Ready target and end this LazyMind turn only after durable '
        'Supervisor ownership is acknowledged.'
    )
    return advance_step_and_hand_off


def _artifact_by_handle(toolkit: HostWorkflowToolkit, session_id: str,
                        artifact_ref: str) -> Dict[str, Any]:
    values = toolkit.list_artifacts(session_id).get('artifacts') or []
    ref = str(artifact_ref or '').strip()
    matches = []
    for item in values:
        index = item.get('list_index')
        handles = {str(item.get('artifact_id') or item.get('id') or ''), str(item.get('slot') or '')}
        if index is not None:
            handles.add(f'{item.get("slot")}[{index}]')
        if ref in handles:
            matches.append(item)
    if len(matches) != 1:
        raise WorkflowClientError(
            'ARTIFACT_NOT_SELECTED',
            f'Artifact reference {ref!r} must identify one selected Session artifact.',
            details={'available_artifacts': [
                f'{item.get("slot")}[{item.get("list_index")}]'
                if item.get('list_index') is not None else item.get('slot') for item in values
            ]},
        )
    return matches[0]


def _safe_session_tools(toolkit: HostWorkflowToolkit, session_id: str) -> List[Any]:
    """Model tools whose protocol and concurrency parameters are Host-injected."""
    def get_workflow_state() -> Dict[str, Any]:
        """Read this conversation's authoritative Workflow state."""
        return toolkit.get_workflow_state(session_id)

    def get_ready_steps() -> Dict[str, Any]:
        """Read exact forward, retryable, and rewindable targets for this Session."""
        return toolkit.get_ready_steps(session_id)

    def advance_step(step_ids: List[str]) -> Dict[str, Any]:
        """Execute exact Runtime-returned target IDs; Host injects version and commands."""
        frontier = toolkit.get_ready_steps(session_id)
        allowed = set(frontier.get('ready_steps') or [])
        allowed.update(frontier.get('retryable_steps') or [])
        allowed.update(frontier.get('rewindable_steps') or [])
        requested = [str(value).strip() for value in step_ids if str(value).strip()]
        if not requested or any(value not in allowed for value in requested):
            raise WorkflowClientError(
                'WORKFLOW_TARGET_NOT_PROJECTED',
                'Every target must come from the latest Runtime target classes.',
                details={'requested': requested, 'allowed': sorted(allowed)},
            )
        recovery = set(frontier.get('retryable_steps') or []) | set(
            frontier.get('rewindable_steps') or [],
        )
        if len(requested) > 1 and any(value in recovery for value in requested):
            raise WorkflowClientError(
                'WORKFLOW_RECOVERY_MUST_BE_SINGULAR',
                'Retryable and rewindable targets must be submitted one at a time.',
            )
        return toolkit.advance_step(
            session_id, int(frontier.get('state_version') or 0),
            [StepCommandInput(step_id=value) for value in requested],
        )

    def resume_workflow() -> Dict[str, Any]:
        """Resume this stopped Session; Host injects lifecycle command metadata."""
        return toolkit.resume_workflow(session_id)

    def list_workflow_inputs() -> Dict[str, Any]:
        """List durable input bindings for this Session."""
        return toolkit.list_workflow_inputs(session_id)

    def list_artifacts() -> Dict[str, Any]:
        """List selected Artifacts for this Session."""
        return toolkit.list_artifacts(session_id)

    def read_artifact(artifact_ref: str) -> Dict[str, Any]:
        """Read a selected Artifact by exact slot handle such as report or images[0]."""
        artifact = _artifact_by_handle(toolkit, session_id, artifact_ref)
        return toolkit.read_artifact(str(artifact.get('artifact_id') or artifact.get('id') or ''))

    def patch_artifact(artifact_ref: str, value: Any, caption: str = '') -> Dict[str, Any]:
        """Patch a selected Artifact; Host injects id, base revision, type, and command."""
        artifact = _artifact_by_handle(toolkit, session_id, artifact_ref)
        artifact_id = str(artifact.get('artifact_id') or artifact.get('id') or '')
        content_type = str(artifact.get('content_type') or 'json')
        return toolkit.patch_artifact(
            artifact_id, int(artifact.get('revision') or 0), value, content_type, caption,
        )

    return [
        get_workflow_state, get_ready_steps, advance_step, resume_workflow,
        list_workflow_inputs, list_artifacts, read_artifact, patch_artifact,
    ]


def _safe_authoring_tools(toolkit: HostWorkflowToolkit) -> List[Any]:
    """Context-bound authoring tools; models author content, not concurrency metadata."""
    cfg = _agentic_config()

    def _draft() -> Dict[str, Any]:
        draft_id = str(cfg.get('workflow_authoring_draft_id') or '')
        if not draft_id:
            raise WorkflowClientError(
                'WORKFLOW_DRAFT_NOT_SELECTED',
                'Create or select a Workflow draft before using this authoring action.',
            )
        value = toolkit.get_workflow_draft(draft_id)
        cfg['workflow_authoring_draft_version'] = int(value.get('version') or 0)
        return value

    def workflow_connection_status() -> Dict[str, Any]:
        """Verify Workflow API connectivity."""
        return toolkit.workflow_connection_status()

    def list_workflows() -> Dict[str, Any]:
        """List exact Workflow references available for selection."""
        return toolkit.list_workflows()

    def get_workflow(workflow_id: str) -> Dict[str, Any]:
        """Select and read a Workflow; Host pins its current revision."""
        value = toolkit.get_workflow(workflow_id)
        cfg['workflow_authoring_workflow_ref'] = str(value.get('workflow_ref') or workflow_id)
        return value

    def list_skills() -> Dict[str, Any]:
        """List Skills available for Workflow conversion."""
        return toolkit.list_skills()

    def get_skill_conversion_context(skill_id: str) -> Dict[str, Any]:
        """Select a Skill snapshot; Host retains revision and tree hash."""
        value = toolkit.get_skill_conversion_context(skill_id)
        cfg['workflow_authoring_skill_context'] = {
            'skill_id': skill_id,
            'revision_id': str(value.get('revision_id') or ''),
            'tree_hash': str(value.get('tree_hash') or ''),
        }
        return value

    def create_workflow_draft(name: str, files: Dict[str, str]) -> Dict[str, Any]:
        """Create a draft from authored files; Host injects pinned Skill metadata."""
        skill = cfg.get('workflow_authoring_skill_context') or {}
        source_type = 'skill' if skill else 'blank'
        value = toolkit.create_workflow_draft(
            name, files, str(skill.get('skill_id') or ''),
            str(skill.get('revision_id') or ''), str(skill.get('tree_hash') or ''), source_type,
        )
        cfg['workflow_authoring_draft_id'] = str(value.get('draft_id') or value.get('id') or '')
        cfg['workflow_authoring_draft_version'] = int(value.get('version') or 0)
        return value

    def list_workflow_drafts() -> Dict[str, Any]:
        """List drafts available for exact selection."""
        return toolkit.list_workflow_drafts()

    def select_workflow_draft(draft_id: str) -> Dict[str, Any]:
        """Select one exact draft returned by list_workflow_drafts."""
        value = toolkit.get_workflow_draft(draft_id)
        cfg['workflow_authoring_draft_id'] = draft_id
        cfg['workflow_authoring_draft_version'] = int(value.get('version') or 0)
        return value

    def get_workflow_draft() -> Dict[str, Any]:
        """Read the selected authoring draft."""
        return _draft()

    def update_workflow_draft_file(path: str, content: str) -> Dict[str, Any]:
        """Update one allowed package path; Host injects draft and optimistic version."""
        current = _draft()
        value = toolkit.update_workflow_draft_file(
            str(cfg['workflow_authoring_draft_id']), path, content,
            int(current.get('version') or 0),
        )
        cfg['workflow_authoring_draft_version'] = int(value.get('version') or 0)
        return value

    def validate_workflow_draft() -> Dict[str, Any]:
        """Validate the selected draft."""
        _draft()
        return toolkit.validate_workflow_draft(str(cfg['workflow_authoring_draft_id']))

    def get_workflow_diagnostics() -> Dict[str, Any]:
        """Read diagnostics for the selected draft."""
        _draft()
        return toolkit.get_workflow_diagnostics(str(cfg['workflow_authoring_draft_id']))

    def publish_workflow() -> Dict[str, Any]:
        """Publish the selected validated draft."""
        _draft()
        return toolkit.publish_workflow(str(cfg['workflow_authoring_draft_id']))

    return [
        workflow_connection_status, list_workflows, get_workflow,
        list_skills, get_skill_conversion_context, create_workflow_draft,
        list_workflow_drafts, select_workflow_draft, get_workflow_draft,
        update_workflow_draft_file, validate_workflow_draft,
        get_workflow_diagnostics, publish_workflow,
    ]


def _import_attachment(path: str) -> Dict[str, Any]:
    from lazymind.chat.workflow.file_adapter import LazyMindHostFileAdapter
    from lazymind.config import config
    cfg = _agentic_config()
    value = LazyMindHostFileAdapter(
        str(config['core_api_url']).rstrip('/'), str(cfg.get('user_id') or ''), transport=httpx,
    ).import_attachment(path)
    return asdict(value)


def _workflow_trigger_tools(
    activations: List[Dict[str, Any]], allowed_refs: set[str], current_query: str = '',
    conversation_id: str = '',
) -> List[Any]:
    """Bind backend-prepared activations to public package reads."""
    candidates = [
        item for item in activations
        if not allowed_refs or str(item.get('workflow_ref') or '') in allowed_refs
    ]
    tools: List[Any] = []
    used_names: set[str] = set()
    for item in candidates:
        workflow_id = str(item.get('workflow_id') or '').strip()
        workflow_ref = str(item.get('workflow_ref') or '').strip()
        revision_id = str(item.get('revision_id') or '').strip()
        if not workflow_id or not workflow_ref:
            continue
        name = str(item.get('tool_name') or '').strip()
        if not name.startswith('trigger_') or not name.endswith('_workflow') or not name.isidentifier():
            continue
        if name in used_names:
            continue
        used_names.add(name)

        def make_trigger(
            bound_id: str, bound_ref: str, bound_revision: str, bound_query: str,
        ) -> Any:
            def bound_trigger(input_bindings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
                """Initialize the selected Workflow Session and return its Ready frontier."""
                effective_context = bound_query
                resolved_bindings: Dict[str, Any] = {}
                for material_id, attachment_ref in (input_bindings or {}).items():
                    from lazymind.chat.engine.subagent.tools import _resolve_attachment
                    path, error = _resolve_attachment(attachment_ref)
                    if error or not path:
                        raise WorkflowClientError(
                            'ATTACHMENT_NOT_SELECTED',
                            error or 'The referenced conversation attachment was not found.',
                        )
                    resolved_bindings[material_id] = _import_attachment(path)
                client = _client()
                package = client.get_workflow(bound_id, bound_revision).result
                toolkit = HostWorkflowToolkit(
                    _client,
                    allowed_workflow_ids=[bound_id],
                    origin_ref=conversation_id,
                )
                prepared = toolkit.prepare_workflow(
                    bound_id, input_bindings=resolved_bindings,
                    request_context=effective_context,
                )
                session_id = str(prepared.get('session_id') or '')
                if not session_id:
                    return {
                        **prepared,
                        'status': 'waiting',
                        'outcome': 'waiting_for_input',
                        'reason': 'Workflow preparation requires additional input before a Session can be created.',
                        'workflow_ref': bound_ref,
                        'workflow_id': bound_id,
                        'revision_id': str(package.get('revision_id') or bound_revision),
                        'request_context': effective_context,
                        'input_bindings': resolved_bindings,
                    }
                state = client.get_state(session_id)
                projection = state.get('projection') if isinstance(state.get('projection'), dict) else state

                def step_ids(values: Any) -> List[str]:
                    result: List[str] = []
                    for value in values or []:
                        step_id = value.get('step_id') if isinstance(value, dict) else value
                        step_id = str(step_id or '').strip()
                        if step_id:
                            result.append(step_id)
                    return result

                ready_steps = step_ids(
                    projection.get('ready') or projection.get('ready_steps')
                    or prepared.get('ready_steps')
                )
                reachable_steps = step_ids(
                    projection.get('reachable') or projection.get('reachable_steps')
                    or ready_steps
                )
                blocked_steps = step_ids(
                    projection.get('blocked') or projection.get('blocked_steps')
                )
                retryable_steps = step_ids(
                    projection.get('retryable') or projection.get('retryable_steps')
                )
                rewindable_steps = step_ids(
                    projection.get('rewindable') or projection.get('rewindable_steps')
                )
                return {
                    **prepared,
                    'status': 'prepared',
                    'outcome': 'ready' if ready_steps else 'waiting',
                    'reason': (
                        'Workflow session was initialized; select an exact Ready step and call advance_step.'
                        if ready_steps else
                        'Workflow session was initialized but no step is currently Ready.'
                    ),
                    'workflow_ref': bound_ref,
                    'workflow_id': bound_id,
                    'revision_id': str(package.get('revision_id') or bound_revision),
                    'request_context': effective_context,
                    'input_bindings': resolved_bindings,
                    'session_id': session_id,
                    'state_version': int(state.get('state_version') or prepared.get('state_version') or 0),
                    'projection': projection,
                    'reachable_steps': reachable_steps,
                    'ready_steps': ready_steps,
                    'blocked_steps': blocked_steps,
                    'retryable_steps': retryable_steps,
                    'rewindable_steps': rewindable_steps,
                    'next_action': {
                        'tool': 'advance_step',
                        'instruction': (
                            'Call advance_step using only exact members of ready_steps, '
                            'retryable_steps, or rewindable_steps; Runtime resolves the operation.'
                        ),
                    },
                }
            return bound_trigger

        trigger_workflow = make_trigger(workflow_id, workflow_ref, revision_id, current_query)

        trigger_workflow.__name__ = name
        trigger_workflow.__doc__ = str(item.get('tool_description') or '').strip()
        tools.append(trigger_workflow)
    return tools


def _is_bound_workflow_trigger(name: str) -> bool:
    return name.startswith('trigger_') and name.endswith('_workflow')


def resolve_workflow_injection(
    workflow_context: Optional[Dict[str, Any]],
    conversation_id: str = '',
    current_query: str = '',
    workflow_catalog: Optional[List[Dict[str, Any]]] = None,
    disabled_builtin_workflows: Optional[List[str]] = None,
    allowed_workflow_refs: Optional[List[str]] = None,
    workflow_activations: Optional[List[Dict[str, Any]]] = None,
) -> WorkflowAgentContribution:
    """Map public Workflow APIs to LazyMind Chat tools; no Runtime decisions live here."""
    cfg = _agentic_config()
    if not cfg.get('enable_workflow', True):
        return WorkflowAgentContribution([], [], {}, '')

    context = workflow_context if isinstance(workflow_context, dict) else {}
    session_id = str(context.get('session_id') or '')
    workflow_id = str(context.get('workflow_id') or context.get('workflow_ref') or '')
    revision_id = str(context.get('revision_id') or '')
    mode = str(context.get('workflow_mode') or 'dynamic')
    patch: Dict[str, Any] = {'workflow_mode': mode}

    catalog = workflow_catalog or []
    allowed_refs = {
        str(value).strip() for value in (allowed_workflow_refs or []) if str(value).strip()
    }
    allowed_items = [
        item for item in catalog
        if str(item.get('workflow_ref') or '') in allowed_refs
    ]
    allowed_ids = [
        str(item.get('workflow_id') or '').strip() for item in allowed_items
        if str(item.get('workflow_id') or '').strip()
    ]
    for ref in allowed_refs:
        if ref.startswith('builtin:'):
            allowed_ids.append(ref.removeprefix('builtin:'))
    allowed_ids = list(dict.fromkeys(allowed_ids))

    activations = workflow_activations or []
    trigger_tools = _workflow_trigger_tools(
        activations, allowed_refs, current_query, conversation_id,
    )
    toolkit = HostWorkflowToolkit(
        _client, allowed_workflow_ids=allowed_ids, origin_ref=conversation_id,
    )
    candidate_tools = [
        *trigger_tools,
        *toolkit.tools(),
    ]
    projection = _state(session_id) if session_id else {}
    tools = AgentWorkflowToolProjection(
        session_id=session_id,
        session_status=str(projection.get('status') or context.get('status') or ''),
    ).expose(candidate_tools)
    execution_tools = {
        'workflow_connection_status', 'get_workflow', 'get_workflow_state',
        'get_ready_steps', 'advance_step', 'resume_workflow',
        'list_workflow_inputs', 'get_workflow_command',
        'list_artifacts', 'read_artifact', 'patch_artifact', 'delete_artifact',
    }
    if allowed_refs or session_id:
        tools = [
            tool for tool in tools
            if _is_bound_workflow_trigger(str(getattr(tool, '__name__', '')))
            or str(getattr(tool, '__name__', '')) in execution_tools
        ]
    if allowed_refs and not session_id:
        tools = [tool for tool in tools if _is_bound_workflow_trigger(tool.__name__)]
    elif not session_id:
        tools = _safe_authoring_tools(toolkit)
    if session_id:
        tools = _safe_session_tools(toolkit, session_id)
        status = str(projection.get('status') or context.get('status') or '').lower()
        if status != 'stopped':
            tools = [tool for tool in tools if tool.__name__ != 'resume_workflow']
        patch.update({
            'workflow_id': workflow_id,
            'workflow_session_id': session_id,
            'workflow_step': context.get('current_step') or '',
            'workflow_ref': context.get('workflow_ref') or '',
            'revision_id': revision_id,
        })
        tools.append(_handoff_tool(session_id))
        runtime_context = (
            '## Workflow Runtime [AUTHORITATIVE]\n'
            + json.dumps(projection, ensure_ascii=False, default=str)
        )
        return WorkflowAgentContribution(
            tools, ['advance_step', 'advance_step_and_hand_off'],
            patch, runtime_context,
        )

    del disabled_builtin_workflows
    selection_context = ''
    if allowed_refs:
        activation_prompts = [
            str(item.get('prompt') or '').strip() for item in activations
            if str(item.get('workflow_ref') or '') in allowed_refs
            and str(item.get('prompt') or '').strip()
        ]
        selection_context = (
            '## Explicit Workflow Selection [AUTHORITATIVE]\n'
            + '\n'.join(activation_prompts) + '\n'
            + 'Start the selected workflow in this turn. Treat current_query as the '
            + 'workflow request_context and as user_input for the first Ready step; do not '
            + 'ask for a second trigger message when current_query is non-empty. For recovery, '
            + 'use only exact retryable_steps or rewindable_steps returned by Runtime.\n'
            + json.dumps({
                'current_query': current_query,
                'allowed_workflow_refs': sorted(allowed_refs),
                'activations': activations,
                'allowed_workflow_ids': allowed_ids,
            }, ensure_ascii=False, default=str)
        )
    return WorkflowAgentContribution(
        tools, ['advance_step'], patch, selection_context,
    )


def update_intentwriter(tool: Any, workflow_context: Optional[Dict[str, Any]]) -> Any:
    """Add LazyMind intent scopes using step ids read from the public package."""
    context = workflow_context if isinstance(workflow_context, dict) else {}
    session_id = str(context.get('session_id') or '')
    workflow_id = str(context.get('workflow_id') or context.get('workflow_ref') or '')
    if not session_id or not workflow_id:
        return tool
    return enable_workflow_intent_scopes(
        tool,
        session_id=session_id,
        workflow_id=workflow_id,
        valid_step_ids=_step_ids(workflow_id, str(context.get('revision_id') or '')),
    )


def _build_chat_agent_task_context(conversation_id: str) -> str:
    """Generic LazyMind task presentation; unrelated to Workflow state authority."""
    if not conversation_id.strip():
        return ''
    from lazymind.chat.engine.subagent.db import TaskQueryDB
    return TaskQueryDB().build_chat_agent_task_context(conversation_id.strip())


async def guard_workflow_agent_stream(initial_stream: Any, **_: Any):
    """LazyMind handoff is enforced by declaring its tool as a stop tool."""
    async for item in initial_stream:
        yield item
