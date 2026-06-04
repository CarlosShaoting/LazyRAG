import re
from typing import Any, Dict

from .static_file_url import static_file_url_from_any, basename_from_path as _basename

_IMAGE_MD_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_STATIC_FILES_MARKER = '/static-files/'
_UPLOAD_ROOT_MARKER = '/var/lib/lazymind/uploads/'
_BLOCKED_HOST_MARKERS = (
    'ext.lazymind.ai',
    'agent-cdn.minimax.io',
)


def _extract_static_files_ref(url: str) -> str:
    trimmed = (url or '').strip()
    idx = trimmed.find(_STATIC_FILES_MARKER)
    if idx < 0:
        return ''
    return trimmed[idx:]


def register_generated_image_urls(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    if not isinstance(config, dict) or not isinstance(payload, dict):
        return
    registry = config.setdefault('_image_url_registry', {})
    candidates: list[str] = []
    for key in ('image_url', 'image_markdown', 'local_path'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    images = payload.get('images')
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            for key in ('image_url', 'image_markdown', 'local_path'):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    for raw in candidates:
        signed = static_file_url_from_any(raw)
        if not signed:
            static_ref = _extract_static_files_ref(raw)
            signed = static_file_url_from_any(static_ref) if static_ref else ''
        if not signed:
            continue
        registry[signed] = signed
        base = _basename(signed)
        if base:
            registry[base] = signed
        static_ref = _extract_static_files_ref(signed) or _extract_static_files_ref(raw)
        if static_ref:
            registry[static_ref] = signed


def _is_blocked_external_url(url: str) -> bool:
    lowered = url.lower()
    if _UPLOAD_ROOT_MARKER in url:
        return True
    return any(marker in lowered for marker in _BLOCKED_HOST_MARKERS)


def build_image_url_map_from_config(config: Dict[str, Any] | None) -> Dict[str, str]:
    if not isinstance(config, dict):
        return {}

    url_map: Dict[str, str] = {}
    registry = config.get('_image_url_registry')
    if isinstance(registry, dict):
        for key, value in registry.items():
            signed = static_file_url_from_any(str(value))
            if signed:
                url_map[str(key)] = signed
                url_map[signed] = signed

    refs = config.get('_citation_sources')
    if isinstance(refs, dict):
        for source in refs.values():
            if not isinstance(source, dict):
                continue
            for field in ('text', 'content'):
                signed = static_file_url_from_any(str(source.get(field) or ''))
                if signed:
                    url_map[signed] = signed
            metadata = source.get('metadata')
            if isinstance(metadata, dict):
                signed = static_file_url_from_any(str(metadata.get('image_url') or ''))
                if signed:
                    url_map[signed] = signed
            image_md = source.get('image_markdown')
            if isinstance(image_md, str):
                for match in _IMAGE_MD_RE.finditer(image_md):
                    signed = static_file_url_from_any(match.group(2))
                    if signed:
                        url_map[signed] = signed

    return url_map


def _resolve_image_target(url: str, url_map: Dict[str, str]) -> str:
    trimmed = (url or '').strip()
    if not trimmed or trimmed.startswith('data:'):
        return trimmed

    if trimmed.startswith('/static-files/'):
        return static_file_url_from_any(trimmed) or trimmed

    direct = url_map.get(trimmed)
    if direct:
        return direct

    signed = static_file_url_from_any(trimmed)
    if signed:
        return signed

    if trimmed.startswith('http://') or trimmed.startswith('https://'):
        base = _basename(trimmed)
        if base and base in url_map:
            return url_map[base]
        if _is_blocked_external_url(trimmed):
            return ''
    return trimmed


def rewrite_markdown_image_urls(
    markdown: str,
    url_map: Dict[str, str] | None = None,
    config: Dict[str, Any] | None = None,
) -> str:
    if not isinstance(markdown, str) or not markdown:
        return markdown

    merged_map: Dict[str, str] = {}
    merged_map.update(build_image_url_map_from_config(config))
    merged_map.update(url_map or {})

    def _replace(match: re.Match) -> str:
        alt, url = match.group(1), (match.group(2) or '').strip()
        if not url:
            return match.group(0)
        mapped = _resolve_image_target(url, merged_map)
        if not mapped:
            return alt if alt else ''
        if mapped != url:
            return f'![{alt}]({mapped})'
        return match.group(0)

    return _IMAGE_MD_RE.sub(_replace, markdown)
