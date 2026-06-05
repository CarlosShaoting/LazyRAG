from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import lazyllm
from lazyllm import AutoModel, fc_register
from lazyllm.components.formatter import encode_query_with_filepaths

from lazymind.chat.engine.prompts import VISION_EXTRACT_DEFAULT_INSTRUCTION
from lazymind.chat.engine.tools.infra import handle_tool_errors, tool_success
from lazymind.chat.service.utils import resolve_local_image_path


@handle_tool_errors
def vision_extractor(url: str, instruction: Optional[str] = None) -> Dict[str, Any]:
    """Extract a text description from an image reachable at the given URL.

    Uses the configured VLM endpoint (role ``vlm`` in runtime_models)
    with LazyLLM multimodal file-path encoding.

    Args:
        url: Local filesystem path under the upload root, or a ``/static-files/``
            signed path from kb results (resolved to the local file automatically).
        instruction: Optional focus for what to extract; defaults to a general
            description prompt.

    Returns:
        A unified tool payload whose ``result`` contains the extracted
        description and resolved local path.
    """
    raw = str(url or '').strip()
    if not raw:
        raise ValueError('url is required')

    local_path = resolve_local_image_path(raw)
    if not local_path or not os.path.isfile(local_path):
        raise ValueError(f'image file not found: {local_path or raw}')

    prompt_instruction = (
        str(instruction).strip() if instruction else VISION_EXTRACT_DEFAULT_INSTRUCTION
    )
    encoded_query = encode_query_with_filepaths(prompt_instruction, [local_path])

    agentic_config = lazyllm.globals['agentic_config']
    priority = int(agentic_config.get('priority', 0) or 0)

    vlm = AutoModel(model='vlm')
    out = vlm(
        encoded_query,
        stream_output=False,
        llm_chat_history=[],
        lazyllm_files=None,
        priority=priority,
    )
    text = str(out).strip()
    return tool_success('vision_extractor', {'description': text, 'url': local_path})


def _resolve_attached_image_paths(urls: Optional[List[str]] = None) -> List[str]:
    agentic_config = lazyllm.globals.get('agentic_config') or {}
    candidates: List[str] = []
    if urls:
        candidates.extend(str(item).strip() for item in urls if str(item).strip())
    else:
        raw = agentic_config.get('image_files') or []
        if isinstance(raw, list):
            candidates.extend(str(item).strip() for item in raw if str(item).strip())
    resolved: List[str] = []
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


@fc_register('tool', execute_in_sandbox=False)
@handle_tool_errors
def describe_attached_images(
    query: str = '',
    urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Describe user-attached image(s) with VLM, focused on the current question.

    Call this when the user uploaded images in the current turn and you need
    textual understanding before answering or searching. For image generation
    use ``image_generator``; for editing an attached image use ``image_editor``.

    Args:
        query: The user's question; optional when only describing attachments.
        urls: Optional image paths or signed ``/static-files/`` URLs. When
            omitted, uses ``agentic_config['image_files']`` for this request.

    Returns:
        On success: ``description``, ``paths``, and ``query`` echo in ``result``.
    """
    image_paths = _resolve_attached_image_paths(urls)
    focus_query = str(query or '').strip() or 'Describe the attached image(s).'
    encoded_query = encode_query_with_filepaths(focus_query, image_paths)

    agentic_config = lazyllm.globals.get('agentic_config') or {}
    priority = int(agentic_config.get('priority', 0) or 0)

    vlm = AutoModel(model='vlm')
    out = vlm(
        encoded_query,
        stream_output=False,
        llm_chat_history=[],
        lazyllm_files=None,
        priority=priority,
    )
    description = str(out).strip()
    if not description:
        raise ValueError('VLM returned an empty image description')
    return tool_success(
        'describe_attached_images',
        {'description': description, 'paths': image_paths, 'query': focus_query},
    )
