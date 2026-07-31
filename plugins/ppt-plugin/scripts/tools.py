"""PPT plugin tools — HTML slide pipeline for SubAgent.

Pipeline:
  collect (optional): kb / web_search / ppt_search_web_images
    → ppt_register_material_images  (workspace Pool-B images)
  ppt_init_deck  (auto-attaches registered material images)
  → ppt_run_stage(preflight|style|outline|asset-plan|batch-page-html|…)
  → ppt_publish_pages  (disk HTML → preview_html artifacts; UI updates)
  → optionally refine preview_notes via save_artifacts (richer spoken intro)

PPTX export is NOT a skill tool — the user clicks Export in PluginPanel.
Runtime lives under plugins/ppt-plugin/runtime/ (vendored SenseNova subset).
Do NOT ppt_read_page_html + save_artifacts for full HTML — tool results >16KB
are offloaded and the model never sees the body, so saves get stuck forever.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Union
from urllib.parse import urlparse

import requests

from lazymind.chat.engine.subagent.context import require_context
from lazymind.chat.engine.subagent.tools import _save_artifact
from lazymind.chat.engine.tools.infra import tool_error, tool_success
from lazymind.chat.service.utils.static_file_url import (
    local_path_from_static_file_url,
)

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
# Vendored SenseNova runtime (not the full skills tree). See plugins/ppt-plugin/README.md.
_RUNTIME = _PLUGIN_ROOT / 'runtime'
_IMAGE_GEN = _PLUGIN_ROOT / 'image_gen'
_RUN_STAGE = _RUNTIME / 'scripts' / 'run_stage.py'

_VALID_STAGES = frozenset({
    'preflight', 'style', 'outline', 'asset-plan',
    'gen-image', 'page-html', 'batch-gen-image', 'batch-page-html',
    'refine-page', 'batch-refine-page',
})

# LLM/VLM stages: in-process + AutoModel. preflight also in-process (no LLM).
_INPROCESS_STAGES = frozenset({
    'preflight', 'style', 'outline', 'asset-plan',
    'page-html', 'batch-page-html', 'refine-page', 'batch-refine-page',
})

# Optional T2I still shells out to image_gen/ (vendored sn-image-base subset).
_IMAGE_STAGES = frozenset({'gen-image', 'batch-gen-image'})

_STAGE_ORDER_HINT = (
    'preflight → style → outline → asset-plan → '
    '[batch-gen-image if needed] → batch-page-html'
)

_NULLISH = frozenset({'', 'null', 'none', 'undefined', 'nil'})
_PROMPT_PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')

_run_stage_mod: Any = None
_model_client_mod: Any = None


def _coerce_str(value: Any, default: str = '') -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in _NULLISH else text


def _coerce_int(value: Any, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = default if value is None or _coerce_str(value) == '' else int(value)
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def _sanitize_prompt(text: str) -> str:
    return _PROMPT_PLACEHOLDER_RE.sub(r'{ \1 }', text) if text else text


def _workspace_root() -> Path:
    ctx = require_context()
    root = Path(ctx.workspace_path) if ctx.workspace_path else Path('/tmp')
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_deck_dir(deck_dir: str) -> Path:
    path = Path(_coerce_str(deck_dir)).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f'deck_dir does not exist: {path}')
    if not (path / 'task_pack.json').exists() or not (path / 'info_pack.json').exists():
        raise FileNotFoundError(
            f'deck_dir missing task_pack.json / info_pack.json: {path}. Call ppt_init_deck first.',
        )
    return path


def _parse_stage_json(stdout: str, stderr: str, returncode: int) -> dict:
    combined = (stdout or '') + '\n' + (stderr or '')
    payload: dict = {}
    for line in reversed([ln.strip() for ln in combined.splitlines() if ln.strip()]):
        if line.startswith('{') and line.endswith('}'):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not payload:
        payload = {
            'status': 'failed',
            'error': (stderr or stdout or 'empty stdout').strip()[:2000],
        }
    if returncode != 0 and payload.get('status') not in ('ok', 'skipped'):
        payload.setdefault('status', 'failed')
        payload.setdefault('error', (stderr or stdout or f'exit {returncode}')[:2000])
    return payload


def _run_image_stage_cmd(cmd: list[str], *, timeout: int = 1200) -> dict:
    env = {k: str(v) for k, v in os.environ.items() if v is not None}
    env['SN_IMAGE_BASE'] = env.get('SN_IMAGE_BASE') or str(_IMAGE_GEN.resolve())
    proc = subprocess.run(
        cmd,
        cwd=str(_RUNTIME / 'scripts'),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return _parse_stage_json(proc.stdout or '', proc.stderr or '', proc.returncode)


def _slugify(text: str, fallback: str = 'ppt_deck') -> str:
    raw = re.sub(r'[^\w\u4e00-\u9fff\-]+', '_', (text or '').strip())[:48].strip('_')
    return raw or fallback


def _infer_language(user_query: str) -> str:
    return 'zh-Hans' if re.search(r'[\u4e00-\u9fff]', user_query or '') else 'en'


def _title_from_html(html: str) -> str:
    tm = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    if tm:
        return re.sub(r'\s+', ' ', tm.group(1)).strip()[:120]
    hm = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S)
    if hm:
        title = re.sub(r'<[^>]+>', '', hm.group(1))
        return re.sub(r'\s+', ' ', title).strip()[:120]
    return ''


def _strip_tags(fragment: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', fragment or '')
    text = re.sub(r'&nbsp;|&#160;', ' ', text, flags=re.I)
    text = re.sub(r'&amp;', '&', text, flags=re.I)
    text = re.sub(r'&lt;', '<', text, flags=re.I)
    text = re.sub(r'&gt;', '>', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_slide_copy(html: str) -> dict[str, Any]:
    """Pull title / subtitle / bullet-like phrases from slide HTML for speaker notes."""
    title = _title_from_html(html)
    subtitle = ''
    # Common SenseNova structure: header h1 + following <p>
    hm = re.search(
        r'<h1[^>]*>[\s\S]*?</h1>\s*<p[^>]*>([\s\S]*?)</p>',
        html,
        re.I,
    )
    if hm:
        subtitle = _strip_tags(hm.group(1))[:160]

    phrases: list[str] = []
    # Prefer semantic / card classes used by the HTML pipeline.
    for pattern in (
        r'class=["\'][^"\']*(?:kpi-title|kpi-label|kpi-value|chart-title|card-title|section-title)[^"\']*["\'][^>]*>([\s\S]*?)</',
        r'<h[2-4][^>]*>([\s\S]*?)</h[2-4]>',
        r'<li[^>]*>([\s\S]*?)</li>',
        r'<strong[^>]*>([\s\S]*?)</strong>',
    ):
        for m in re.finditer(pattern, html, re.I):
            t = _strip_tags(m.group(1))
            if 2 <= len(t) <= 80 and t not in phrases and t != title:
                phrases.append(t)
            if len(phrases) >= 10:
                break
        if len(phrases) >= 10:
            break

    return {
        'title': title,
        'subtitle': subtitle,
        'phrases': phrases,
    }


def _notes_from_html(html: str, page_no: int) -> str:
    """Build a richer auto speaker-notes paragraph from the page HTML.

    Used at publish time so the UI has a usable script even before the model
    rewrites notes. Prefer 4–7 sentences / ~120–280 Chinese chars.
    """
    meta = _extract_slide_copy(html)
    title = meta['title'] or f'第 {page_no} 页'
    subtitle = meta['subtitle']
    phrases = meta['phrases'][:8]

    parts: list[str] = []
    if subtitle:
        parts.append(f'本页主题是「{title}」，副线是「{subtitle}」。')
    else:
        parts.append(f'本页主题是「{title}」。')

    if phrases:
        lead = '、'.join(phrases[:4])
        parts.append(
            f'讲解时请先点明标题，再依次展开：{lead}'
            + ('等要点。' if len(phrases) > 4 else '。')
        )
        if len(phrases) > 4:
            more = '、'.join(phrases[4:8])
            parts.append(f'补充说明时可带过 {more}，帮助听众建立完整印象。')
    else:
        parts.append(
            '讲解时请先点出页面标题，再按版块顺序说明核心观点与关键数据，'
            '并结合图示或卡片信息做简要解读。'
        )

    parts.append(
        '建议用一两句解释「为什么重要 / 对听众意味着什么」，'
        '避免只念标题；最后用一句结论收束本页，并自然过渡到下一页。'
    )
    notes = ''.join(parts)
    # Soft length guard for artifact summary / UI.
    return notes[:600]


_THINK_BLOCK_RE = re.compile(r'<think\b[^>]*>[\s\S]*?</think>', re.IGNORECASE)
_HTML_DOC_RE = re.compile(
    r'(?is)(<!doctype\s+html\b[\s\S]*?</html>|<html\b[\s\S]*?</html>)'
)


def _sanitize_page_html(raw: str) -> str:
    """Strip model think traces / markdown fences; keep the HTML document."""
    s = (raw or '').strip()
    if not s:
        return s
    s = _THINK_BLOCK_RE.sub('', s).strip()
    s = re.sub(r'(?is)^<think\b[^>]*>[\s\S]*?(?=<!doctype|<html\b|```)', '', s).strip()
    if s.startswith('```'):
        first_nl = s.find('\n')
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith('```'):
            s = s[:-3]
        s = s.strip()
    fence = re.search(r'(?is)```(?:html|HTML)?\s*\n([\s\S]*?)```', s)
    if fence:
        s = fence.group(1).strip()
    m = _HTML_DOC_RE.search(s)
    return m.group(1).strip() if m else s.strip()


def _page_html_path(deck: Path, page_no: int) -> Path:
    return deck / 'pages' / f'page_{page_no:03d}.html'


def _iter_page_numbers(deck: Path) -> list[int]:
    pages: list[int] = []
    pages_dir = deck / 'pages'
    if not pages_dir.is_dir():
        return pages
    for path in sorted(pages_dir.glob('page_*.html')):
        if '.refined.' in path.name:
            continue
        m = re.match(r'page_(\d+)\.html$', path.name)
        if m:
            pages.append(int(m.group(1)))
    return pages


def _parse_page_list(pages: Any) -> Optional[list[int]]:
    """Normalize pages arg to a sorted unique 1-based list, or None = all."""
    if pages is None or pages == '' or str(pages).strip().lower() in _NULLISH:
        return None
    if isinstance(pages, int):
        return [pages] if pages >= 1 else None
    if isinstance(pages, float):
        n = int(pages)
        return [n] if n >= 1 else None
    if isinstance(pages, str):
        text = pages.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parts = re.split(r'[\s,;]+', text)
            out = []
            for p in parts:
                if not p:
                    continue
                try:
                    n = int(p)
                except ValueError:
                    continue
                if n >= 1:
                    out.append(n)
            return sorted(set(out)) or None
        return _parse_page_list(parsed)
    if isinstance(pages, (list, tuple)):
        out = []
        for item in pages:
            try:
                n = int(item)
            except (TypeError, ValueError):
                continue
            if n >= 1:
                out.append(n)
        return sorted(set(out)) or None
    return None


def _notes_stub(title_hint: str, page_no: int) -> str:
    """Fallback when HTML extraction is unavailable."""
    title = (title_hint or '').strip() or f'第 {page_no} 页'
    return (
        f'本页主题是「{title}」。讲解时先点出页面标题，再按版块顺序说明核心要点与数据，'
        f'补充为什么这些信息对听众重要，最后用一句话收束本页结论，并自然过渡到下一页。'
    )


def _publish_one_page(
    deck: Path,
    page_no: int,
    *,
    with_notes: bool = True,
) -> dict[str, Any]:
    """Save one page HTML (+ optional notes stub) into session artifacts."""
    path = _page_html_path(deck, page_no)
    if not path.exists():
        return {'page': page_no, 'ok': False, 'error': f'missing {path.name}'}
    html = _sanitize_page_html(path.read_text(encoding='utf-8'))
    if not html or '<html' not in html.lower():
        return {'page': page_no, 'ok': False, 'error': 'not a valid HTML document'}
    title = _title_from_html(html)
    html_res = _save_artifact(
        key='preview_html',
        value=html,
        content_type='text',
        source_tool='ppt_publish_pages',
        sort_order=page_no,
        caption=title or None,
    )
    notes_res = None
    if with_notes:
        notes_res = _save_artifact(
            key='preview_notes',
            value=_notes_from_html(html, page_no) or _notes_stub(title, page_no),
            content_type='text',
            source_tool='ppt_publish_pages',
            sort_order=page_no,
        )
    return {
        'page': page_no,
        'ok': True,
        'title_hint': title,
        'bytes': len(html.encode('utf-8')),
        'html_path': str(path.resolve()),
        'html_save': html_res,
        'notes_save': notes_res,
    }


def _publish_pages_from_disk(
    deck: Path,
    pages: Optional[list[int]] = None,
    *,
    with_notes: bool = True,
) -> dict[str, Any]:
    targets = pages if pages is not None else _iter_page_numbers(deck)
    published: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for page_no in targets:
        try:
            require_context()
            item = _publish_one_page(deck, page_no, with_notes=with_notes)
        except Exception as exc:
            item = {'page': page_no, 'ok': False, 'error': str(exc)}
        if item.get('ok'):
            published.append({
                'page': item['page'],
                'title_hint': item.get('title_hint'),
                'bytes': item.get('bytes'),
            })
        else:
            failed.append({'page': page_no, 'error': item.get('error') or 'publish failed'})
    return {
        'deck_dir': str(deck.resolve()),
        'published_count': len(published),
        'failed_count': len(failed),
        'published': published,
        'failed': failed or None,
    }


def _outline_page_numbers(
    deck: Path,
    start_page: int = 0,
    end_page: int = 0,
) -> list[int]:
    outline_path = deck / 'outline.json'
    if not outline_path.exists():
        return []
    try:
        outline = json.loads(outline_path.read_text(encoding='utf-8'))
    except Exception:
        return []
    out: list[int] = []
    for page in outline.get('pages', []) or []:
        try:
            pno = int(page.get('page_no', 0))
        except (TypeError, ValueError):
            continue
        if pno <= 0:
            continue
        if start_page > 0 and pno < start_page:
            continue
        if end_page > 0 and pno > end_page:
            continue
        out.append(pno)
    return out


def _batch_page_html_publish_progressive(
    deck: Path,
    *,
    concurrency: int = 2,
    start_page: int = 0,
    end_page: int = 0,
) -> dict:
    """Generate pages concurrently; publish to UI in page order as soon as ready."""
    mc, rs = _load_sn_ppt_modules()
    page_nos = _outline_page_numbers(deck, start_page, end_page)
    if not page_nos:
        return {'status': 'failed', 'error': 'no pages in outline matching range', 'stage': 'page-html'}

    mc.set_llm_impl(_agent_llm_call)
    workers = max(1, min(int(concurrency or 2), 8))
    results: dict[int, dict[str, Any]] = {}
    published: list[dict[str, Any]] = []
    ready_ok: dict[int, bool] = {}
    next_publish_i = 0

    def _flush_ready() -> None:
        nonlocal next_publish_i
        while next_publish_i < len(page_nos):
            pno = page_nos[next_publish_i]
            if pno not in ready_ok:
                return
            if not ready_ok[pno]:
                next_publish_i += 1
                continue
            try:
                pub = _publish_one_page(deck, pno, with_notes=True)
                if pub.get('ok'):
                    published.append({
                        'page': pno,
                        'title_hint': pub.get('title_hint'),
                        'bytes': pub.get('bytes'),
                    })
                else:
                    results[pno]['publish_error'] = pub.get('error') or 'publish failed'
            except Exception as exc:
                results[pno]['publish_error'] = str(exc)
            next_publish_i += 1

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {
                ex.submit(rs._capture_cmd, rs.cmd_page_html, deck, pno): pno
                for pno in page_nos
            }
            for fut in as_completed(future_map):
                pno = future_map[fut]
                try:
                    code, payload = fut.result()
                except Exception as exc:
                    code, payload = 1, {'status': 'failed', 'error': str(exc)}
                if not isinstance(payload, dict):
                    payload = {'status': 'failed', 'error': 'empty page payload'}
                ok = code == 0 and payload.get('status', 'ok' if code == 0 else 'failed') == 'ok'
                results[pno] = {'page': pno, 'ok': ok, 'payload': payload}
                ready_ok[pno] = ok
                _flush_ready()
    finally:
        mc.set_llm_impl(None)
        mc.set_vlm_impl(None)

    failed = [
        {'page': p, 'error': (results[p].get('payload') or {}).get('error') or 'failed'}
        for p in page_nos if not results.get(p, {}).get('ok')
    ]
    return {
        'status': 'ok' if len(failed) == 0 else ('partial' if published else 'failed'),
        'stage': 'page-html',
        'concurrency': workers,
        'submitted': len(page_nos),
        'ok': len(page_nos) - len(failed),
        'failed': len(failed),
        'failed_detail': failed or None,
        'published_count': len(published),
        'published': published,
        'auto_published': True,
    }


def _agent_llm_call(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    timeout: float | None = None,
    retries: int = 0,
    request_name: str = 'llm',
) -> str:
    from lazyllm import AutoModel
    from lazyllm.components import ChatPrompter

    llm = AutoModel(model='llm').share(
        prompt=ChatPrompter(instruction=_sanitize_prompt(system_prompt or '')),
        stream=False,
    )
    out = llm(user_prompt or '')
    text = str(out).strip() if out is not None else ''
    if not text:
        raise RuntimeError(f'AutoModel llm returned empty text [{request_name}]')
    return text


def _agent_vlm_call(
    system_prompt: str,
    user_prompt: str,
    images: list,
    *,
    model: str | None = None,
) -> str:
    from lazyllm import AutoModel
    from lazyllm.components.formatter import encode_query_with_filepaths

    paths = []
    for img in images or []:
        p = Path(img)
        if not p.exists():
            raise FileNotFoundError(f'image not found: {p}')
        paths.append(str(p.resolve()))
    encoded = encode_query_with_filepaths(
        f'{_sanitize_prompt(system_prompt or "")}\n\n{user_prompt or ""}'.strip(),
        paths,
    )
    out = AutoModel(model='vlm')(encoded, stream_output=False, llm_chat_history=[], lazyllm_files=None)
    text = str(out).strip() if out is not None else ''
    if not text:
        raise RuntimeError('AutoModel vlm returned empty text')
    return text


def _load_sn_ppt_modules() -> tuple[Any, Any]:
    global _run_stage_mod, _model_client_mod
    if _run_stage_mod is not None and _model_client_mod is not None:
        return _model_client_mod, _run_stage_mod

    for path in (str((_RUNTIME / 'lib').resolve()), str((_RUNTIME / 'scripts').resolve())):
        if path not in sys.path:
            sys.path.insert(0, path)

    import model_client as mc  # type: ignore  # noqa: WPS433
    import run_stage as rs  # type: ignore  # noqa: WPS433
    _model_client_mod = mc
    _run_stage_mod = rs
    return mc, rs


def _run_stage_inprocess(
    stage_name: str,
    deck: Path,
    *,
    page: int = 0,
    concurrency: int = 2,
    start_page: int = 0,
    end_page: int = 0,
) -> dict:
    mc, rs = _load_sn_ppt_modules()
    needs_llm = stage_name != 'preflight'
    if needs_llm:
        mc.set_llm_impl(_agent_llm_call)
    if stage_name in ('refine-page', 'batch-refine-page'):
        mc.set_vlm_impl(_agent_vlm_call)
    try:
        if stage_name == 'preflight':
            code, payload = rs._capture_cmd(rs.cmd_preflight, deck)
        elif stage_name == 'style':
            code, payload = rs._capture_cmd(rs.cmd_style, deck)
        elif stage_name == 'outline':
            code, payload = rs._capture_cmd(rs.cmd_outline, deck)
        elif stage_name == 'asset-plan':
            code, payload = rs._capture_cmd(rs.cmd_asset_plan, deck)
        elif stage_name == 'page-html':
            code, payload = rs._capture_cmd(rs.cmd_page_html, deck, page)
            if isinstance(payload, dict) and payload.get('status', 'ok' if code == 0 else 'failed') == 'ok':
                try:
                    pub = _publish_one_page(deck, page, with_notes=True)
                    payload['published'] = {
                        'page': page,
                        'ok': bool(pub.get('ok')),
                        'title_hint': pub.get('title_hint'),
                        'bytes': pub.get('bytes'),
                    }
                    payload['auto_published'] = True
                except Exception as exc:
                    payload['publish_error'] = str(exc)
        elif stage_name == 'batch-page-html':
            # Generate concurrently and publish each finished page to the UI immediately.
            return _batch_page_html_publish_progressive(
                deck,
                concurrency=concurrency,
                start_page=start_page,
                end_page=end_page,
            )
        elif stage_name == 'refine-page':
            code, payload = rs._capture_cmd(rs.cmd_refine_page, deck, page)
        elif stage_name == 'batch-refine-page':
            code, payload = rs._capture_cmd(rs.cmd_batch_refine_page, deck, concurrency)
        else:
            return {'status': 'failed', 'error': f'unsupported in-process stage: {stage_name}'}
        if not isinstance(payload, dict):
            payload = {'status': 'failed', 'error': 'empty stage payload'}
        payload.setdefault('status', 'ok' if code == 0 else 'failed')
        return payload
    except Exception as exc:
        return {'status': 'failed', 'error': f'{stage_name} failed: {exc}', 'stage': stage_name}
    finally:
        mc.set_llm_impl(None)
        mc.set_vlm_impl(None)


def _stage_tool_result(stage_name: str, payload: dict) -> dict:
    status = payload.get('status')
    clean = {k: v for k, v in payload.items() if not str(k).startswith('_')}
    if status == 'ok':
        return tool_success('ppt_run_stage', {'stage': stage_name, **clean})
    if status == 'skipped':
        return tool_success('ppt_run_stage', {
            'stage': stage_name,
            'status': 'skipped',
            'reason': payload.get('reason') or payload.get('error') or 'skipped',
            **{k: v for k, v in clean.items() if k != 'status'},
        })
    return tool_error(
        'ppt_run_stage',
        payload.get('error') or f'{stage_name} failed',
        detail=json.dumps(payload, ensure_ascii=False)[:2000],
        meta={'stage': stage_name},
    )


_MATERIAL_DIR_NAME = 'material_images'
_MATERIAL_MANIFEST = 'manifest.json'
_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
_DOWNLOAD_TIMEOUT = 25
_DOWNLOAD_UA = 'Mozilla/5.0 (compatible; LazyMind-PPT/1.0; material-image)'
_IMAGE_URL_KEYS = (
    'contentUrl', 'content_url', 'imageUrl', 'image_url',
    'thumbnailUrl', 'thumbnail_url', 'src', 'url',
)


def _material_root() -> Path:
    root = _workspace_root() / _MATERIAL_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _material_manifest_path() -> Path:
    return _material_root() / _MATERIAL_MANIFEST


def _load_material_manifest() -> dict:
    path = _material_manifest_path()
    if not path.exists():
        return {'images': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'images': []}
    if not isinstance(data, dict):
        return {'images': []}
    images = data.get('images')
    if not isinstance(images, list):
        data['images'] = []
    return data


def _write_material_manifest(data: dict) -> Path:
    path = _material_manifest_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def _is_image_url(value: str) -> bool:
    lower = value.lower()
    if not (lower.startswith('http://') or lower.startswith('https://')):
        return False
    for ext in _IMAGE_EXTS:
        if ext in lower:
            return True
    return any(token in lower for token in ('image', 'img', 'photo', 'pic'))


def _collect_image_urls(node: Any, out: List[str], seen: set) -> None:
    if isinstance(node, dict):
        for key in _IMAGE_URL_KEYS:
            raw = node.get(key)
            if isinstance(raw, str) and _is_image_url(raw) and raw not in seen:
                seen.add(raw)
                out.append(raw)
        for value in node.values():
            _collect_image_urls(value, out, seen)
    elif isinstance(node, list):
        for item in node:
            _collect_image_urls(item, out, seen)


def _guess_ext_from_bytes(data: bytes, fallback: str = '.png') -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    if data.startswith(b'BM'):
        return '.bmp'
    return fallback


def _resolve_local_image_ref(raw: str) -> Optional[Path]:
    text = (raw or '').strip()
    if not text:
        return None
    try:
        resolved = local_path_from_static_file_url(text)
        if resolved:
            text = resolved
    except Exception:
        pass
    path = Path(text).expanduser()
    if path.is_file() and path.suffix.lower() in _IMAGE_EXTS:
        return path.resolve()
    return None


def _download_image_bytes(url: str) -> bytes:
    resp = requests.get(
        url,
        timeout=_DOWNLOAD_TIMEOUT,
        headers={'User-Agent': _DOWNLOAD_UA},
        stream=True,
    )
    resp.raise_for_status()
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total > 12 * 1024 * 1024:
            raise ValueError('image larger than 12MB')
    data = b''.join(chunks)
    if len(data) < 32:
        raise ValueError('image payload too small')
    # Soft magic check — reject obvious HTML error pages
    head = data[:64].lstrip().lower()
    if head.startswith(b'<!doctype') or head.startswith(b'<html'):
        raise ValueError('URL returned HTML, not an image')
    return data


def _parse_images_payload(images_json: Union[str, list, None]) -> list[dict]:
    if isinstance(images_json, list):
        items = images_json
    else:
        raw = _coerce_str(images_json, '[]') or '[]'
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f'images_json must be a JSON array: {exc}') from exc
        if not isinstance(parsed, list):
            raise ValueError('images_json must be a JSON array')
        items = parsed
    out: list[dict] = []
    for item in items:
        if isinstance(item, str):
            out.append({'url': item})
            continue
        if not isinstance(item, dict):
            continue
        out.append(item)
    return out


def _stage_one_material_image(item: dict, index: int) -> dict:
    caption = _coerce_str(item.get('caption') or item.get('alt') or item.get('description'))
    alt = _coerce_str(item.get('alt') or caption) or f'material image {index + 1}'
    source = _coerce_str(item.get('source'), 'manual') or 'manual'
    url = _coerce_str(
        item.get('url') or item.get('image_url') or item.get('src'),
    )
    local_hint = _coerce_str(
        item.get('local_path') or item.get('path') or item.get('value'),
    )

    dest_dir = _material_root()
    stem = f'material_{index + 1:02d}_{uuid.uuid4().hex[:8]}'

    if local_hint:
        local = _resolve_local_image_ref(local_hint)
        if local is not None:
            ext = local.suffix.lower() or '.png'
            dest = dest_dir / f'{stem}{ext}'
            dest.write_bytes(local.read_bytes())
            return {
                'path': str(dest.resolve()),
                'alt': alt,
                'caption': caption or alt,
                'source': source or 'kb',
                'origin': str(local),
            }
        if local_hint.startswith(('http://', 'https://')):
            url = local_hint

    if not url:
        raise ValueError('each image needs url or local_path')

    data = _download_image_bytes(url)
    parsed_ext = Path(urlparse(url).path).suffix.lower()
    if parsed_ext not in _IMAGE_EXTS:
        parsed_ext = ''
    ext = parsed_ext or _guess_ext_from_bytes(data)
    dest = dest_dir / f'{stem}{ext}'
    dest.write_bytes(data)
    return {
        'path': str(dest.resolve()),
        'alt': alt,
        'caption': caption or alt,
        'source': source or 'web',
        'origin': url,
    }


def _attach_material_images_to_deck(deck: Path) -> dict:
    """Copy workspace material images into deck and wire info_pack Pool B."""
    manifest = _load_material_manifest()
    images = [x for x in (manifest.get('images') or []) if isinstance(x, dict) and x.get('path')]
    if not images:
        return {'attached': 0, 'reference_images': [], 'captions': {}}

    ip_path = deck / 'info_pack.json'
    ip = json.loads(ip_path.read_text(encoding='utf-8'))
    ua = ip.setdefault('user_assets', {})
    ref_paths: list[str] = list(ua.get('reference_images') or [])
    captions: dict[str, str] = dict(ua.get('reference_image_captions') or {})
    images_dir = deck / 'images'
    images_dir.mkdir(parents=True, exist_ok=True)

    attached = 0
    for i, entry in enumerate(images[:12]):
        src = Path(str(entry['path']))
        if not src.is_file():
            continue
        ext = src.suffix.lower() or '.png'
        dst = images_dir / f'material_{i + 1:02d}{ext}'
        dst.write_bytes(src.read_bytes())
        abs_dst = str(dst.resolve())
        if abs_dst not in ref_paths:
            ref_paths.append(abs_dst)
        cap = _coerce_str(entry.get('caption') or entry.get('alt'))
        if cap:
            captions[abs_dst] = cap
        attached += 1

    ua['reference_images'] = ref_paths
    ua['reference_image_captions'] = captions
    ip_path.write_text(json.dumps(ip, ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'attached': attached,
        'reference_images': ref_paths,
        'captions': captions,
    }


def ppt_search_web_images(query: str, count: Union[int, str, None] = 3) -> dict:
    """Search the open web for candidate image URLs for PPT slides.

    Use during collect_materials when the deck needs real photos / diagrams
    from the internet. Returns URLs only — then call ppt_register_material_images
    with the chosen URLs (and captions) so they land in the final HTML via
    outline use_image / Pool B.

    Tries Tavily (include_images) and Bocha image fields first, then a scoped
    web search fallback.

    Args:
        query (str): Visual concept to search, e.g. 'solar panel farm aerial'.
        count (int): Max URLs to return (1-6). Default 3.

    Returns:
        On success: query, urls (list of https image candidates).
    """
    q = _coerce_str(query)
    if not q:
        return tool_error('ppt_search_web_images', 'query is required')
    n = _coerce_int(count, 3, lo=1, hi=6)
    urls: list[str] = []
    seen: set[str] = set()

    try:
        from lazyllm.tools.tools.search import BochaSearch, TavilySearch
    except Exception as exc:
        return tool_error('ppt_search_web_images', f'search backends unavailable: {exc}')

    # Tavily with include_images
    try:
        tavily = TavilySearch()
        if tavily.__key_source__():
            results = tavily.search(q, include_images=True, max_results=n)
            for item in results or []:
                extra = item.get('extra') or {}
                for img in extra.get('images') or []:
                    if isinstance(img, str) and _is_image_url(img) and img not in seen:
                        seen.add(img)
                        urls.append(img)
                    if len(urls) >= n:
                        break
                if len(urls) >= n:
                    break
    except Exception:
        pass

    # Bocha web-search payload often embeds image fields
    if len(urls) < n:
        try:
            engine = BochaSearch()
            if engine.__key_source__():
                api = f'{engine._base_url}/v1/web-search'
                resp = engine._request(
                    'POST',
                    api,
                    headers={'Content-Type': 'application/json'},
                    json={'query': q, 'count': min(max(n, 1), 20)},
                    timeout=engine._timeout,
                )
                found: list[str] = []
                _collect_image_urls(resp.json(), found, set())
                for u in found:
                    if u not in seen:
                        seen.add(u)
                        urls.append(u)
                    if len(urls) >= n:
                        break
        except Exception:
            pass

    if not urls:
        return tool_error(
            'ppt_search_web_images',
            f'No image URLs for "{q}". Configure Tavily/Bocha, or pass KB '
            'local_path/image_url into ppt_register_material_images instead.',
        )
    return tool_success('ppt_search_web_images', {
        'query': q,
        'urls': urls[:n],
        'count': min(len(urls), n),
        'next': (
            'Call ppt_register_material_images with '
            '[{"url":..., "caption":..., "source":"web"}, ...] for chosen URLs.'
        ),
    })


def ppt_register_material_images(
    images_json: Union[str, list, None] = None,
    replace: Union[bool, str, None] = False,
) -> dict:
    """Download/copy KB or web images into the workspace for later HTML embedding.

    Call this in collect_materials after kb / web_search / ppt_search_web_images.
    Registered images are auto-attached by ppt_init_deck into
    info_pack.user_assets.reference_images (Pool B). The outline stage assigns
    them via use_image.reference_image_index; page-html copies each into
    images/page_XXX_inherited.* and inserts a foreground <img> in the slide HTML.

    Args:
        images_json (str): JSON array. Each item is a URL string, or an object:
            {url|image_url|local_path|path, caption?, alt?, source?}.
            Prefer local_path from kb image hits; use url from ppt_search_web_images.
        replace (bool): If true, clear previous material images first. Default false
            (append, capped at 12 total).

    Returns:
        On success: count, images (path/caption/source), manifest_path.
    """
    try:
        items = _parse_images_payload(images_json)
    except ValueError as exc:
        return tool_error('ppt_register_material_images', str(exc))
    if not items:
        return tool_error(
            'ppt_register_material_images',
            'images_json is empty — pass KB local_path/image_url or web image urls',
        )

    do_replace = str(replace).strip().lower() in ('1', 'true', 'yes', 'y')
    manifest = {'images': []} if do_replace else _load_material_manifest()
    existing = [x for x in (manifest.get('images') or []) if isinstance(x, dict)]
    room = max(0, 12 - len(existing))
    if room <= 0:
        return tool_error(
            'ppt_register_material_images',
            'already have 12 material images; call with replace=true to reset',
        )

    registered: list[dict] = []
    errors: list[str] = []
    for i, item in enumerate(items[:room]):
        try:
            entry = _stage_one_material_image(item, len(existing) + i)
            existing.append(entry)
            registered.append(entry)
        except Exception as exc:
            errors.append(f'item[{i}]: {exc}')

    if not registered:
        return tool_error(
            'ppt_register_material_images',
            'failed to register any image: ' + '; '.join(errors[:3]),
        )

    manifest['images'] = existing
    manifest['updated_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat(
        timespec='seconds',
    )
    manifest_path = _write_material_manifest(manifest)

    # Persist a compact inventory for the Materials tab / generate_ppt context.
    lines = [
        f'{idx + 1}. [{img.get("source") or "material"}] {img.get("caption") or img.get("alt")}'
        f' → {img.get("path")}'
        for idx, img in enumerate(existing)
    ]
    try:
        _save_artifact(
            key='material_images',
            content_type='text',
            value='\n'.join(lines),
            sort_order=1,
        )
    except Exception:
        pass

    return tool_success('ppt_register_material_images', {
        'count': len(registered),
        'total': len(existing),
        'images': [
            {
                'path': x.get('path'),
                'caption': x.get('caption'),
                'source': x.get('source'),
                'origin': x.get('origin'),
            }
            for x in registered
        ],
        'manifest_path': str(manifest_path),
        'errors': errors or None,
        'note': (
            'ppt_init_deck will attach these into reference_images so outline '
            'can set use_image and page-html inserts them into slide HTML.'
        ),
    })


def ppt_attach_material_images(deck_dir: str) -> dict:
    """Attach workspace material_images into an existing deck's info_pack Pool B.

    Usually unnecessary — ppt_init_deck attaches automatically. Use this if the
    deck was created before collect_materials registered images, or after a
    late ppt_register_material_images call.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck / ppt_find_deck.

    Returns:
        On success: attached count and reference_images paths.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_attach_material_images', str(exc))
    result = _attach_material_images_to_deck(deck)
    if result['attached'] <= 0:
        return tool_error(
            'ppt_attach_material_images',
            'no material images registered — call ppt_register_material_images in collect_materials first',
        )
    return tool_success('ppt_attach_material_images', {
        'deck_dir': str(deck.resolve()),
        'attached': result['attached'],
        'reference_image_count': len(result['reference_images']),
        'reference_images': result['reference_images'],
    })


