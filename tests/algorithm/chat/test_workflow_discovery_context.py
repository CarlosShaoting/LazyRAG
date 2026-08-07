import json

import lazyllm

from lazymind.chat.workflow.workflow_manager import (
    build_workflow_discovery_context,
    resolve_workflow_injection,
)


def _catalog():
    return [
        {
            'workflow_ref': 'builtin:image-workflow',
            'workflow_id': 'image-workflow',
            'name': 'AI Image Generation',
            'description': 'Generate, find, or edit images.',
            'when_to_use': 'Use for complex image requests; avoid simple one-shot images.',
            'revision_id': 'rev-image',
        },
        {
            'workflow_ref': 'builtin:test-workflow',
            'workflow_id': 'test-workflow',
            'name': 'Workflow Runtime End-to-End Self-Test',
            'description': 'Smoke-test the Workflow runtime.',
            'when_to_use': 'Use only when the user explicitly asks to test Workflow runtime.',
            'revision_id': 'rev-test',
        },
    ]


def test_workflow_discovery_context_renders_catalog_for_routing():
    discovery = build_workflow_discovery_context(
        _catalog(),
        current_query='找几张参考图再生成一张产品海报',
    )

    assert [item['tool_name'] for item in discovery.activations] == [
        'trigger_image_workflow',
        'trigger_test_workflow',
    ]
    assert 'Available Workflow Catalog' in discovery.prompt
    assert '找几张参考图再生成一张产品海报' in discovery.prompt
    payload = json.loads(discovery.prompt[discovery.prompt.index('{'):])
    assert payload['workflows'][0] == {
        'workflow_ref': 'builtin:image-workflow',
        'workflow_id': 'image-workflow',
        'name': 'AI Image Generation',
        'description': 'Generate, find, or edit images.',
        'when_to_use': 'Use for complex image requests; avoid simple one-shot images.',
        'trigger_tool': 'trigger_image_workflow',
    }


def test_non_mentioned_workflows_are_available_for_chatagent_routing():
    previous = lazyllm.globals.get('agentic_config')
    lazyllm.globals['agentic_config'] = {'enable_workflow': True}
    try:
        contribution = resolve_workflow_injection(
            None,
            conversation_id='conversation-1',
            current_query='找几张参考图再生成一张产品海报',
            workflow_catalog=_catalog(),
            allowed_workflow_refs=[],
            workflow_activations=[],
        )
    finally:
        if previous is None:
            lazyllm.globals.pop('agentic_config', None)
        else:
            lazyllm.globals['agentic_config'] = previous

    tool_names = {getattr(tool, '__name__', '') for tool in contribution.tools}
    assert 'trigger_image_workflow' in tool_names
    assert 'trigger_test_workflow' in tool_names
    assert 'advance_step' in tool_names
    assert 'advance_step_and_hand_off' in tool_names
    assert 'list_workflows' in tool_names
    assert 'Available Workflow Catalog' in contribution.runtime_context
    assert 'Use for complex image requests' in contribution.runtime_context
