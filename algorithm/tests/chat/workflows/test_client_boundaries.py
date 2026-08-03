from pathlib import Path


def test_runtime_table_queries_are_isolated_to_persistence_adapter():
    chat_root = Path(__file__).parents[3] / 'lazymind' / 'chat'
    violations = []
    table_tokens = ('workflow_sessions', 'workflow_session_steps', 'workflow_slot_revisions',
                    'workflow_attempt_input_bindings', 'workflow_input_bindings')
    for path in chat_root.rglob('*.py'):
        if path.name == 'persistence_compat.py':
            continue
        text = path.read_text()
        if any(token in text for token in table_tokens) and any(
                sql in text.upper() for sql in ('SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ')):
            violations.append(str(path.relative_to(chat_root)))
    assert violations == []


def test_workflow_http_payloads_live_in_client_or_compatibility_adapter():
    chat_root = Path(__file__).parents[3] / 'lazymind' / 'chat'
    violations = []
    for path in chat_root.rglob('*.py'):
        if path.name in {'client.py', 'file_adapter.py', 'compat.py'}:
            continue
        text = path.read_text()
        if 'httpx.' in text and '/workflow-' in text:
            violations.append(str(path.relative_to(chat_root)))
    assert violations == []
