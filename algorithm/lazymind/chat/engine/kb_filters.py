"""Shared helpers for propagating knowledge-base filters into agent / plugin tasks."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

LOG = logging.getLogger(__name__)


def _extract_kb_ids(search_config: Dict[str, Any]) -> List[str]:
    kb_ids: List[str] = []
    raw = search_config.get('kb_id')
    if isinstance(raw, str) and raw.strip():
        kb_ids.append(raw.strip())
    raw_list = search_config.get('kb_ids')
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, str) and item.strip():
                kb_ids.append(item.strip())
    return kb_ids


def enrich_filters_from_conversation(conversation_id: str, filters: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill filters.kb_id from conversation.search_config when task params omit them."""
    if filters.get('kb_id'):
        return filters
    conv_id = (conversation_id or '').strip()
    if not conv_id:
        return filters
    try:
        import httpx
        from lazymind.config import config as _cfg

        core_url = str(_cfg['core_api_url']).rstrip('/')
        resp = httpx.get(f'{core_url}/conversations/{conv_id}', timeout=5.0)
        resp.raise_for_status()
        body = resp.json()
        data = body.get('data') if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return filters
        sc = data.get('search_config') or {}
        if not isinstance(sc, dict):
            return filters
        kb_ids = _extract_kb_ids(sc)
        if not kb_ids:
            return filters
        merged = dict(filters)
        merged['kb_id'] = kb_ids[0]
        if len(kb_ids) > 1:
            merged['kb_ids'] = kb_ids
        LOG.info('[kb_filters] backfilled kb_id=%r from conversation %s', kb_ids[0], conv_id)
        return merged
    except Exception as exc:
        LOG.warning('[kb_filters] failed to load conversation %s: %s', conv_id, exc)
        return filters
