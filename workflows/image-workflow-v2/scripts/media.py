from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from lazyllm.tools.agent import ToolExecutionError

from lazymind.chat.engine.tools.infra.image_generation_support import (
    _resolve_source_image_paths,
)
from lazymind.chat.engine.tools.multimodal import (
    image_editor,
    image_generator,
)

_ASPECT_RATIO_SIZES = {
    # Keep hints near LazyMind's provider-neutral 1024px default. Concrete
    # providers may normalize them further, while the prompt also carries the
    # requested ratio so models that expose only fixed sizes retain the intent.
    '1:1': '1024x1024',
    '16:9': '1344x768',
    '9:16': '768x1344',
    '4:3': '1152x864',
    '3:4': '864x1152',
    '3:2': '1152x768',
    '2:3': '768x1152',
    '21:9': '1344x576',
}

_SUPPORTED_RATIO_RE = re.compile(
    r'(?<!\d)(21\s*[:：]\s*9|16\s*[:：]\s*9|9\s*[:：]\s*16|'
    r'4\s*[:：]\s*3|3\s*[:：]\s*4|3\s*[:：]\s*2|2\s*[:：]\s*3|'
    r'1\s*[:：]\s*1)(?!\d)',
    re.IGNORECASE,
)
_ASPECT_RATIO_WORD_RE = re.compile(
    r'竖版|竖向|纵向|portrait|vertical|横版|横向|宽屏|landscape|widescreen|方图|正方形|square',
    re.IGNORECASE,
)

_SOURCE_SIZE_TARGET_PIXELS = 1024 * 1024
_SOURCE_SIZE_MIN_EDGE = 512
_SOURCE_SIZE_MAX_EDGE = 2048
_SOURCE_SIZE_STEP = 8


def _coerce_url_list(urls: Optional[Union[str, List[str]]]) -> List[str]:
    if urls is None:
        return []
    if isinstance(urls, list):
        return [str(item).strip() for item in urls if str(item or '').strip()]
    text = str(urls).strip()
    if not text:
        return []
    if text.startswith('['):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item or '').strip()]
    return [text]


def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    ratio = str(aspect_ratio or '').strip()
    try:
        return _ASPECT_RATIO_SIZES[ratio]
    except KeyError as exc:
        supported = ', '.join(_ASPECT_RATIO_SIZES)
        raise ToolExecutionError(
            f'Unsupported aspect_ratio {ratio!r}. Supported values: {supported}.'
        ) from exc


def _source_preserving_image_size(source_path: str) -> str:
    """Return a provider-neutral edit size that retains the source orientation."""
    try:
        from PIL import Image

        with Image.open(source_path) as image:
            width, height = image.size
            orientation = image.getexif().get(274)
            if orientation in {5, 6, 7, 8}:
                width, height = height, width
            image.load()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            'The authoritative source image could not be read for aspect-ratio preservation.'
        ) from exc

    if width <= 0 or height <= 0:
        raise ToolExecutionError(
            'The authoritative source image has invalid dimensions.'
        )

    min_scale = max(_SOURCE_SIZE_MIN_EDGE / width, _SOURCE_SIZE_MIN_EDGE / height)
    max_scale = min(_SOURCE_SIZE_MAX_EDGE / width, _SOURCE_SIZE_MAX_EDGE / height)
    if min_scale > max_scale:
        raise ToolExecutionError(
            'The authoritative source image aspect ratio is too extreme to preserve within '
            f'{_SOURCE_SIZE_MIN_EDGE}-{_SOURCE_SIZE_MAX_EDGE}px media-model limits.'
        )

    target_scale = math.sqrt(_SOURCE_SIZE_TARGET_PIXELS / (width * height))
    scale = min(max(target_scale, min_scale), max_scale)

    def _aligned(value: float) -> int:
        rounded = int(round(value / _SOURCE_SIZE_STEP) * _SOURCE_SIZE_STEP)
        return min(_SOURCE_SIZE_MAX_EDGE, max(_SOURCE_SIZE_MIN_EDGE, rounded))

    output_width = _aligned(width * scale)
    output_height = _aligned(height * scale)
    return f'{output_width}x{output_height}'


