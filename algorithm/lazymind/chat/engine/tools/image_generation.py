from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import lazyllm
from lazyllm import AutoModel, fc_register
from lazyllm.components.formatter import decode_query_with_filepaths

from lazymind.chat.engine.tools.infra import handle_tool_errors
from lazymind.chat.service.utils.markdown_images import register_generated_image_urls
from lazymind.chat.service.utils.static_file_url import (
    _upload_root,
    basename_from_path,
    resolve_local_image_path,
    static_file_url_from_any,
)
from lazymind.model_config import get_config_path

_DEFAULT_IMAGE_SIZE = '1024x1024'
_DEFAULT_BATCH_SIZE = 1
_IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
_UPLOAD_SUBDIR = 'ai_generated'


def _agentic_priority() -> int:
    agentic_config = lazyllm.globals.get('agentic_config') or {}
    return int(agentic_config.get('priority', 0) or 0)


def _parse_generated_files(result: Any) -> List[str]:
    if not isinstance(result, str):
        raise ValueError(f'unexpected model output type: {type(result).__name__}')
    decoded = decode_query_with_filepaths(result)
    if not isinstance(decoded, dict):
        raise ValueError('model output is not a lazyllm-query payload')
    files = decoded.get('files') or []
    if not isinstance(files, list) or not files:
        raise ValueError('model returned no generated image files')
    paths: List[str] = []
    for item in files:
        path = str(item or '').strip()
        if not path:
            continue
        if not os.path.isfile(path):
            raise ValueError(f'generated image file not found: {path}')
        paths.append(path)
    if not paths:
        raise ValueError('model returned no valid image file paths')
    return paths


def _relocate_generated_image_to_upload(source_path: str) -> str:
    root = Path(_upload_root()).resolve()
    dest_dir = root / _UPLOAD_SUBDIR
    src = Path(source_path).resolve()
    if not src.is_file():
        raise ValueError(f'generated image file not found: {source_path}')
    try:
        src.relative_to(dest_dir.resolve())
        return str(src)
    except ValueError:
        pass

    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix if src.suffix.lower() in _IMAGE_SUFFIXES else '.png'
    dest = dest_dir / f'{uuid.uuid4().hex}{suffix}'
    shutil.move(str(src), str(dest))
    return str(dest)


def _relocate_generated_images(paths: List[str]) -> List[str]:
    return [_relocate_generated_image_to_upload(path) for path in paths]


def _build_image_payload(local_path: str, *, label: str) -> Dict[str, str]:
    signed = static_file_url_from_any(local_path)
    payload = {'local_path': local_path}
    if signed:
        payload['image_url'] = signed
        file_label = label or basename_from_path(signed) or 'generated image'
        payload['image_markdown'] = f'![{file_label}]({signed})'
    return payload


def _run_image_model(
    role: str,
    prompt: str,
    *,
    files: Optional[List[str]] = None,
    image_size: str = _DEFAULT_IMAGE_SIZE,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    text = str(prompt or '').strip()
    if not text:
        raise ValueError('prompt is required')

    size = str(image_size or _DEFAULT_IMAGE_SIZE).strip() or _DEFAULT_IMAGE_SIZE
    count = int(batch_size or _DEFAULT_BATCH_SIZE)
    if count < 1:
        raise ValueError('batch_size must be at least 1')

    call_kwargs: Dict[str, Any] = {
        'image_size': size,
        'batch_size': count,
        'priority': _agentic_priority(),
    }
    if files:
        call_kwargs['files'] = files

    model = AutoModel(model=role, config=get_config_path())
    raw = model(text, stream_output=False, **call_kwargs)
    temp_paths = _parse_generated_files(raw)
    paths = _relocate_generated_images(temp_paths)
    images = [_build_image_payload(path, label=basename_from_path(path)) for path in paths]
    primary = images[0]
    result = {
        'success': True,
        'prompt': text,
        'image_size': size,
        'batch_size': count,
        'images': images,
        **primary,
    }
    agentic_config = lazyllm.globals.get('agentic_config')
    if isinstance(agentic_config, dict):
        register_generated_image_urls(agentic_config, result)
    return result


def _resolve_source_image_paths(url: Optional[str], urls: Optional[List[str]]) -> List[str]:
    candidates: List[str] = []
    if url:
        candidates.append(str(url).strip())
    for item in urls or []:
        value = str(item or '').strip()
        if value:
            candidates.append(value)
    if not candidates:
        raise ValueError('at least one source image url is required for image editing')

    resolved: List[str] = []
    seen: set[str] = set()
    for raw in candidates:
        local_path = resolve_local_image_path(raw)
        if not local_path or not os.path.isfile(local_path):
            raise ValueError(f'source image file not found: {local_path or raw}')
        if local_path.lower().endswith(_IMAGE_SUFFIXES) and local_path not in seen:
            seen.add(local_path)
            resolved.append(local_path)
    if not resolved:
        raise ValueError('no valid source image files resolved')
    return resolved


@fc_register('tool', execute_in_sandbox=False)
@handle_tool_errors
def image_generator(
    prompt: str,
    image_size: str = _DEFAULT_IMAGE_SIZE,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """Generate an image from a text prompt (text-to-image).

    Uses the configured ``image_generator`` role in runtime_models (type
    ``text2image``). Model files are written under lazyllm temp first, then
    moved into ``shared_upload_dir/ai_generated/`` for signed static URLs.

    Args:
        prompt: Natural-language description of the image to generate.
        image_size: Output resolution, e.g. ``1024x1024``.
        batch_size: Number of images to generate (default 1).

    Returns:
        On success: ``success``, ``prompt``, ``local_path``, optional
        ``image_url`` / ``image_markdown``, and ``images`` (list per file).
    """
    return _run_image_model(
        'image_generator',
        prompt,
        image_size=image_size,
        batch_size=batch_size,
    )


@fc_register('tool', execute_in_sandbox=False)
@handle_tool_errors
def image_editor(
    prompt: str,
    url: str,
    urls: Optional[List[str]] = None,
    image_size: str = _DEFAULT_IMAGE_SIZE,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """Edit a reference image according to a text instruction (image-to-image).

    Uses the configured ``image_editor`` role in runtime_models (type
    ``image_editing``). Pass ``local_path`` from kb results or a filesystem path;
    ``/static-files/`` signed URLs are resolved automatically.

    Args:
        prompt: Edit instruction, e.g. change colors or add text.
        url: Primary reference image path or signed static URL.
        urls: Optional extra reference images (same path rules as ``url``).
        image_size: Output resolution, e.g. ``1024x1024``.
        batch_size: Number of variants to generate (default 1).

    Returns:
        Same shape as ``image_generator``.
    """
    source_files = _resolve_source_image_paths(url, urls)
    return _run_image_model(
        'image_editor',
        prompt,
        files=source_files,
        image_size=image_size,
        batch_size=batch_size,
    )
