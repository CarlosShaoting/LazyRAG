from lazymind.chat.service.chat_service import (
    _should_register_subagent_tools,
    _workflow_collects_knowledge_internally,
    _workflow_turn_is_bound,
)


def test_selected_ppt_workflow_owns_knowledge_collection():
    assert _workflow_collects_knowledge_internally(
        None, ['builtin:ppt-workflow'],
    )


def test_active_ppt_workflow_owns_knowledge_collection():
    assert _workflow_collects_knowledge_internally(
        {'workflow_id': 'ppt-workflow'}, [],
    )


def test_unrelated_workflow_keeps_global_knowledge_tools():
    assert not _workflow_collects_knowledge_internally(
        {'workflow_ref': 'builtin:image-workflow'},
        ['builtin:image-workflow'],
    )


def test_completed_workflow_session_owns_mutation_tools():
    context = {'session_id': 'session-1', 'workflow_ref': 'builtin:ppt-workflow'}

    assert _workflow_turn_is_bound(context, [])
    assert not _should_register_subagent_tools(True, [], context)


def test_explicit_workflow_selection_owns_mutation_tools_before_session_exists():
    refs = ['builtin:ppt-workflow']

    assert _workflow_turn_is_bound(None, refs)
    assert not _should_register_subagent_tools(True, refs, None)


def test_plain_chat_keeps_generic_subagent_tools():
    assert not _workflow_turn_is_bound(None, [])
    assert _should_register_subagent_tools(True, [], None)