def _require_generated_result(result: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Convert a missing global media role into a clear workflow failure."""
    if not isinstance(result, dict):
        raise ToolExecutionError(f'Configured {role} returned an invalid result.')
    if result.get('status') == 'blocked':
        control = result.get('_agent_control')
        marker = control.get('final_text') if isinstance(control, dict) else ''
        raise ToolExecutionError(
            str(marker or result.get('message') or f'No configured {role} model is available.')
        )
    images = result.get('images') or []
    if not images and not result.get('local_path'):
        raise ToolExecutionError(f'Configured {role} returned no generated image files.')
    result.setdefault('model_role', role)
    return result


def _generate_with_configured_model(
    prompt: str,
    *,
    aspect_ratio: str,
    urls: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Generate through the request-scoped LazyMind media-model roles."""
    references = _coerce_url_list(urls)
    image_size = _size_for_aspect_ratio(aspect_ratio)
    ratio_prompt = f'{prompt}\nRequested output aspect ratio: {aspect_ratio}.'
    if references:
        result = image_editor(
            ratio_prompt,
            references,
            image_size=image_size,
            batch_size=1,
        )
        return _require_generated_result(result, 'image_editor')
    result = image_generator(
        ratio_prompt,
        image_size=image_size,
        batch_size=1,
    )
    return _require_generated_result(result, 'image_generator')


def _edit_with_configured_model(
    prompt: str,
    urls: Union[str, List[str]],
    *,
    aspect_ratio: Optional[str] = None,
) -> Dict[str, Any]:
    """Edit one authoritative image through the configured editor role."""
    references = _coerce_url_list(urls)
    if len(references) != 1:
        raise ToolExecutionError(
            'Configured image editing requires exactly one authoritative source image.'
        )
    resolved_references = _resolve_source_image_paths(references)
    if len(resolved_references) != 1:
        raise ToolExecutionError(
            'Configured image editing requires exactly one resolved authoritative source image.'
        )
    ratio = str(aspect_ratio or '').strip()
    image_size = (
        _size_for_aspect_ratio(ratio)
        if ratio
        else _source_preserving_image_size(resolved_references[0])
    )
    edit_prompt = prompt
    if ratio:
        edit_prompt += f'\nRequested output aspect ratio: {ratio}.'
    else:
        edit_prompt += '\nPreserve the source image aspect ratio.'
    result = image_editor(
        edit_prompt,
        resolved_references,
        image_size=image_size,
        batch_size=1,
    )
    return _require_generated_result(result, 'image_editor')


def _artifact_rows(key: str) -> List[Dict[str, Any]]:
    """Return normalized artifact rows from the current workflow binding."""
    from lazymind.chat.engine.subagent.tools import get_artifact

    result = get_artifact(key)
    if not isinstance(result, dict) or result.get('status') != 'ok':
        return []
    return [row for row in (result.get('artifacts') or []) if isinstance(row, dict)]


def _artifact_text(key: str) -> str:
    rows = _artifact_rows(key)
    if not rows:
        raise ToolExecutionError(f'Required workflow artifact {key!r} is missing.')
    value = rows[-1].get('value') or {}
    if isinstance(value, dict):
        if value.get('text') is not None:
            return str(value['text']).strip()
        if value.get('data') is not None:
            data = value['data']
            return data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and value.get('path'):
        return Path(value['path']).read_text(encoding='utf-8').strip()
    raise ToolExecutionError(f'Workflow artifact {key!r} contains no readable text.')


def _artifact_json(key: str) -> Dict[str, Any]:
    rows = _artifact_rows(key)
    if not rows:
        raise ToolExecutionError(f'Required workflow artifact {key!r} is missing.')
    value = rows[-1].get('value') or {}
    data = value.get('data') if isinstance(value, dict) else value
    if data is None and isinstance(value, dict) and value.get('path'):
        data = Path(value['path']).read_text(encoding='utf-8')
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                f'Workflow artifact {key!r} is not valid JSON.'
            ) from exc
    if not isinstance(data, dict):
        raise ToolExecutionError(f'Workflow artifact {key!r} must be a JSON object.')
    return data


def _artifact_image_refs(*keys: str) -> List[str]:
    refs: List[str] = []
    for key in keys:
        for row in _artifact_rows(key):
            value = row.get('value') or {}
            if isinstance(value, dict):
                ref = value.get('path') or value.get('image_url') or value.get('url')
            else:
                ref = value
            text = str(ref or '').strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _has_explicit_aspect_ratio(request: str) -> bool:
    text = str(request or '')
    return bool(_SUPPORTED_RATIO_RE.search(text) or _ASPECT_RATIO_WORD_RE.search(text))