def ppt_init_deck(
    user_query: str,
    page_count: Union[int, str, None] = 4,
    topic: Optional[str] = None,
    role: Optional[str] = None,
    audience: Optional[str] = None,
    scene: Optional[str] = None,
    style_hint: Optional[str] = None,
    image_source: Optional[str] = None,
    infographic_source: Optional[str] = None,
    ppt_mode: Optional[str] = None,
    key_points_json: Union[str, list, None] = None,
) -> dict:
    """Create deck workspace with task_pack.json + info_pack.json.

    Prefer omitting optional fields instead of passing null. image_source must be
    the string 'none' (not JSON null) when no photos are needed.

    If collect_materials previously called ppt_register_material_images, those
    files are auto-attached into user_assets.reference_images so outline / page-html
    can embed them as foreground slide images (Pool B / use_image).

    Args:
        user_query (str): Full presentation request (required).
        page_count (int): Target slide count (2-12). Default 4.
        topic (str): Short topic; inferred from user_query when empty.
        role (str): Speaker role.
        audience (str): Target audience.
        scene (str): Presentation scene.
        style_hint (str): Optional visual style guidance.
        image_source (str): 'none' | 'ai-gen' | 'web-search'. Default 'none'.
            Material images from collect do NOT require ai-gen/web-search —
            keep 'none' and rely on registered reference_images.
            Never pass null — omit the field or use 'none'.
        infographic_source (str): 'echarts' | 'ai-gen'. Default 'echarts'.
        ppt_mode (str): 'fast' or 'standard'. Default 'fast'.
        key_points_json (str): JSON array string like '["a","b"]', or omit.

    Returns:
        On success: deck_dir, deck_id, page_count, next_stage=preflight,
        material_images_attached.
    """
    if not _RUN_STAGE.exists():
        return tool_error(
            'ppt_init_deck',
            f'PPT runtime missing at {_RUNTIME}. Expected plugins/ppt-plugin/runtime '
            '(vendored SenseNova subset; see README.md).',
        )
    query = _coerce_str(user_query)
    if not query:
        return tool_error('ppt_init_deck', 'user_query is required')

    pages = _coerce_int(page_count, 4, lo=2, hi=12)
    mode = _coerce_str(ppt_mode, 'fast').lower()
    if mode not in ('fast', 'standard'):
        mode = 'fast'
    img_src = _coerce_str(image_source, 'none').lower()
    if img_src not in ('none', 'ai-gen', 'web-search'):
        img_src = 'none'
    info_src = _coerce_str(infographic_source, 'echarts').lower()
    if info_src not in ('echarts', 'ai-gen'):
        info_src = 'echarts'

    if isinstance(key_points_json, list):
        key_points = [str(x) for x in key_points_json][:12]
    else:
        try:
            parsed = json.loads(_coerce_str(key_points_json, '[]') or '[]')
            key_points = [str(x) for x in parsed][:12] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            key_points = []

    topic_text = _coerce_str(topic) or query.split('\n', 1)[0][:80]
    deck_id = f"ppt_{_slugify(topic_text)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    deck_dir = _workspace_root() / 'ppt_decks' / deck_id
    deck_dir.mkdir(parents=True, exist_ok=True)
    (deck_dir / 'pages').mkdir(exist_ok=True)
    (deck_dir / 'images').mkdir(exist_ok=True)

    style = _coerce_str(style_hint)
    enriched = f'{query}\n\n视觉风格参考：\n{style}' if style else query
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

    (deck_dir / 'task_pack.json').write_text(json.dumps({
        'deck_id': deck_id,
        'deck_dir': str(deck_dir.resolve()),
        'ppt_mode': mode,
        'params': {
            'role': _coerce_str(role, '演示讲解者'),
            'audience': _coerce_str(audience, '通用听众'),
            'scene': _coerce_str(scene, '主题分享'),
            'page_count': pages,
            'language': _infer_language(query),
            'image_source': img_src,
            'infographic_source': info_src,
        },
        'created_at': now,
        'skill_version': '0.1.0',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (deck_dir / 'info_pack.json').write_text(json.dumps({
        'user_query': enriched,
        'query_normalized': {'topic': topic_text, 'key_points': key_points},
        'user_assets': {
            'reference_images': [],
            'reference_image_captions': {},
            'reference_docs': [],
            'reference_docs_failed': [],
        },
        'document_digest': None,
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    attached = _attach_material_images_to_deck(deck_dir)

    return tool_success('ppt_init_deck', {
        'deck_dir': str(deck_dir.resolve()),
        'deck_id': deck_id,
        'page_count': pages,
        'ppt_mode': mode,
        'image_source': img_src,
        'material_images_attached': attached['attached'],
        'next_stage': 'preflight',
        'stage_order': _STAGE_ORDER_HINT,
    })


def ppt_find_deck() -> dict:
    """Find newest deck under this SubAgent workspace ppt_decks/.

    Returns:
        On success: deck_dir, deck_id, page_count, html_count.
    """
    root = _workspace_root() / 'ppt_decks'
    if not root.is_dir():
        return tool_error('ppt_find_deck', 'No ppt_decks under workspace; run full generation first.')
    candidates = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / 'task_pack.json').exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return tool_error('ppt_find_deck', 'No deck with task_pack.json found.')
    deck = candidates[0]
    html_count = len([
        p for p in (deck / 'pages').glob('page_*.html') if '.refined.' not in p.name
    ]) if (deck / 'pages').is_dir() else 0
    page_count = 0
    deck_id = deck.name
    try:
        pack = json.loads((deck / 'task_pack.json').read_text(encoding='utf-8'))
        page_count = int((pack.get('params') or {}).get('page_count') or 0)
        deck_id = str(pack.get('deck_id') or deck_id)
    except Exception:
        pass
    return tool_success('ppt_find_deck', {
        'deck_dir': str(deck.resolve()),
        'deck_id': deck_id,
        'page_count': page_count,
        'html_count': html_count,
    })


def ppt_run_stage(
    deck_dir: str,
    stage: str,
    page: int = 0,
    slot: str = '',
    concurrency: int = 2,
    start_page: int = 0,
    end_page: int = 0,
) -> dict:
    """Run one PPT HTML-pipeline stage (plugins/ppt-plugin/runtime).

    LLM stages use AutoModel(model='llm') in-process. Prefer batch-page-html.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck.
        stage (str): preflight|style|outline|asset-plan|gen-image|page-html|
            batch-gen-image|batch-page-html|refine-page|batch-refine-page.
            Export is UI-only — do not pass stage=export.
        page (int): Required for gen-image / page-html / refine-page (1-based).
        slot (str): Required for gen-image.
        concurrency (int): For batch stages (default 2).
        start_page (int): Optional batch-page-html start.
        end_page (int): Optional batch-page-html end.

    Returns:
        Stage status fields from run_stage.
    """
    stage_name = _coerce_str(stage).lower()
    if stage_name == 'export':
        return tool_error(
            'ppt_run_stage',
            'Export is UI-only. Ask the user to click the Export button; '
            'do not run stage=export from the skill.',
        )
    if stage_name not in _VALID_STAGES:
        return tool_error(
            'ppt_run_stage',
            f'Unknown stage {stage!r}. Valid: {", ".join(sorted(_VALID_STAGES))}',
        )
    if not _RUN_STAGE.exists():
        return tool_error('ppt_run_stage', f'run_stage.py missing: {_RUN_STAGE}')

    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_run_stage', str(exc))

    page_no = _coerce_int(page, 0, lo=0)
    conc = _coerce_int(concurrency, 2, lo=1, hi=8)
    sp = _coerce_int(start_page, 0, lo=0)
    ep = _coerce_int(end_page, 0, lo=0)
    slot_id = _coerce_str(slot)

    if stage_name in _INPROCESS_STAGES:
        if stage_name in ('page-html', 'refine-page') and page_no < 1:
            return tool_error('ppt_run_stage', f'{stage_name} requires page>=1')
        payload = _run_stage_inprocess(
            stage_name, deck, page=page_no, concurrency=conc, start_page=sp, end_page=ep,
        )
        return _stage_tool_result(stage_name, payload)

    if stage_name in _IMAGE_STAGES:
        cmd = [sys.executable, str(_RUN_STAGE), stage_name, '--deck-dir', str(deck)]
        if stage_name == 'gen-image':
            if page_no < 1:
                return tool_error('ppt_run_stage', 'gen-image requires page>=1')
            if not slot_id:
                return tool_error('ppt_run_stage', 'gen-image requires slot')
            cmd.extend(['--page', str(page_no), '--slot', slot_id])
        else:
            cmd.extend(['--concurrency', str(conc)])
        try:
            payload = _run_image_stage_cmd(cmd)
        except subprocess.TimeoutExpired:
            return tool_error('ppt_run_stage', f'{stage_name} timed out')
        except Exception as exc:
            return tool_error('ppt_run_stage', f'{stage_name} failed: {exc}')
        return _stage_tool_result(stage_name, payload)

    return tool_error('ppt_run_stage', f'Unhandled stage {stage_name}')


def ppt_list_pages(deck_dir: str) -> dict:
    """List generated HTML pages under deck_dir/pages.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck.

    Returns:
        count and page entries with page, html_path, title_hint.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_list_pages', str(exc))

    items: list[dict[str, Any]] = []
    for path in sorted((deck / 'pages').glob('page_*.html')):
        if '.refined.' in path.name:
            continue
        m = re.match(r'page_(\d+)\.html$', path.name)
        if not m:
            continue
        page_no = int(m.group(1))
        title_hint = ''
        try:
            title_hint = _title_from_html(path.read_text(encoding='utf-8', errors='ignore'))
        except OSError:
            pass
        query_path = path.parent / f'page_{page_no:03d}.query.txt'
        items.append({
            'page': page_no,
            'html_path': str(path.resolve()),
            'query_path': str(query_path.resolve()) if query_path.exists() else None,
            'title_hint': title_hint,
            'bytes': path.stat().st_size,
        })
    return tool_success('ppt_list_pages', {
        'deck_dir': str(deck),
        'count': len(items),
        'pages': items,
    })


def ppt_publish_pages(
    deck_dir: str,
    pages: Optional[Union[str, list, int]] = None,
    with_notes: bool = True,
) -> dict:
    """Publish page HTML from disk into preview_html (+ notes) artifacts.

    Reads pages/page_NNN.html and saves session artifacts directly — does NOT
    return HTML to the model (avoids 16KB tool-result offload / stuck saves).
    Prefer this over ppt_read_page_html + save_artifacts.

    After batch-page-html / page-html, publish usually already ran automatically.
    Call this to republish or to publish selected pages after a partial edit.

    Args:
        deck_dir (str): Absolute deck directory.
        pages: Optional 1-based page number(s). Default publishes all pages on disk.
        with_notes (bool): Also save a short speaker-notes stub per page.

    Returns:
        published page summaries (no HTML bodies).
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_publish_pages', str(exc))
    try:
        require_context()
    except Exception as exc:
        return tool_error('ppt_publish_pages', f'SubAgent context required: {exc}')

    page_list = _parse_page_list(pages)
    result = _publish_pages_from_disk(deck, page_list, with_notes=bool(with_notes))
    if result['published_count'] <= 0:
        return tool_error(
            'ppt_publish_pages',
            'No pages published. Run batch-page-html / page-html first.',
            detail=json.dumps(result, ensure_ascii=False)[:1500],
        )
    return tool_success('ppt_publish_pages', result)


def ppt_read_page_html(deck_dir: str, page: int) -> dict:
    """Inspect one page metadata (does NOT return full HTML).

    Full HTML is too large for the model context and gets offloaded, which used
    to make save_artifacts stuck. Use ppt_publish_pages to put slides into the UI.

    Args:
        deck_dir (str): Absolute deck directory.
        page (int): 1-based page number.

    Returns:
        page, html_path, title_hint, bytes — never the HTML body.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_read_page_html', str(exc))
    page_no = _coerce_int(page, 0)
    if page_no < 1:
        return tool_error('ppt_read_page_html', 'page must be >= 1')

    path = _page_html_path(deck, page_no)
    if not path.exists():
        return tool_error('ppt_read_page_html', f'missing HTML: {path}')

    html = _sanitize_page_html(path.read_text(encoding='utf-8'))
    return tool_success('ppt_read_page_html', {
        'page': page_no,
        'html_path': str(path.resolve()),
        'title_hint': _title_from_html(html),
        'bytes': len(html.encode('utf-8')),
        'note': (
            'HTML body omitted on purpose. Call ppt_publish_pages(deck_dir, pages=page) '
            'to save into preview_html for the UI.'
        ),
    })
