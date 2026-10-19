"""Restricted tools for editing a Workflow deck through an ordinary SubAgent."""
from typing import Any, Dict, List, Optional

from lazyllm.tools import fc_register
from lazyllm.tools.agent import ToolExecutionError

from .context import require_context
from . import tools


def _session() -> str:
    ctx = require_context()
    session = str(ctx.params.get('_pptx_edit_session_id') or '')
    if ctx.agent_type != 'pptx_edit' or not session:
        raise ToolExecutionError('A bound PPTX editing task is required')
    return session


@fc_register(host_file='NONE')
def inspect_current_pptx() -> Dict[str, Any]:
    """Read current PPTX text slots, source_sha256 and all speaker notes before editing."""
    return tools.edit_presentation('native_pptx', 'inspect_content', workflow_session_id=_session())


@fc_register(host_file='NONE')
def read_pptx_edit_material(slot: str = 'material_summary') -> Dict[str, Any]:
    """Read existing evidence only: material_summary or requirement_analysis; no research."""
    if slot not in {'material_summary', 'requirement_analysis'}:
        raise ToolExecutionError('Only saved material_summary and requirement_analysis may be read')
    rows = tools._public_workflow_artifacts(_session(), slot)
    rows = [row for row in rows if row.get('selected') and row.get('validity') == 'effective'
            and not row.get('deleted')]
    return {'artifacts': [tools._workflow_client().read_artifact(row['id']).result for row in rows]}


@fc_register(host_file='NONE')
def publish_pptx_edit(source_sha256: str,
                      text_edits: Optional[List[Dict[str, Any]]] = None,
                      speaker_notes: Optional[List[Dict[str, Any]]] = None,
                      require_all_notes: bool = False) -> Dict[str, Any]:
    """Publish sparse text edits and/or notes once, then finish the task.

    Use the inspected source_sha256. text_edits: [{id,expected_text,text}].
    speaker_notes: [{page,text}] with 1-based pages. Set require_all_notes=true
    for every-page speeches. Preserve all unspecified text, formatting and notes.
    """
    session = _session()
    ctx = require_context()
    if ctx.local_artifacts(['pptx_edit_receipt']):
        raise ToolExecutionError('This task already published its edit; do not publish twice')
    result = tools.edit_presentation(
        'native_pptx', 'edit_content', source_sha256=source_sha256,
        text_edits=text_edits, speaker_notes=speaker_notes,
        require_all_notes=require_all_notes, workflow_session_id=session,
    )
    if result.get('status') != 'ok' or not result.get('workflow_artifact'):
        raise ToolExecutionError('PPTX publication did not return a successful artifact revision')
    # This receipt satisfies the SubAgent completion contract. The file itself
    # remains authoritative in the Workflow slot; never create a parallel deck.
    value = {'data': result['workflow_artifact']}
    seq = ctx.next_artifact_seq('pptx_edit_receipt')
    ctx.record_local_artifact('pptx_edit_receipt', 'json', value, seq)
    ctx.emit({'type': 'artifact', 'slot': 'pptx_edit_receipt',
              'content_type': 'json', 'value': value, 'seq': seq})
    return result


def edit_tools():
    return [inspect_current_pptx, read_pptx_edit_material, publish_pptx_edit]
