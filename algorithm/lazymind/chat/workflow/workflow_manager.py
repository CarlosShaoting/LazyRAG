"""LazyMind Chat adapter for the public Workflow runtime.

This module deliberately owns no Workflow definition loading, graph policy,
transition state, input binding, or Artifact persistence.  It only turns the
public Workflow SDK into ChatAgent tools and applies LazyMind's handoff rule.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import httpx
import lazyllm

from lazymind.chat.engine.tools.intent_writer import enable_workflow_intent_scopes
from lazymind.workflow_sdk import AdvanceRequest, StepCommand, WorkflowClient, WorkflowClientError
from lazymind.workflow_toolkit import HostWorkflowToolkit

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
    def advance_step_and_hand_off(
        step_id: str,
        objective: str = '',
        user_input: str = '',
        runtime_instruction: str = '',
    ) -> str:
        """Advance one Ready Workflow step through the public runtime."""
        state = _client().get_state(session_id)
        version = int(state.get('state_version') or 0)
        response = _client().advance(AdvanceRequest(
            session_id=session_id,
            expected_state_version=version,
            steps=[StepCommand(
                step_id=step_id,
                objective=objective,
                user_input=user_input,
                runtime_instruction=runtime_instruction,
            )],
            handoff=True,
            command_id=str(uuid.uuid4()),
        ))
        return _result_text(response)

    advance_step_and_hand_off.__doc__ = (
        'Submit a Ready target and end this LazyMind turn only after durable '
        'Supervisor ownership is acknowledged.'
    )
    return advance_step_and_hand_off


def _attachment_import_tool() -> Any:
    def import_workflow_attachment(path: str) -> Dict[str, Any]:
        """Import a selected LazyMind attachment into the public resource store."""
        from lazymind.chat.workflow.file_adapter import LazyMindHostFileAdapter
        from lazymind.config import config
        cfg = _agentic_config()
        value = LazyMindHostFileAdapter(
            str(config['core_api_url']).rstrip('/'), str(cfg.get('user_id') or ''),
            transport=httpx,
        ).import_attachment(path)
        return asdict(value)

    return import_workflow_attachment


def _workflow_trigger_tools(
    activations: List[Dict[str, Any]], allowed_refs: set[str],
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

        def make_trigger(bound_id: str, bound_ref: str, bound_revision: str) -> Any:
            def bound_trigger(request_context: str = '') -> Dict[str, Any]:
                """Load the exact remotely published Workflow selected for this request."""
                package = _client().get_workflow(bound_id, bound_revision).result
                return {
                    'status': 'loaded',
                    'workflow_ref': bound_ref,
                    'workflow_id': bound_id,
                    'revision_id': str(package.get('revision_id') or bound_revision),
                    'request_context': request_context,
                    'workflow': package,
                    'next_action': (
                        'Follow workflow-agent-kit. Import required inputs, then call '
                        'prepare_workflow with this exact workflow_id.'
                    ),
                }
            return bound_trigger

        trigger_workflow = make_trigger(workflow_id, workflow_ref, revision_id)

        trigger_workflow.__name__ = name
        trigger_workflow.__doc__ = str(item.get('tool_description') or '').strip()
        tools.append(trigger_workflow)
    return tools


def resolve_workflow_injection(
    workflow_context: Optional[Dict[str, Any]],
    conversation_id: str = '',
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
    trigger_tools = _workflow_trigger_tools(activations, allowed_refs)
    tools = [
        *trigger_tools,
        *HostWorkflowToolkit(
            _client, allowed_workflow_ids=allowed_ids, origin_ref=conversation_id,
        ).tools(),
        _attachment_import_tool(),
    ]
    if session_id:
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
            + json.dumps(_state(session_id), ensure_ascii=False, default=str)
        )
        return WorkflowAgentContribution(
            tools, ['advance_step_and_hand_off'],
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
            + json.dumps({
                'allowed_workflow_refs': sorted(allowed_refs),
                'activations': activations,
                'allowed_workflow_ids': allowed_ids,
            }, ensure_ascii=False, default=str)
        )
    return WorkflowAgentContribution(
        tools, [], patch, selection_context,
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
