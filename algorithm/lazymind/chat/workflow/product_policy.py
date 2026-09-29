"""Bounded execution for the built-in product workflow.

This is a product-only policy adapter.  The shared runner and remote executor
call it as an optional policy: when ``publication_enabled`` is false they keep
their upstream defaults and the generic Workflow main path is unchanged.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

PRODUCT_WORKFLOW = 'product_solution_delivery'
WRITER_STAGES = ('direction', 'design', 'prd', 'review', 'handoff')


@dataclass(frozen=True)
class ProductPolicy:
    rounds: int
    timeout: int
    fail_fast: frozenset[str]
    calls: dict[str, int]


def publication_enabled(params: dict[str, Any]) -> bool:
    runtime = params.get('workflow_runtime') or {}
    owned = runtime.get('publisher_owned_slots') or []
    return params.get('workflow_id') == PRODUCT_WORKFLOW and {'workspace_state', 'stage_manifest'} <= set(owned)


def policy_for(params: dict[str, Any]) -> ProductPolicy | None:
    if not publication_enabled(params):
        return None
    step = params.get('step_id', '')
    calls = {'load_product_skill_contract': 2, 'load_product_stage_inputs': 2,
             'get_artifact': 3, 'save_artifacts': 2, 'validate_product_stage_assessment': 2}
    if step in ('route_product_stage', 'route_design_scope'):
        rounds, timeout = 5, 120
        publishers = {'publish_product_route', 'publish_design_route', 'publish_design_route_compact'}
        calls.update({name: 2 for name in publishers}, profile_product_materials=2)
    elif step == 'finalize_product_delivery':
        rounds, timeout = 3, 120
        publishers = {'publish_product_handoff_state'}
        calls['publish_product_handoff_state'] = 1
    elif step in {f'build_{stage}_outline' for stage in WRITER_STAGES}:
        rounds, timeout = 4, 300
        publishers = {'product_writer_generate_outline_from_inputs', 'product_writer_revise_markdown',
                      'product_writer_revise_and_publish'}
        calls.update({name: 1 for name in publishers})
    elif step in {f'write_{stage}_document' for stage in WRITER_STAGES}:
        rounds, timeout = 7, 720
        publishers = {'product_writer_generate_document_from_inputs', 'product_writer_revise_markdown',
                      'product_writer_revise_and_publish'}
        calls.update({name: 1 for name in publishers})
    elif step in ('analyze_competitive_position', 'build_interactive_prototype'):
        rounds, timeout = 7, 600
        publishers = {'write_product_artifact_bundle'}
        calls['write_product_artifact_bundle'] = 1
    elif step in ('collect_design_light_evidence', 'collect_design_heavy_evidence'):
        rounds, timeout = (20, 480) if 'light' in step else (24, 600)
        publishers = {'publish_design_heavy_evidence', 'publish_design_heavy_unavailable'}
        calls.update({name: 1 for name in publishers})
    else:
        return None
    return ProductPolicy(rounds, timeout, frozenset(publishers), calls)


def _scalar(value: Any) -> str:
    for _ in range(3):
        if isinstance(value, dict):
            value = value.get('data', value.get('text', value))
        elif isinstance(value, str) and value.strip().startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                break
        else:
            break
    if isinstance(value, (dict, list)):
        raise ValueError('PRODUCT_INPUT_INVALID: scalar input must be text')
    return str(value or '').strip()


def normalize_bound_inputs(params: dict[str, Any]) -> list[str]:
    """Normalize known scalar aliases in the execution projection, never mutate input resources."""
    if not publication_enabled(params) or params.get('step_id') != 'route_product_stage':
        return []
    inputs = dict(params.get('remote_inputs') or {})
    aliases = {
        'execution_depth': {
            '': 'auto', 'auto': 'auto', 'standard': 'auto', 'default': 'auto',
            '自动判断': 'auto', '由当前阶段判断': 'auto',
            'light': 'light', '轻量': 'light', '轻量模式': 'light', '精简': 'light', '复用现有': 'light',
            'minimum-fill': 'minimum-fill', '最小补齐': 'minimum-fill', '最小补齐模式': 'minimum-fill',
            '补齐': 'minimum-fill', 'full': 'full', '完整': 'full', '完整模式': 'full', '完整执行': 'full',
        },
        'reference_sample_choice': {
            '': '', 'default': '', 'none': 'none-confirmed', 'none-confirmed': 'none-confirmed',
            '默认结构': 'none-confirmed', '使用默认结构': 'none-confirmed', '无样例': 'none-confirmed',
            '不使用参考样例': 'none-confirmed', '不提供参考样例': 'none-confirmed', '不使用样例': 'none-confirmed',
            'provided': 'provided', '已提供': 'provided', '有样例': 'provided',
            'not-required': 'not-required', '不需要': 'not-required', '不适用': 'not-required',
        },
    }
    changed = []
    for field, values in aliases.items():
        if field not in inputs:
            continue
        raw = _scalar(inputs[field]).lower()
        if raw not in values:
            raise ValueError(f'PRODUCT_INPUT_INVALID: {field} has an unsupported value')
        normalized = values[raw]
        if field == 'reference_sample_choice' and normalized == '':
            normalized = 'provided' if inputs.get('reference_sample') else 'none-confirmed'
        if normalized != inputs[field]:
            inputs[field] = normalized
            changed.append(field)
    if 'word_target' in inputs:
        raw = _scalar(inputs['word_target']).replace(',', '')
        if raw.lower() in ('default', 'stage-specific', 'not-applicable', '不适用'):
            inputs['word_target'] = ''
            changed.append('word_target')
        elif (inputs.get('requested_stage') in WRITER_STAGES and raw
              and (not re.search(r'\d+', raw) or int(re.search(r'\d+', raw)[0]) < 300)):
            raise ValueError('PRODUCT_INPUT_INVALID: word_target must be at least 300')
    params['remote_inputs'] = inputs
    return changed


def tool_failure(event: dict[str, Any], names: frozenset[str]) -> str:
    """Recognize the upstream structured error envelope, not only plain exception strings."""
    if event.get('tag') != 'tool_results':
        return ''
    for result in event.get('tool_results') or []:
        name = result.get('name') if isinstance(result, dict) else None
        if name not in names:
            continue
        payload = result.get('result', result.get('content'))
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                return f'PRODUCT_TOOL_FAILED: {name}: {payload[:500]}'
        if not isinstance(payload, dict) or payload.get('ok') is False or payload.get('error'):
            return f'PRODUCT_TOOL_FAILED: {name}: {str(payload)[:500]}'
    return ''


async def bounded_frames(frames: AsyncIterator[str], params: dict[str, Any], stop) -> AsyncIterator[str]:
    policy = policy_for(params)
    if policy is None:
        async for frame in frames:
            yield frame
        return
    try:
        async with asyncio.timeout(policy.timeout):
            async for frame in frames:
                yield frame
    except TimeoutError as exc:
        stop()
        raise RuntimeError(f'PRODUCT_STEP_TIMEOUT: {params.get("step_id")} exceeded {policy.timeout}s') from exc
    finally:
        await frames.aclose()


def execution_workspace(spec: dict[str, Any], metadata: dict[str, Any]) -> str:
    """Project product execution into the existing conversation file area.

    Core's task workspace remains the fallback for pre-upgrade resumptions. New
    tasks use a stable task-scoped directory, so retries retain paths while other
    stages/projects in the conversation cannot overwrite their files.
    """
    from hashlib import sha256
    from pathlib import Path

    original = str(spec['workspace_path'])
    if not publication_enabled(spec.get('params') or {}):
        return original
    from lazymind.chat.engine.tools.conversation_workspace import chat_agent_workspace

    owner = str(metadata.get('owner_user_id') or '').strip()
    conversation = str(metadata.get('conversation_id') or '').strip()
    task = str(metadata.get('task_id') or '').strip()
    if not all((owner, conversation, task)):
        raise ValueError('Product shared workspace requires trusted conversation and task scope')
    shared = Path(chat_agent_workspace(owner, conversation)).resolve()
    target = shared / 'product-workflow' / sha256(task.encode()).hexdigest()[:32]
    if not target.resolve().is_relative_to(shared):
        raise ValueError('Product workspace must stay inside the conversation workspace')
    if spec.get('steps') and not target.is_dir():
        return original
    return str(target)
