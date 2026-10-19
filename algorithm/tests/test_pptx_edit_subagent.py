from unittest.mock import MagicMock

import pytest
from lazyllm.tools.agent import ToolExecutionError

from lazymind.chat.engine.subagent import pptx_edit
from lazymind.chat.engine.subagent.context import SubAgentContext
from lazymind.chat.engine.subagent.runner import _resolve_runtime_tools, _build_subagent_tools
from lazymind.chat.engine.subagent.tools import artifact_is_deliverable


@pytest.fixture
def context(monkeypatch):
    ctx = SubAgentContext('task', 'conversation', 'pptx_edit', 'edit notes',
                          {'_pptx_edit_session_id': 'session',
                           'output_slot_types': {'pptx_edit_receipt': 'json'}},
                          '/tmp', [], ['pptx_edit_receipt'], None, MagicMock())
    monkeypatch.setattr(pptx_edit, 'require_context', lambda: ctx)
    return ctx


def test_scoped_worker_tool_surface():
    runtime = _resolve_runtime_tools(['web_search', 'run_script'], {'_pptx_edit_session_id': 'session'})
    tools = _build_subagent_tools(runtime, tools_only=True)
    assert [tool.__name__ for tool in tools] == [
        'inspect_current_pptx', 'read_pptx_edit_material', 'publish_pptx_edit']


def test_publish_receipt_only_after_success(context, monkeypatch):
    edit = MagicMock(return_value={'status': 'ok', 'workflow_artifact': {'id': 'revision-2'}})
    monkeypatch.setattr(pptx_edit.tools, 'edit_presentation', edit)
    pptx_edit.inspect_current_pptx()
    assert edit.call_args.kwargs['workflow_session_id'] == 'session'
    assert not context.local_artifacts()
    notes = [{'page': 1, 'text': '详细讲稿'}]
    pptx_edit.publish_pptx_edit('hash', speaker_notes=notes, require_all_notes=True)
    assert edit.call_args.kwargs['speaker_notes'] == notes
    assert edit.call_args.kwargs['require_all_notes'] is True
    receipt = context.local_artifacts()[0]
    assert artifact_is_deliverable(context, receipt)
    assert receipt['value']['data']['id'] == 'revision-2'
    context.emit.assert_called_once()
    with pytest.raises(ToolExecutionError):
        pptx_edit.publish_pptx_edit('hash', speaker_notes=notes)


def test_failed_publish_cannot_complete_task(context, monkeypatch):
    monkeypatch.setattr(pptx_edit.tools, 'edit_presentation', lambda *a, **kw: {'status': 'error'})
    with pytest.raises(ToolExecutionError):
        pptx_edit.publish_pptx_edit('hash')
    assert context.local_artifacts() == []
    context.emit.assert_not_called()


def test_material_read_is_restricted(context):
    with pytest.raises(ToolExecutionError):
        pptx_edit.read_pptx_edit_material('native_pptx')
    context.agent_type = 'research'
    with pytest.raises(ToolExecutionError):
        pptx_edit.inspect_current_pptx()
