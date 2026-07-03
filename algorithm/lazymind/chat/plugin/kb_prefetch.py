"""Knowledge-base prefetch for plugins that opt in via plugin.yaml ``kb_prefetch``.

Runs ``kb_search`` in the main ChatAgent context (not inside SubAgent workers),
caches results per plugin session, and injects a formatted block into
``runtime_instruction`` for every step trigger.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from lazymind.chat.plugin import plugin_loader

logger = logging.getLogger(__name__)

_PREFETCH_HEADER = '## Knowledge base prefetch (authoritative)'
# session_id -> (cache_key, prefetch_block)
_PREFETCH_CACHE: Dict[str, Tuple[str, str]] = {}


def _cache_key(kb_id: str, query: str) -> str:
    return f'{kb_id}:{query.strip()}'


def _format_kb_items(items: List[Dict[str, Any]]) -> str:
    lines = [
        _PREFETCH_HEADER,
        '',
        'The following knowledge-base hits were retrieved in the main chat context.',
        'Do NOT call kb_search in plugin steps — use the findings below.',
        '',
    ]
    if not items:
        lines.append('(No knowledge-base hits returned for this query.)')
        return '\n'.join(lines)

    for idx, item in enumerate(items, start=1):
        group = str(item.get('group') or 'block')
        file_name = str(item.get('file_name') or 'unknown')
        lines.append(f'### Hit {idx} ({group}) — {file_name}')
        if group == 'image':
            meta = item.get('metadata') or {}
            url = meta.get('image_url') or item.get('local_path') or ''
            if url:
                lines.append(f'- image_url: {url}')
        text = str(item.get('text') or '').strip()
        if text:
            lines.append(text)
        lines.append('')

    lines.append('Use the text hits in your step outputs as appropriate for the step prompt.')
    return '\n'.join(lines)


def _run_kb_search(query: str, filters: Dict[str, Any], user_id: str) -> str:
    from lazymind.chat.engine.tools.algo import search_kb
    from lazymind.chat.engine.tools.kb import (
        _DEFAULT_IMAGE_TOPK,
        _DEFAULT_K_MAX,
        _DEFAULT_RERANK_TOPK,
        _DEFAULT_RETRIEVER_TOPK,
        _ensure_kb_search_runtime,
        _serialize_kb_result,
    )

    kb_id = str(filters.get('kb_id') or '').strip()
    if not kb_id or not query.strip():
        return ''

    try:
        retrievers, reranker, image_retriever = _ensure_kb_search_runtime()
        payload = {
            'query': query.strip(),
            'filters': filters,
            'user_id': user_id,
        }
        result = search_kb(
            payload,
            retrievers=retrievers,
            reranker=reranker,
            image_retriever=image_retriever,
            retriever_topk=_DEFAULT_RETRIEVER_TOPK,
            rerank_topk=_DEFAULT_RERANK_TOPK,
            k_max=_DEFAULT_K_MAX,
            image_topk=_DEFAULT_IMAGE_TOPK,
        )
        serialized = _serialize_kb_result(result)
    except Exception:
        logger.exception('[KB_PREFETCH] kb_search failed kb_id=%s', kb_id)
        return _format_kb_items([])

    items: List[Dict[str, Any]] = []
    if isinstance(serialized, dict):
        nested = serialized.get('items') or []
        if isinstance(nested, list):
            items = [x for x in nested if isinstance(x, dict)]
    elif isinstance(serialized, list):
        items = [x for x in serialized if isinstance(x, dict)]

    return _format_kb_items(items)


def prefetch_kb_for_plugin(
    *,
    plugin_id: str,
    session_id: str,
    query: str,
    filters: Dict[str, Any],
    user_id: str,
    force: bool = False,
) -> str:
    """Run (or return cached) KB prefetch for an opt-in plugin session."""
    if not plugin_loader.kb_prefetch_enabled(plugin_id):
        return ''
    kb_id = str(filters.get('kb_id') or '').strip()
    if not kb_id or not session_id:
        return ''

    key = _cache_key(kb_id, query)
    cached = _PREFETCH_CACHE.get(session_id)
    if not force and cached and cached[0] == key:
        return cached[1]

    block = _run_kb_search(query, filters, user_id)
    if block:
        _PREFETCH_CACHE[session_id] = (key, block)
    elif session_id in _PREFETCH_CACHE:
        del _PREFETCH_CACHE[session_id]
    return block


def inject_plugin_kb_prefetch(
    *,
    plugin_id: str,
    session_id: str,
    query: str,
    filters: Dict[str, Any],
    user_id: str,
    runtime_instruction: str,
    refresh: bool = False,
) -> str:
    """Append cached or freshly prefetched KB block to *runtime_instruction*."""
    base = runtime_instruction or ''
    if _PREFETCH_HEADER in base:
        return base
    if not plugin_loader.kb_prefetch_enabled(plugin_id):
        return base

    block = prefetch_kb_for_plugin(
        plugin_id=plugin_id,
        session_id=session_id,
        query=query,
        filters=filters,
        user_id=user_id,
        force=refresh,
    )
    if not block:
        return base
    sep = '\n\n' if base.strip() else ''
    return base + sep + block


def clear_plugin_kb_prefetch_cache(session_id: Optional[str] = None) -> None:
    """Drop prefetch cache for one session or all sessions (tests)."""
    if session_id:
        _PREFETCH_CACHE.pop(session_id, None)
    else:
        _PREFETCH_CACHE.clear()
