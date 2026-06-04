from __future__ import annotations

import os
from functools import wraps
from typing import Any, Dict, Optional

import lazyllm
from lazyllm import AutoModel, fc_register
from lazyllm.components.formatter import encode_query_with_filepaths

from chat.components.process.query_image_rewriter import (
    QueryImageRewriter,
    extract_text_from_model_output,
)
from chat.utils.load_config import get_config_path
from chat.utils.static_file_url import resolve_local_image_path


_VISION_EXTRACT_DEFAULT_INSTRUCTION = (
    'Describe the image in plain text. Include visible text, objects, charts, and any '
    'details that would help answer follow-up questions about this image.'
)


def _tool_failure(tool_name: str, exc: Exception) -> Dict[str, Any]:
    return {
        'success': False,
        'reason': f'{tool_name} failed: {exc}',
        'error': str(exc),
        'error_type': type(exc).__name__,
    }


def _handle_tool_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return _tool_failure(func.__name__, exc)

    return wrapper


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def vision_extractor(url: str, instruction: Optional[str] = None) -> Dict[str, Any]:
    """Extract a text description from an image reachable at the given URL.

    Uses the configured VLM endpoint (role ``vlm`` in runtime_models)
    with the same multimodal encoding as ``QueryImageRewriter`` (file paths / URLs
    embedded in the prompt for the VLM).

    Args:
        url: Local filesystem path under the upload root, or a ``/static-files/``
            signed path from kb results (resolved to the local file automatically).
        instruction: Optional focus for what to extract; defaults to a general
            description prompt.

    Returns:
        A dict with ``success``, and on success ``description`` (plain text).
    """
    raw = str(url or '').strip()
    if not raw:
        raise ValueError('url is required')

    local_path = resolve_local_image_path(raw)
    if not local_path or not os.path.isfile(local_path):
        raise ValueError(f'image file not found: {local_path or raw}')

    prompt_instruction = (
        str(instruction).strip() if instruction else _VISION_EXTRACT_DEFAULT_INSTRUCTION
    )
    encoded_query = encode_query_with_filepaths(prompt_instruction, [local_path])

    agentic_config = lazyllm.globals.get('agentic_config') or {}
    priority = int(agentic_config.get('priority', 0) or 0)

    vlm = AutoModel(model='vlm', config=get_config_path())
    out = vlm(
        encoded_query,
        stream_output=False,
        llm_chat_history=[],
        lazyllm_files=None,
        priority=priority,
    )
    text = extract_text_from_model_output(out)
    return {'success': True, 'description': text, 'url': local_path}


def _agentic_priority() -> int:
    agentic_config = lazyllm.globals.get('agentic_config') or {}
    return int(agentic_config.get('priority', 0) or 0)


def _resolve_attached_image_paths(urls: Optional[list[str]] = None) -> list[str]:
    agentic_config = lazyllm.globals.get('agentic_config') or {}
    candidates: list[str] = []
    if urls:
        candidates.extend(str(item).strip() for item in urls if str(item).strip())
    else:
        raw = agentic_config.get('image_files') or []
        if isinstance(raw, list):
            candidates.extend(str(item).strip() for item in raw if str(item).strip())
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        local_path = resolve_local_image_path(raw)
        if not local_path or not os.path.isfile(local_path):
            raise ValueError(f'attached image file not found: {local_path or raw}')
        if local_path not in seen:
            seen.add(local_path)
            resolved.append(local_path)
    if not resolved:
        raise ValueError('no attached images found for this session')
    return resolved


def _description_from_rewriter_output(
    original_query: str,
    rewriter_payload: dict[str, Any],
) -> str:
    merged = str(rewriter_payload.get('query') or '').strip()
    marker = '\nImage context:'
    if marker in merged:
        return merged.split(marker, 1)[1].strip()
    if merged and merged != original_query.strip():
        return merged
    return ''


@fc_register('tool', execute_in_sandbox=False)
@_handle_tool_errors
def describe_attached_images(
    query: str = '',
    urls: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Describe user-attached image(s) with VLM, focused on the current question.

    Call this when the user uploaded images in the current turn and you need
    textual understanding (objects, text in image, layout) before answering or
    searching. For image generation use ``image_generator``; for editing an
    attached image use ``image_editor`` with ``url`` set to a listed path.

    Args:
        query: The user's question; focuses the description. Optional when the
            request is only to describe the attachment(s).
        urls: Optional image paths or signed ``/static-files/`` URLs. When
            omitted, uses ``agentic_config['image_files']`` for this request.

    Returns:
        On success: ``success``, ``description``, ``paths``, and ``query`` echo.
    """
    image_paths = _resolve_attached_image_paths(urls)
    focus_query = str(query or '').strip() or 'Describe the attached image(s).'
    payload: Dict[str, Any] = {
        'query': focus_query,
        'image_files': image_paths,
        'priority': _agentic_priority(),
    }
    rewriter = QueryImageRewriter(
        vlm=AutoModel(model='vlm', config=get_config_path()),
    )
    out = rewriter.forward(payload)
    if not isinstance(out, dict):
        raise ValueError('unexpected VLM rewriter output')
    description = _description_from_rewriter_output(focus_query, out)
    if not description:
        raise ValueError('VLM returned an empty image description')
    return {
        'success': True,
        'description': description,
        'paths': image_paths,
        'query': focus_query,
    }
