from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import lazyllm
import pytest

from lazymind.chat.engine.tools import temporary_retrieval_session as session


@pytest.fixture
def session_state(monkeypatch, tmp_path):
    available = {'embed': False, 'checks': 0}

    def model_available(role):
        assert role == 'embed_main'
        available['checks'] += 1
        return available['embed']

    monkeypatch.setattr(session, 'is_model_role_available', model_available)
    monkeypatch.setattr(session, 'workspace_for_request', lambda user_id, conversation_id:
                        str(tmp_path / user_id / conversation_id))
    return available


def test_chat_mode_is_pinned_before_first_upload_and_users_are_isolated(session_state):
    first = {'user_id': 'alice', 'conversation_id': 'chat-1', 'files': []}
    assert session.initialize_temporary_retrieval(first) is False
    session_state['embed'] = True
    assert session.initialize_temporary_retrieval(first) is False
    assert session.initialize_temporary_retrieval({**first, 'conversation_id': 'chat-2'}) is True
    assert session.initialize_temporary_retrieval({**first, 'user_id': 'bob'}) is True
    session_state['embed'] = False
    assert session.initialize_temporary_retrieval({**first, 'conversation_id': 'chat-2'}) is True
    assert session_state['checks'] == 3


def test_initialization_is_single_choice_across_concurrent_requests(session_state):
    config = {'user_id': 'alice', 'conversation_id': 'concurrent'}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(session.initialize_temporary_retrieval, [config] * 16))
    assert results == [False] * 16
    assert session_state['checks'] == 1


def test_missing_conversation_never_uses_a_shared_fallback(session_state):
    with pytest.raises(RuntimeError, match='conversation_id'):
        session.initialize_temporary_retrieval({'user_id': 'alice'})


def test_conversation_cache_eviction_does_not_change_mode(monkeypatch, session_state):
    from lazymind.chat.engine.tools.algo import search_temp

    monkeypatch.setattr(search_temp, '_session_retrievers', search_temp.OrderedDict())
    monkeypatch.setattr(search_temp, '_MAX_CACHED_CONVERSATIONS', 1)
    built = []

    def make(*, use_embed):
        result = SimpleNamespace(use_embed=use_embed)
        built.append(result)
        return result

    monkeypatch.setattr(search_temp, '_make_retriever', make)
    lazyllm.globals._init_sid('temporary-retrieval-cache-test')
    try:
        config = {'user_id': 'alice', 'conversation_id': 'first'}
        lazyllm.globals['agentic_config'] = config
        first = search_temp._ensure_retriever()
        session_state['embed'] = True
        assert search_temp._ensure_retriever() is first
        lazyllm.globals['agentic_config'] = {**config, 'conversation_id': 'second'}
        second = search_temp._ensure_retriever()
        assert second.use_embed is True
        lazyllm.globals['agentic_config'] = config
        restored = search_temp._ensure_retriever()
        assert restored is not first
        assert restored.use_embed is False
        assert [item.use_embed for item in built] == [False, True, False]
    finally:
        lazyllm.globals.clear()
