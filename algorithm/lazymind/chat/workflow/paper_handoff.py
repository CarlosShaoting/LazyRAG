"""Bind an authorized paper task to a package-declared hidden input at launch."""
import json


def resolve_paper_handoff(client, conversation_id, runtime_policy):
    policy = (runtime_policy or {}).get('paper_handoff') or {}
    material = policy.get('input')
    if not material or not conversation_id:
        return {}, []
    response = client.transport.request(
        'GET', client.base_url + '/academic/chat-context', headers=client._headers(),
        params={'conversation_id': conversation_id}, timeout=30,
    )
    # Ordinary PPT chats have no paper handoff. All authorization/server errors
    # other than a missing task remain errors; never fall back to invented input.
    if response.status_code == 404:
        return {}, []
    response.raise_for_status()
    context = response.json()
    context = context.get('data', context)
    if context.get('kind') != policy.get('kind'):
        return {}, []
    papers = (context.get('input') or {}).get('papers')
    if not context.get('handoff_id') or not isinstance(papers, list) or not papers:
        raise ValueError('Paper handoff has no selected papers')
    if any(not isinstance(paper, dict) or not paper.get('paper_id') for paper in papers):
        raise ValueError('Paper handoff contains an invalid PaperRef')
    return {material: json.dumps(context, ensure_ascii=False)}, list(policy.get('satisfies') or [])