def _requested_aspect_ratio(request: str) -> str:
    update = str(request or '').rpartition('User update (overrides conflicting launch requirements):\n')[2]
    if update and _has_explicit_aspect_ratio(update):
        request = update
    matches = list(_SUPPORTED_RATIO_RE.finditer(str(request or '')))
    match = matches[-1] if matches else None
    if match:
        return re.sub(r'\s+', '', match.group(1)).replace('：', ':')
    text = str(request or '')
    if re.search(r'(?:竖版|竖向|纵向|portrait|vertical)', text, re.IGNORECASE):
        return '9:16'
    if re.search(r'(?:横版|横向|宽屏|landscape|widescreen)', text, re.IGNORECASE):
        return '16:9'
    if re.search(r'(?:方图|正方形|square)', text, re.IGNORECASE):
        return '1:1'
    return '1:1'


def _immutable_request() -> str:
    from lazymind.chat.engine.subagent.context import require_context

    ctx = require_context()
    from lazymind.chat.workflow.image_request import effective_image_request

    return effective_image_request(ctx.params or {})


def _publish_generated_images(slot: str, result: Dict[str, Any], source_tool: str) -> Dict[str, Any]:
    """Publish only files returned by the configured LazyMind media model."""
    from lazymind.chat.engine.subagent.tools import _save_artifact

    images = result.get('images') if isinstance(result, dict) else None
    if not isinstance(images, list) or not images:
        raise ToolExecutionError('Configured media model returned no normalized image payloads.')
    saved = []
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            raise ToolExecutionError('Configured media model returned an invalid image payload.')
        local_path = str(image.get('local_path') or '').strip()
        if not local_path or not Path(local_path).is_file():
            raise ToolExecutionError('Configured media-model payload has no real local file.')
        save_options: Dict[str, Any] = {
            'content_type': 'image',
            'source_tool': source_tool,
            'internal_publish': True,
        }
        if slot == 'ordinary_output':
            save_options['publisher_list_index'] = index
        saved.append(_save_artifact(slot, {'path': local_path}, **save_options))
    return {
        'status': 'ok',
        'slot': slot,
        'saved_count': len(saved),
        'model_role': result.get('model_role'),
        'provider': result.get('provider'),
        'model': result.get('model'),
        'image_size': result.get('image_size'),
    }


def generate_ordinary_image() -> Dict[str, Any]:
    """Generate and atomically publish the ordinary-route image.

    The prompt and optional references come only from bound workflow artifacts;
    the aspect ratio respects bound request revisions and the current update. A failed provider
    call cannot create ``ordinary_output``.
    """
    prompt = _artifact_text('ordinary_prompt')
    request = _immutable_request()
    update = request.partition('User update (overrides conflicting launch requirements):\n')[2]
    # A later approval must not undo a requirement already saved by preparation.
    marker = 'User update (overrides conflicting launch requirements):\n'
    ratio_request = prompt.split('\nReference evidence', 1)[0] if marker in prompt else request or prompt
    if update:
        prompt += '\nCurrent user requirements (override conflicting prompt details):\n' + update
        ratio_request += '\n' + marker + update
    references = _artifact_image_refs('source_image', 'material_images')
    result = _generate_with_configured_model(
        prompt,
        aspect_ratio=_requested_aspect_ratio(ratio_request),
        urls=references or None,
    )
    return _publish_generated_images(
        'ordinary_output', result, 'generate_ordinary_image',
    )


def generate_edit_candidate() -> Dict[str, Any]:
    """Generate and atomically publish one real local-edit candidate."""
    contract = _artifact_json('edit_contract')
    source_refs = _artifact_image_refs('authoritative_image')
    if len(source_refs) != 1:
        raise ToolExecutionError(
            'The edit route requires exactly one authoritative_image artifact.'
        )
    required = ('requested_edit', 'edit_scope', 'preserve', 'do_not')
    missing = [key for key in required if not str(contract.get(key) or '').strip()]
    if missing:
        raise ToolExecutionError(
            f'edit_contract is missing required fields: {", ".join(missing)}.'
        )
    prompt = '\n'.join((
        f'Requested edit: {contract["requested_edit"]}',
        f'Edit scope: {contract["edit_scope"]}',
        f'Preserve: {contract["preserve"]}',
        f'Do not: {contract["do_not"]}',
    ))
    request = _immutable_request()
    update = request.partition('User update (overrides conflicting launch requirements):\n')[2]
    request = str(contract.get('user_request') or request)
    if update:
        prompt += '\nCurrent user requirements (preserve everything else):\n' + update
        request += '\nUser update (overrides conflicting launch requirements):\n' + update
    explicit_ratio = _has_explicit_aspect_ratio(request)
    aspect_ratio = _requested_aspect_ratio(request) if explicit_ratio else None
    result = _edit_with_configured_model(
        prompt,
        source_refs,
        aspect_ratio=aspect_ratio,
    )
    return _publish_generated_images(
        'edit_candidate', result, 'generate_edit_candidate',
    )
