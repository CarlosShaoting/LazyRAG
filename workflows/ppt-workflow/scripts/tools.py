"""PPT workflow tools — HTML slide pipeline for SubAgent.

Preferred high-level pipeline (one tool call each):
  collect (optional): kb / web_search / ppt_search_web_images
    → ppt_register_material_images  (workspace Pool-B images)
  ppt_build_outline(...)   # init → preflight → style → outline → publish_outline
  ppt_generate_pages(...)  # asset-plan → [batch-gen-image] → batch-page-html

Low-level stages (ppt_init_deck / ppt_run_stage / ppt_publish_*) remain for
debug and recovery; prefer the wrappers above for full runs.

Single-page content edit (no full deck rebuild):
  ppt_find_deck → ppt_read_page_outline → ppt_patch_page_outline
    → ppt_edit_page_html                  (exact removal / retext, no LLM redraw)
    or ppt_run_stage(page-html, page=N)   (LLM redraw of that page)

Delete an entire slide (not a bullet):
  ppt_find_deck → ppt_delete_page(deck_dir, page=N)
    renumbers later pages on disk + outline; removes UI list items.

PPTX export is NOT a skill tool — the user clicks Export in WorkflowPanel.
Runtime lives under workflows/ppt-workflow/runtime/ (vendored SenseNova subset).
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
from collections import Counter
from concurrent.futures import as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, List, Optional, Union
from urllib.parse import urlparse

import requests
from lazyllm import ThreadPoolExecutor

from lazymind.chat.engine.subagent.context import require_context
from lazymind.chat.engine.subagent.tools import _resolve_artifact_text, _save_artifact
from lazymind.chat.engine.tools.infra import tool_error, tool_success
from lazymind.chat.service.utils.static_file_url import (
    local_path_from_static_file_url,
)

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
# Vendored SenseNova runtime (not the full skills tree). See workflows/ppt-workflow/README.md.
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


def _conversation_root() -> Path:
    """Root shared by every step task of one conversation.

    SubAgent workspaces are per task (<root>/<user>/<task_id>/), so decks and
    material images written by one step would be invisible to the next step —
    a follow-up single-page edit could not find the deck it must patch, and
    collect_materials images could not be attached at ppt_init_deck. Both live
    here instead, scoped by conversation so nothing leaks across conversations.
    """
    ctx = require_context()
    conversation = _slugify(_coerce_str(getattr(ctx, 'conversation_id', '')), 'no_conversation')
    workspace = Path(ctx.workspace_path) if ctx.workspace_path else None
    base = workspace.parent if workspace and workspace.parent != workspace else Path('/tmp')
    root = base / 'ppt_sessions' / conversation
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
        r'class=["\'][^"\']*'
        r'(?:kpi-title|kpi-label|kpi-value|chart-title|card-title|section-title)'
        r'[^"\']*["\'][^>]*>([\s\S]*?)</',
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


def _paths_for_page(deck: Path, page_no: int) -> list[Path]:
    """All known on-disk artifacts for one 1-based page number."""
    tag = f'page_{page_no:03d}'
    return [
        deck / 'pages' / f'{tag}.html',
        deck / 'pages' / f'{tag}.query.txt',
        deck / 'pages' / f'{tag}.review.md',
        deck / 'pages' / f'{tag}.refined.html',
        deck / 'screenshots' / f'{tag}.png',
    ]


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


def _max_page_no_on_disk(deck: Path) -> int:
    """Highest page number referenced by pages/ or screenshots/ files."""
    nos: set[int] = set(_iter_page_numbers(deck))
    pages_dir = deck / 'pages'
    if pages_dir.is_dir():
        for path in pages_dir.glob('page_*'):
            m = re.match(r'page_(\d+)\.', path.name)
            if m:
                nos.add(int(m.group(1)))
    shots = deck / 'screenshots'
    if shots.is_dir():
        for path in shots.glob('page_*.png'):
            m = re.match(r'page_(\d+)\.png$', path.name)
            if m:
                nos.add(int(m.group(1)))
    return max(nos) if nos else 0


def _workflow_session_id() -> str:
    try:
        import lazyllm
        cfg = lazyllm.globals.get('agentic_config') or {}
    except Exception:
        cfg = {}
    return str(cfg.get('workflow_session_id') or '').strip()


def _delete_ui_slot_item(slot: str, sort_order: int) -> dict[str, Any]:
    """Remove one list-slot item by 1-based sort_order via Go core DELETE."""
    session_id = _workflow_session_id()
    if not session_id:
        return {'slot': slot, 'ok': False, 'skipped': True, 'reason': 'no workflow_session_id'}
    try:
        ctx = require_context()
        order_list = ctx.db.load_slot_order_list(session_id, slot)
    except Exception as exc:
        return {'slot': slot, 'ok': False, 'skipped': True, 'reason': str(exc)}
    if not order_list:
        return {'slot': slot, 'ok': False, 'skipped': True, 'reason': 'empty or non-list slot'}
    if sort_order < 1 or sort_order > len(order_list):
        return {
            'slot': slot,
            'ok': False,
            'skipped': True,
            'reason': f'sort_order {sort_order} out of range (n={len(order_list)})',
        }
    list_index = int(order_list[sort_order - 1])
    try:
        from lazymind.config import config as _cfg
        import httpx
        core_url = str(_cfg['core_api_url']).rstrip('/')
        resp = httpx.delete(
            f'{core_url}/workflow-sessions/{session_id}/slots/{slot}/items/idx/{list_index}',
            timeout=10.0,
        )
    except Exception as exc:
        return {'slot': slot, 'ok': False, 'error': f'request failed: {exc}'}
    if resp.status_code != 200:
        return {
            'slot': slot,
            'ok': False,
            'error': f'Go core returned {resp.status_code}: {resp.text[:200]}',
        }
    return {'slot': slot, 'ok': True, 'list_index': list_index, 'sort_order': sort_order}


def _remove_outline_page(deck: Path, page_no: int) -> dict[str, Any]:
    """Drop page_no from outline.json and shift later page_no values down by 1."""
    outline = _load_outline(deck)
    removed_title = ''
    new_pages: list[dict] = []
    found = False
    for page in outline.get('pages') or []:
        try:
            pno = int(page.get('page_no', 0))
        except (TypeError, ValueError):
            continue
        if pno == page_no:
            found = True
            removed_title = _coerce_str(page.get('title'))
            continue
        entry = dict(page)
        if pno > page_no:
            entry['page_no'] = pno - 1
        new_pages.append(entry)
    if not found:
        raise KeyError(f'outline has no page {page_no}')
    outline['pages'] = new_pages
    if 'page_count' in outline:
        outline['page_count'] = len(new_pages)
    _write_outline(deck, outline)
    return {'removed_title': removed_title, 'remaining': len(new_pages)}


def _remove_asset_plan_page(deck: Path, page_no: int) -> Optional[dict[str, Any]]:
    """Drop page_no from asset_plan.json when present; renumber later pages."""
    path = deck / 'asset_plan.json'
    if not path.exists():
        return None
    try:
        plan = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'ok': False, 'error': 'asset_plan.json unreadable'}
    pages = plan.get('pages')
    if not isinstance(pages, list):
        return None
    new_pages: list[dict] = []
    found = False
    for page in pages:
        if not isinstance(page, dict):
            continue
        try:
            pno = int(page.get('page_no', 0))
        except (TypeError, ValueError):
            continue
        if pno == page_no:
            found = True
            continue
        entry = dict(page)
        if pno > page_no:
            entry['page_no'] = pno - 1
        new_pages.append(entry)
    plan['pages'] = new_pages
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)
    return {'ok': True, 'found': found, 'remaining': len(new_pages)}


def _sync_task_pack_page_count(deck: Path, page_count: int) -> None:
    path = deck / 'task_pack.json'
    if not path.exists():
        return
    try:
        pack = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return
    if not isinstance(pack, dict):
        return
    params = pack.get('params')
    if not isinstance(params, dict):
        params = {}
        pack['params'] = params
    params['page_count'] = int(page_count)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def _delete_page_files_and_renumber(deck: Path, page_no: int) -> dict[str, Any]:
    """Delete on-disk files for page_no; shift higher pages down by 1."""
    removed = []
    for path in _paths_for_page(deck, page_no):
        if path.exists():
            path.unlink()
            removed.append(str(path.resolve()))

    max_no = _max_page_no_on_disk(deck)
    renamed: list[dict[str, str]] = []
    # Ascending rename after delete: page_(k) -> page_(k-1) for k > page_no.
    for old_no in range(page_no + 1, max_no + 1):
        new_no = old_no - 1
        for src in _paths_for_page(deck, old_no):
            if not src.exists():
                continue
            dst = src.parent / src.name.replace(
                f'page_{old_no:03d}', f'page_{new_no:03d}', 1,
            )
            if dst.exists():
                dst.unlink()
            src.rename(dst)
            renamed.append({'from': str(src.resolve()), 'to': str(dst.resolve())})
    return {
        'removed_files': removed,
        'renamed_files': renamed,
        'html_pages_remaining': _iter_page_numbers(deck),
    }


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


_OUTLINE_TEXT_FIELDS = ('title', 'subtitle', 'narrative', 'visual_hints')

# Layout hints often hard-code item counts ('底部横向排列四个指标卡片'). Left stale
# after a delete, the page-html rewriter keeps the old column count and the
# generator invents a filler item, so the deleted entry reappears on the slide.
_COUNT_PHRASE_RE = re.compile(r'(?:\d+|[一二三四五六七八九十两])\s*(?:个|张|栏|列|行|块|项|大)[^，。；\s]{0,6}')

_OUTLINE_OPS_HELP = (
    'Valid ops: delete_bullet(index|match), replace_bullet(index|match, head?, detail?), '
    'insert_bullet(head, detail?, index?), set_bullets(bullets), '
    f'set_field(field={"|".join(_OUTLINE_TEXT_FIELDS)}, value), '
    'delete_data_point(index|match), set_data_points(data_points).'
)


def _outline_path(deck: Path) -> Path:
    return deck / 'outline.json'


def _load_outline(deck: Path) -> dict:
    path = _outline_path(deck)
    if not path.exists():
        raise FileNotFoundError(
            f'outline.json missing in {deck}. Run the outline stage before patching.',
        )
    outline = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(outline.get('pages'), list) or not outline['pages']:
        raise ValueError(f'outline.json has no pages list: {path}')
    return outline


def _write_outline(deck: Path, outline: dict) -> None:
    path = _outline_path(deck)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def _find_outline_page(outline: dict, page_no: int) -> dict:
    for page in outline['pages']:
        try:
            if int(page.get('page_no', -1)) == page_no:
                return page
        except (TypeError, ValueError):
            continue
    available = [str(p.get('page_no')) for p in outline['pages']]
    raise KeyError(f'outline has no page {page_no}. Pages: {", ".join(available)}')


def _bullet_text(entry: Any) -> str:
    if isinstance(entry, dict):
        return f'{_coerce_str(entry.get("head"))} {_coerce_str(entry.get("detail"))}'.strip()
    return _coerce_str(entry)


def _data_point_text(entry: Any) -> str:
    if isinstance(entry, dict):
        return ' '.join(
            _coerce_str(entry.get(key))
            for key in ('label', 'value', 'context')
        ).strip()
    return _coerce_str(entry)


def _as_bullet(value: Any) -> dict:
    """Normalize a bullet payload into the outline {head, detail} shape."""
    if isinstance(value, dict):
        head = _coerce_str(value.get('head'))
        detail = _coerce_str(value.get('detail'))
    else:
        head, detail = _coerce_str(value), ''
    if not head:
        raise ValueError('each bullet requires a non-empty head')
    return {'head': head, 'detail': detail}


def _resolve_entry_index(items: list, op: dict, text_of: Any, label: str) -> int:
    """Resolve op index (1-based, negative counts from the end) or match text."""
    if not items:
        raise ValueError(f'page has no {label} to address')
    raw_index = op.get('index')
    if _coerce_str(raw_index) != '':
        try:
            n = int(raw_index)
        except (TypeError, ValueError):
            raise ValueError(f'index must be an integer, got {raw_index!r}')
        if n == 0:
            raise ValueError('index is 1-based: use 1 for the first item, -1 for the last')
        idx = n - 1 if n > 0 else len(items) + n
        if not 0 <= idx < len(items):
            raise ValueError(f'index {n} out of range: {label} has {len(items)} items')
        return idx
    needle = _coerce_str(op.get('match')).lower()
    if needle:
        for i, entry in enumerate(items):
            if needle in text_of(entry).lower():
                return i
        raise ValueError(f'no {label} entry matches {op.get("match")!r}')
    raise ValueError(f'op needs index or match to address {label}')


def _page_list(page: dict, key: str) -> list:
    items = page.get(key)
    if not isinstance(items, list):
        items = []
        page[key] = items
    return items


def _parse_ops_payload(ops_json: Union[str, list, dict, None]) -> list[dict]:
    if ops_json is None or (isinstance(ops_json, str) and _coerce_str(ops_json) == ''):
        raise ValueError(f'ops_json is required. {_OUTLINE_OPS_HELP}')
    data = json.loads(ops_json) if isinstance(ops_json, str) else ops_json
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError(f'ops_json must be a non-empty JSON list. {_OUTLINE_OPS_HELP}')
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f'each op must be an object, got {type(item).__name__}')
    return data


def _apply_outline_ops(page: dict, ops: list[dict]) -> list[str]:
    """Mutate one outline page in place. Raises ValueError on an invalid op."""
    applied: list[str] = []
    for op in ops:
        name = _coerce_str(op.get('op')).lower().replace('-', '_')
        if name == 'delete_bullet':
            bullets = _page_list(page, 'bullets')
            idx = _resolve_entry_index(bullets, op, _bullet_text, 'bullets')
            removed = bullets.pop(idx)
            applied.append(f'deleted bullet #{idx + 1}: {_bullet_text(removed)[:60]}')
        elif name == 'replace_bullet':
            bullets = _page_list(page, 'bullets')
            idx = _resolve_entry_index(bullets, op, _bullet_text, 'bullets')
            current = bullets[idx]
            entry = _as_bullet(current) if not isinstance(current, dict) else dict(current)
            head, detail = _coerce_str(op.get('head')), _coerce_str(op.get('detail'))
            if not head and not detail:
                raise ValueError('replace_bullet requires head and/or detail')
            if head:
                entry['head'] = head
            if detail:
                entry['detail'] = detail
            bullets[idx] = _as_bullet(entry)
            applied.append(f'replaced bullet #{idx + 1}: {_bullet_text(bullets[idx])[:60]}')
        elif name == 'insert_bullet':
            bullets = _page_list(page, 'bullets')
            entry = _as_bullet(op)
            if _coerce_str(op.get('index')) == '':
                bullets.append(entry)
                position = len(bullets)
            else:
                try:
                    n = int(op['index'])
                except (TypeError, ValueError):
                    raise ValueError(f'index must be an integer, got {op.get("index")!r}')
                if n == 0:
                    raise ValueError('index is 1-based: use 1 to insert first')
                position = n if n > 0 else len(bullets) + n + 2
                if not 1 <= position <= len(bullets) + 1:
                    raise ValueError(
                        f'index {n} out of range: page has {len(bullets)} bullets',
                    )
                bullets.insert(position - 1, entry)
            applied.append(f'inserted bullet #{position}: {_bullet_text(entry)[:60]}')
        elif name == 'set_bullets':
            raw = op.get('bullets')
            if not isinstance(raw, list) or not raw:
                raise ValueError('set_bullets requires a non-empty bullets list')
            page['bullets'] = [_as_bullet(item) for item in raw]
            applied.append(f'set {len(page["bullets"])} bullets')
        elif name == 'set_field':
            field = _coerce_str(op.get('field')).lower()
            if field not in _OUTLINE_TEXT_FIELDS:
                raise ValueError(
                    f'set_field field must be one of {", ".join(_OUTLINE_TEXT_FIELDS)}',
                )
            value = _coerce_str(op.get('value'))
            if not value:
                raise ValueError(f'set_field {field} requires a non-empty value')
            page[field] = value
            applied.append(f'set {field}: {value[:60]}')
        elif name == 'delete_data_point':
            points = _page_list(page, 'data_points')
            idx = _resolve_entry_index(points, op, _data_point_text, 'data_points')
            removed = points.pop(idx)
            applied.append(f'deleted data_point #{idx + 1}: {_data_point_text(removed)[:60]}')
        elif name == 'set_data_points':
            raw = op.get('data_points')
            if not isinstance(raw, list):
                raise ValueError('set_data_points requires a data_points list')
            points = []
            for item in raw:
                if not isinstance(item, dict) or not _coerce_str(item.get('label')):
                    raise ValueError('each data_point requires a label')
                points.append({
                    'label': _coerce_str(item.get('label')),
                    'value': _coerce_str(item.get('value')),
                    'context': _coerce_str(item.get('context')),
                })
            page['data_points'] = points
            applied.append(f'set {len(points)} data_points')
        else:
            raise ValueError(f'unknown op {op.get("op")!r}. {_OUTLINE_OPS_HELP}')
    return applied


def _stale_count_hints(page: dict, ops: list[dict]) -> list[str]:
    """Warn when visual_hints still states a count the page may no longer match."""
    changed_counts = False
    hints_updated = False
    for op in ops:
        name = _coerce_str(op.get('op')).lower().replace('-', '_')
        if name in {'delete_bullet', 'insert_bullet', 'set_bullets',
                    'delete_data_point', 'set_data_points'}:
            changed_counts = True
        elif name == 'set_field' and _coerce_str(op.get('field')).lower() == 'visual_hints':
            hints_updated = True
    if not changed_counts or hints_updated:
        return []
    phrases = _COUNT_PHRASE_RE.findall(_coerce_str(page.get('visual_hints')))
    if not phrases:
        return []
    return [
        f'visual_hints still says "{"、".join(phrases[:3])}" while the page now has '
        f'{len(page.get("bullets") or [])} bullets and '
        f'{len(page.get("data_points") or [])} data_points. If that count is now wrong, '
        'patch visual_hints with set_field before redrawing — otherwise page-html keeps '
        'the old column count and invents a filler item to replace what you deleted.'
    ]


def _outline_page_view(page: dict) -> dict:
    bullets = [
        {'index': i, 'head': _coerce_str(b.get('head')) if isinstance(b, dict) else _coerce_str(b),
         'detail': _coerce_str(b.get('detail')) if isinstance(b, dict) else ''}
        for i, b in enumerate(page.get('bullets') or [], start=1)
    ]
    data_points = [
        {'index': i, **{k: _coerce_str(p.get(k)) for k in ('label', 'value', 'context')}}
        for i, p in enumerate(page.get('data_points') or [], start=1)
        if isinstance(p, dict)
    ]
    return {
        'page': int(page.get('page_no', 0)),
        'page_kind': _coerce_str(page.get('page_kind')),
        'title': _coerce_str(page.get('title')),
        'subtitle': _coerce_str(page.get('subtitle')),
        'narrative': _coerce_str(page.get('narrative')),
        'visual_hints': _coerce_str(page.get('visual_hints')),
        'bullets': bullets,
        'data_points': data_points,
        'use_table': page.get('use_table'),
        'use_image': page.get('use_image'),
        'asset_slot_count': len(page.get('asset_slots') or []),
    }


def _format_slide_outline_brief(page: dict) -> str:
    """Human-editable per-page brief shown in the Outline tab and fed to page-html."""
    view = _outline_page_view(page)
    lines: list[str] = [
        f'第{view["page"]}页',
        f'页面类型：{view["page_kind"] or "content"}',
        f'标题：{view["title"] or "(未命名)"}',
    ]
    if view['subtitle']:
        lines.append(f'副标题：{view["subtitle"]}')
    if view['narrative']:
        lines.append(f'叙事：{view["narrative"]}')
    if view['visual_hints']:
        lines.append(f'版面提示：{view["visual_hints"]}')

    if view['bullets']:
        lines.append('')
        lines.append('要点：')
        for b in view['bullets']:
            detail = f' — {b["detail"]}' if b['detail'] else ''
            lines.append(f'{b["index"]}. {b["head"]}{detail}')

    if view['data_points']:
        lines.append('')
        lines.append('数据点：')
        for p in view['data_points']:
            bits = [p['label'], p['value'], p['context']]
            lines.append(f'{p["index"]}. ' + ' · '.join(x for x in bits if x))

    use_image = view.get('use_image')
    if isinstance(use_image, dict) and use_image:
        lines.append('')
        lines.append(f'配图：{json.dumps(use_image, ensure_ascii=False)}')
    use_table = view.get('use_table')
    if use_table:
        lines.append('')
        lines.append(f'表格：{json.dumps(use_table, ensure_ascii=False)}')

    lines.extend([
        '',
        '请根据以上内容生成完整可渲染的单页 PPT HTML。',
        '保留全部事实、标题、要点数量与数据，不要编造或增减条目。',
        '按版面提示排版；配图/表格字段如存在必须落到页面上。',
    ])
    return '\n'.join(lines).strip()


def _publish_one_slide_outline(deck: Path, page_no: int) -> dict[str, Any]:
    """Save one page brief into the slide_outline list slot."""
    outline = _load_outline(deck)
    page = _find_outline_page(outline, page_no)
    brief = _format_slide_outline_brief(page)
    title = _coerce_str(page.get('title')) or f'第 {page_no} 页'
    save_res = _save_artifact(
        key='slide_outline',
        value=brief,
        content_type='text',
        source_tool='ppt_publish_outline',
        sort_order=page_no,
        caption=title,
    )
    return {
        'page': page_no,
        'ok': True,
        'title_hint': title,
        'chars': len(brief),
        'save': save_res,
    }


def _publish_slide_outlines_from_disk(
    deck: Path,
    pages: Optional[list[int]] = None,
) -> dict[str, Any]:
    outline = _load_outline(deck)
    if pages is None:
        targets = []
        for page in outline.get('pages') or []:
            try:
                targets.append(int(page.get('page_no')))
            except (TypeError, ValueError):
                continue
        targets = sorted(set(n for n in targets if n >= 1))
    else:
        targets = pages

    published: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for page_no in targets:
        try:
            require_context()
            item = _publish_one_slide_outline(deck, page_no)
        except Exception as exc:
            item = {'page': page_no, 'ok': False, 'error': str(exc)}
        if item.get('ok'):
            published.append({
                'page': item['page'],
                'title_hint': item.get('title_hint'),
                'chars': item.get('chars'),
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


def _load_slide_outline_briefs(page_nos: list[int]) -> dict[int, str]:
    """Read UI-authoritative slide_outline briefs (includes human edits)."""
    briefs: dict[int, str] = {}
    try:
        ctx = require_context()
    except Exception:
        return briefs
    for page_no in page_nos:
        try:
            text, _ctype = _resolve_artifact_text(ctx, 'slide_outline', sort_order=page_no)
        except Exception:
            text = None
        if text and str(text).strip():
            briefs[page_no] = str(text).strip()
    return briefs


_VOID_TAGS = frozenset({
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
})

# Structural containers a text-driven delete must never remove.
_PROTECTED_TAGS = frozenset({'html', 'head', 'body', 'style', 'script'})
_PROTECTED_IDS = frozenset({'bg', 'ct'})
_PROTECTED_CLASSES = frozenset({'wrapper'})

# Element kinds that can stand alone as "one item" when no repeated sibling exists.
_ITEM_TAGS = ('li', 'tr', 'td', 'div', 'section', 'article', 'p', 'span')

_GRID_REPEAT_RE = re.compile(
    r'(grid-template-(?:columns|rows)\s*:\s*repeat\(\s*)(\d+)(\s*,)',
)

_HTML_EDIT_OPS_HELP = (
    'Valid ops: delete_node(el|group|class|match, index?), '
    'replace_text(el|match, value, all?).'
)


class _HtmlTree(HTMLParser):
    """Minimal element tree carrying exact source spans (stdlib only).

    Enough to delete or retext one element of an already generated slide without
    re-running the page-html LLM. Not a general HTML5 parser: it tolerates stray
    end tags and unclosed elements, which is all the generated decks contain.
    """

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.html = html
        self._line_starts = [0] + [i + 1 for i, ch in enumerate(html) if ch == '\n']
        self.nodes: list[dict[str, Any]] = []
        self.texts: list[dict[str, Any]] = []
        self._open: list[int] = []
        self.feed(html)
        self.close()
        for node in self.nodes:
            if node['end'] is None:
                node['end'] = len(html)

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs: list) -> None:
        start = self._offset()
        raw = self.get_starttag_text() or f'<{tag}>'
        attr_map = {k: (v or '') for k, v in attrs}
        node = {
            'tag': tag,
            'id': attr_map.get('id', ''),
            'el': attr_map.get('data-el', '').strip(),
            'group': attr_map.get('data-group', '').strip(),
            'classes': attr_map.get('class', '').split(),
            'start': start,
            'open_end': start + len(raw),
            'end': None,
            'parent': self._open[-1] if self._open else None,
            'children': [],
        }
        index = len(self.nodes)
        self.nodes.append(node)
        if node['parent'] is not None:
            self.nodes[node['parent']]['children'].append(index)
        if tag in _VOID_TAGS or raw.rstrip().endswith('/>'):
            node['end'] = node['open_end']
        else:
            self._open.append(index)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self._open) - 1, -1, -1):
            if self.nodes[self._open[depth]]['tag'] != tag:
                continue
            close = self.html.find('>', self._offset())
            end = close + 1 if close != -1 else self._offset()
            for index in self._open[depth:]:
                if self.nodes[index]['end'] is None:
                    self.nodes[index]['end'] = end
            del self._open[depth:]
            return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.texts.append({
                'start': self._offset(),
                'text': data,
                'parent': self._open[-1] if self._open else None,
            })

    def ancestors(self, index: int) -> list[int]:
        chain = []
        parent = self.nodes[index]['parent']
        while parent is not None:
            chain.append(parent)
            parent = self.nodes[parent]['parent']
        return chain

    def is_protected(self, index: int) -> bool:
        node = self.nodes[index]
        return (
            node['tag'] in _PROTECTED_TAGS
            or node['id'] in _PROTECTED_IDS
            or bool(set(node['classes']) & _PROTECTED_CLASSES)
        )

    def inside_raw_text(self, offset: int) -> bool:
        """True when offset falls inside a <style> / <script> body."""
        return any(
            node['tag'] in ('style', 'script') and node['open_end'] <= offset < node['end']
            for node in self.nodes
        )

    def node_text(self, index: int) -> str:
        node = self.nodes[index]
        return _strip_tags(self.html[node['open_end']:node['end']])

    def find_repeated_item(self, index: int) -> int:
        """Walk up to the element that is one item of a repeated group.

        A KPI card lives as `.stat-card` among sibling `.stat-card`s; deleting
        that element (not its inner text node) is what removes the item.
        """
        for candidate in [index] + self.ancestors(index):
            if self.is_protected(candidate):
                break
            if len(self.siblings_like(candidate)) > 1:
                return candidate
        for candidate in [index] + self.ancestors(index):
            if self.is_protected(candidate):
                break
            if self.nodes[candidate]['tag'] in _ITEM_TAGS:
                return candidate
        return index

    def siblings_like(self, index: int) -> list[int]:
        """Siblings sharing this element's tag and class list, including itself."""
        node = self.nodes[index]
        parent = node['parent']
        if parent is None:
            return [index]
        signature = (node['tag'], tuple(node['classes']))
        return [
            sibling for sibling in self.nodes[parent]['children']
            if (self.nodes[sibling]['tag'], tuple(self.nodes[sibling]['classes'])) == signature
        ]


def _shrink_grid_tracks(
    html: str, tree: _HtmlTree, parent: Optional[int], old_count: int, deleted: int = 1,
) -> Optional[str]:
    """Drop tracks from the parent's CSS grid so the row does not keep holes."""
    if parent is None or old_count - deleted < 1:
        return None
    selectors = [f'.{cls}' for cls in tree.nodes[parent]['classes']]
    if tree.nodes[parent]['id']:
        selectors.append(f'#{tree.nodes[parent]["id"]}')
    for selector in selectors:
        for match in re.finditer(re.escape(selector) + r'\s*\{([^}]*)\}', html):
            body = match.group(1)
            hit = _GRID_REPEAT_RE.search(body)
            if not hit or int(hit.group(2)) != old_count:
                continue
            new_body = (
                body[:hit.start()] + hit.group(1) + str(old_count - deleted) + hit.group(3)
                + body[hit.end():]
            )
            return html[:match.start(1)] + new_body + html[match.end(1):]
    return None


def _text_occurrences(tree: _HtmlTree, needle: str) -> list[int]:
    """Offsets of needle inside rendered text (never markup, CSS or JS)."""
    found: list[int] = []
    start = 0
    while True:
        at = tree.html.find(needle, start)
        if at < 0:
            return found
        start = at + 1
        open_bracket = tree.html.rfind('<', 0, at)
        close_bracket = tree.html.rfind('>', 0, at)
        if open_bracket > close_bracket or tree.inside_raw_text(at):
            continue
        found.append(at)


def _delete_span(html: str, start: int, end: int) -> str:
    """Cut [start, end) plus the blank line it leaves behind."""
    tail = end
    while tail < len(html) and html[tail] in ' \t':
        tail += 1
    if tail < len(html) and html[tail] == '\n':
        tail += 1
        head = start
        while head > 0 and html[head - 1] in ' \t':
            head -= 1
        start = head
    return html[:start] + html[tail:]


def _element_inventory(tree: _HtmlTree) -> dict[str, Any]:
    """Addressable content elements of a slide — the JSON view used for edits.

    Prefers the `data-el` / `data-group` anchors emitted by page-html. Decks
    generated before those existed fall back to repeated class groups, which is
    what `delete_node(class=..., index=...)` addresses.
    """
    elements = [
        {
            'el': node['el'],
            'group': node['group'] or None,
            'tag': node['tag'],
            'classes': node['classes'] or None,
            'text': tree.node_text(index).strip()[:80],
        }
        for index, node in enumerate(tree.nodes) if node['el']
    ]
    groups: dict[str, list[str]] = {}
    for item in elements:
        if item['group']:
            groups.setdefault(item['group'], []).append(item['el'])
    repeated: list[dict[str, Any]] = []
    if not elements:
        seen: set[tuple] = set()
        for index, node in enumerate(tree.nodes):
            signature = (node['tag'], tuple(node['classes']))
            if not node['classes'] or signature in seen:
                continue
            siblings = tree.siblings_like(index)
            if len(siblings) < 2:
                continue
            seen.add(signature)
            repeated.append({
                'class': node['classes'][0],
                'count': len(siblings),
                'items': [tree.node_text(s).strip()[:40] for s in siblings],
            })
    seen_ids = Counter(item['el'] for item in elements)
    return {
        'elements': elements or None,
        'groups': {k: v for k, v in groups.items() if len(v) > 1} or None,
        'duplicate_ids': sorted(k for k, n in seen_ids.items() if n > 1) or None,
        'repeated_classes': repeated or None,
        'addressing': (
            'delete_node/replace_text accept el (or group) for these ids.'
            if elements else
            'This page predates data-el anchors: address items with class + index, '
            'or redraw it once with page-html to get stable ids.'
        ),
    }


def _known_element_ids(tree: _HtmlTree) -> str:
    ids = [node['el'] for node in tree.nodes if node['el']]
    return ', '.join(ids[:12]) if ids else '(this page has no data-el anchors)'


def _describe_nodes(tree: _HtmlTree, indexes: list[int]) -> str:
    return '; '.join(
        f'{i}='
        + (f'el="{tree.nodes[c]["el"]}" ' if tree.nodes[c]['el'] else '')
        + f'<{tree.nodes[c]["tag"]}'
        + (f'.{".".join(tree.nodes[c]["classes"])}' if tree.nodes[c]['classes'] else '')
        + f'> "{tree.node_text(c).strip()[:40]}"'
        for i, c in enumerate(indexes, start=1)
    )


def _resolve_el(tree: _HtmlTree, el: str, op: dict) -> list[int]:
    """Nodes carrying data-el=`el`, refusing to guess when the id is not unique.

    page-html is told to keep ids unique, but a generator sometimes reuses one
    (e.g. a section label and the first list item both tagged bullet-1). Editing
    or deleting every match would silently hit unrelated content, so require an
    index instead.
    """
    matches = [i for i, node in enumerate(tree.nodes) if node['el'] == el]
    if not matches:
        raise ValueError(f'no element has data-el="{el}". Known: {_known_element_ids(tree)}')
    if len(matches) == 1:
        return matches
    nth = _coerce_int(op.get('index'), 0, lo=1)
    if _coerce_str(op.get('index')) != '':
        if len(matches) < nth:
            raise ValueError(f'el="{el}" matches {len(matches)} elements, no #{nth}')
        return [matches[nth - 1]]
    raise ValueError(
        f'el="{el}" is not unique — {len(matches)} elements carry it, '
        f'pass index to pick one: {_describe_nodes(tree, matches)}',
    )


def _select_delete_targets(tree: _HtmlTree, op: dict) -> list[int]:
    """Resolve one delete_node op to the element(s) it removes.

    Addressing precedence: el (one item) > group (a titled block) > class+index >
    visible text. Ids come from page-html's data-el anchors and never move when
    unrelated content changes, so they are the safe way to say "this one".
    """
    el = _coerce_str(op.get('el'))
    group = _coerce_str(op.get('group'))
    wanted = _coerce_str(op.get('class'))
    needle = _coerce_str(op.get('match'))
    explicit = _coerce_str(op.get('index')) != ''
    nth = _coerce_int(op.get('index'), 1, lo=1)

    if el:
        return _resolve_el(tree, el, op)
    if group:
        matches = [i for i, node in enumerate(tree.nodes) if node['group'] == group]
        if not matches:
            raise ValueError(f'no element has data-group="{group}"')
        return matches
    if wanted:
        matches = [i for i, node in enumerate(tree.nodes) if wanted in node['classes']]
        if len(matches) < nth:
            raise ValueError(
                f'class {wanted!r} matches {len(matches)} elements, no #{nth}',
            )
        return [matches[nth - 1]]
    if not needle:
        raise ValueError('delete_node requires el, group, class or match')

    hits = _text_occurrences(tree, needle)
    if not hits:
        raise ValueError(f'no visible text matches {needle!r}')
    candidates = [_resolve_delete_target(tree, offset) for offset in hits]
    if explicit:
        if len(candidates) < nth:
            raise ValueError(f'{needle!r} appears {len(candidates)} times, no #{nth}')
        return [candidates[nth - 1]]
    repeated = [c for c in candidates if len(tree.siblings_like(c)) > 1]
    if len(repeated) == 1:
        return [repeated[0]]
    if len(candidates) == 1:
        return [candidates[0]]
    raise ValueError(
        f'{needle!r} appears {len(candidates)} times — pass el, or index to pick one: '
        + _describe_nodes(tree, candidates),
    )


def _resolve_delete_target(tree: _HtmlTree, offset: int) -> int:
    """Element a text hit at `offset` should delete: its repeated-item ancestor."""
    holder = max(
        (i for i, node in enumerate(tree.nodes) if node['open_end'] <= offset < node['end']),
        key=lambda i: tree.nodes[i]['start'],
        default=None,
    )
    if holder is None:
        raise ValueError('match is not inside any element')
    return tree.find_repeated_item(holder)


def _drop_emptied_parents(html: str, parent_start: int) -> str:
    """Remove a container left with no content by the deletion."""
    for _ in range(3):
        tree = _HtmlTree(html)
        node = next((n for n in tree.nodes if n['start'] == parent_start), None)
        if node is None:
            return html
        index = tree.nodes.index(node)
        if tree.is_protected(index) or node['children'] or tree.node_text(index).strip():
            return html
        parent_start = tree.nodes[node['parent']]['start'] if node['parent'] is not None else -1
        html = _delete_span(html, node['start'], node['end'])
        if parent_start < 0:
            return html
    return html


def _sync_doc_title(html: str, old: str, new: str, applied: list[str]) -> str:
    """Keep <head><title> in step with a retexted on-slide title.

    The UI page label and title_hint come from <title> (see _title_from_html),
    so leaving it behind makes a renamed slide keep its old name in the deck
    sidebar. Only rewrite it when it still holds exactly the replaced text —
    a <title> that says something else is deliberate.
    """
    if not old or old == new:
        return html
    match = re.search(r'(<title[^>]*>)(.*?)(</title>)', html, re.I | re.S)
    if not match or match.group(2).strip() != old:
        return html
    applied.append(f'synced <title> -> {new!r}')
    return html[:match.start()] + match.group(1) + new + match.group(3) + html[match.end():]


def _apply_html_ops(html: str, ops: list[dict]) -> tuple[str, list[str], list[str], list[str]]:
    """Apply deterministic edits to one page's HTML. Raises ValueError on bad ops.

    Returns (html, applied, layout_notes, removed_texts).
    """
    applied: list[str] = []
    notes: list[str] = []
    removed_texts: list[str] = []
    for op in ops:
        name = _coerce_str(op.get('op')).lower().replace('-', '_')
        if name == 'delete_node':
            tree = _HtmlTree(html)
            targets = _select_delete_targets(tree, op)
            for target in targets:
                if tree.is_protected(target):
                    raise ValueError(
                        f'refusing to delete <{tree.nodes[target]["tag"]}> — it is page '
                        'structure, not a content item',
                    )
            deleted_per_parent: dict[int, list[int]] = {}
            # Delete back-to-front so the spans of earlier elements stay valid.
            for target in sorted(targets, key=lambda i: tree.nodes[i]['start'], reverse=True):
                node = tree.nodes[target]
                removed = tree.node_text(target).strip()
                removed_texts.append(removed)
                html = _delete_span(html, node['start'], node['end'])
                applied.append(
                    'deleted '
                    + (f'el="{node["el"]}" ' if node['el'] else '')
                    + f'<{node["tag"]}'
                    + (f' class="{" ".join(node["classes"])}"' if node['classes'] else '')
                    + f'> containing: {removed[:60]}'
                )
                if node['parent'] is not None:
                    deleted_per_parent.setdefault(node['parent'], []).append(target)
            for parent, removed_children in deleted_per_parent.items():
                old_count = len(tree.siblings_like(removed_children[0]))
                reflowed = _shrink_grid_tracks(
                    html, tree, parent, old_count, len(removed_children),
                )
                if reflowed:
                    html = reflowed
                    notes.append(
                        f'grid tracks reduced {old_count} -> {old_count - len(removed_children)}',
                    )
                    continue
                shrunk = _drop_emptied_parents(html, tree.nodes[parent]['start'])
                if shrunk != html:
                    html = shrunk
                    notes.append('removed the container left empty by the deletion')
        elif name == 'replace_text':
            value = _coerce_str(op.get('value'))
            if not value:
                raise ValueError('replace_text requires value')
            needle = _coerce_str(op.get('match'))
            el = _coerce_str(op.get('el'))
            tree = _HtmlTree(html)
            if el:
                target = _resolve_el(tree, el, op)[0]
                node = tree.nodes[target]
                inner = html[node['open_end']:node['end']]
                body_end = inner.rfind('</')
                body = inner[:body_end] if body_end >= 0 else inner
                if '<' in body.strip():
                    if not needle:
                        raise ValueError(
                            f'el="{el}" wraps nested markup; pass match as well to say which '
                            'text to replace, or target the inner element directly',
                        )
                    if needle not in body:
                        raise ValueError(f'el="{el}" does not contain {needle!r}')
                    start = node['open_end'] + body.index(needle)
                    html = html[:start] + value + html[start + len(needle):]
                    applied.append(f'retexted el="{el}": {needle!r} -> {value!r}')
                    html = _sync_doc_title(html, needle, value, applied)
                else:
                    start = node['open_end']
                    html = html[:start] + value + html[start + len(body):]
                    applied.append(f'retexted el="{el}" -> {value!r}')
                    html = _sync_doc_title(html, body.strip(), value, applied)
            else:
                if not needle:
                    raise ValueError('replace_text requires el or match')
                hits = _text_occurrences(tree, needle)
                if not hits:
                    raise ValueError(f'no visible text matches {needle!r}')
                targets = hits if op.get('all') else hits[:1]
                for offset in reversed(targets):
                    html = html[:offset] + value + html[offset + len(needle):]
                applied.append(f'replaced {needle!r} -> {value!r} ({len(targets)}x)')
        else:
            raise ValueError(f'unknown op {op.get("op")!r}. {_HTML_EDIT_OPS_HELP}')
    return html, applied, notes, removed_texts


def _outline_still_has(deck: Path, page_no: int, removed_texts: list[str]) -> list[str]:
    """Words removed from the slide that the page outline still carries."""
    if not removed_texts:
        return []
    try:
        blob = json.dumps(
            _find_outline_page(_load_outline(deck), page_no), ensure_ascii=False,
        )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
        return []
    stale = []
    for text in removed_texts:
        for token in re.split(r'\s+', text):
            if len(token) >= 2 and token in blob and token not in stale:
                stale.append(token)
    return stale


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
    concurrency: int = 4,
    start_page: int = 0,
    end_page: int = 0,
) -> dict:
    """Generate pages concurrently; publish to UI in page order as soon as ready.

    Prefer each page's slide_outline artifact (including human UI edits) as the
    HTML-generator brief. Fall back to the deterministic outline.json path when
    a brief is missing.
    """
    mc, rs = _load_sn_ppt_modules()
    page_nos = _outline_page_numbers(deck, start_page, end_page)
    if not page_nos:
        return {'status': 'failed', 'error': 'no pages in outline matching range', 'stage': 'page-html'}

    briefs = _load_slide_outline_briefs(page_nos)
    mc.set_llm_impl(_agent_llm_call)
    workers = max(1, min(int(concurrency or 4), 8))
    results: dict[int, dict[str, Any]] = {}
    published: list[dict[str, Any]] = []
    ready_ok: dict[int, bool] = {}
    next_publish_i = 0

    def _run_one(pno: int) -> tuple[int, dict]:
        brief = briefs.get(pno)
        if brief:
            return rs._capture_cmd(rs.cmd_page_html_from_brief, deck, pno, brief)
        return rs._capture_cmd(rs.cmd_page_html, deck, pno)

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
            future_map = {ex.submit(_run_one, pno): pno for pno in page_nos}
            for fut in as_completed(future_map):
                pno = future_map[fut]
                try:
                    code, payload = fut.result()
                except Exception as exc:
                    code, payload = 1, {'status': 'failed', 'error': str(exc)}
                if not isinstance(payload, dict):
                    payload = {'status': 'failed', 'error': 'empty page payload'}
                ok = code == 0 and payload.get('status', 'ok' if code == 0 else 'failed') == 'ok'
                results[pno] = {
                    'page': pno,
                    'ok': ok,
                    'payload': payload,
                    'brief_source': 'slide_outline' if pno in briefs else 'outline.json',
                }
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
        'briefs_used': len(briefs),
        'briefs_missing': [p for p in page_nos if p not in briefs] or None,
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
    concurrency: int = 4,
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
            briefs = _load_slide_outline_briefs([page])
            brief = briefs.get(page)
            if brief:
                code, payload = rs._capture_cmd(rs.cmd_page_html_from_brief, deck, page, brief)
            else:
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
                if isinstance(payload, dict):
                    payload['brief_source'] = 'slide_outline' if brief else 'outline.json'
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
    root = _conversation_root() / _MATERIAL_DIR_NAME
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
    """Create a NEW deck workspace with task_pack.json + info_pack.json.

    Prefer ppt_build_outline for a full outline run (it calls this then
    preflight/style/outline/publish). Use this alone only when debugging.

    Only for building a deck from scratch. Never call this to edit an existing
    deck: it starts an empty deck, so every page the user already accepted has to
    be redrawn. To change a page, call ppt_find_deck then ppt_patch_page_outline
    plus ppt_run_stage(stage='page-html', page=N).

    Prefer omitting optional fields instead of passing null. image_source must be
    the string 'none' (not JSON null) when no photos are needed.

    If collect_materials previously called ppt_register_material_images, those
    files are auto-attached into user_assets.reference_images so outline / page-html
    can embed them as foreground slide images (Pool B / use_image).

    Args:
        user_query (str): Full presentation request (required).
        page_count (int): Target slide count (1-12). Default 4.
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
            f'PPT runtime missing at {_RUNTIME}. Expected workflows/ppt-workflow/runtime '
            '(vendored SenseNova subset; see README.md).',
        )
    query = _coerce_str(user_query)
    if not query:
        return tool_error('ppt_init_deck', 'user_query is required')

    pages = _coerce_int(page_count, 4, lo=1, hi=12)
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
    deck_dir = _conversation_root() / 'ppt_decks' / deck_id
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
    """Find the newest deck of this conversation, including earlier step tasks.

    Call this at the start of any edit of an existing deck. Decks are shared
    across the conversation's step tasks, so a deck built by an earlier
    generate_ppt run is found here.

    Returns:
        On success: deck_dir, deck_id, page_count, html_count.
        On error: no deck exists for this conversation yet — only then is full
        generation via ppt_init_deck appropriate.
    """
    root = _conversation_root() / 'ppt_decks'
    candidates = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / 'task_pack.json').exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if root.is_dir() else []
    if not candidates:
        return tool_error(
            'ppt_find_deck',
            'No deck exists for this conversation yet; run full generation first.',
        )
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
        'older_deck_count': len(candidates) - 1,
    })


def _tool_failed(resp: Any) -> bool:
    return not isinstance(resp, dict) or not resp.get('success')


def _tool_payload(resp: Any) -> dict:
    if not isinstance(resp, dict):
        return {}
    result = resp.get('result')
    return result if isinstance(result, dict) else {}


def _tool_fail_reason(resp: Any) -> str:
    if not isinstance(resp, dict):
        return 'empty tool response'
    err = resp.get('error')
    if isinstance(err, dict):
        return str(err.get('reason') or err.get('detail') or 'failed')
    if err:
        return str(err)
    return 'failed'


def _deck_image_source(deck: Path) -> str:
    try:
        pack = json.loads((deck / 'task_pack.json').read_text(encoding='utf-8'))
        src = _coerce_str((pack.get('params') or {}).get('image_source'), 'none').lower()
        return src if src in ('none', 'ai-gen', 'web-search') else 'none'
    except Exception:
        return 'none'


def _asset_plan_pending_slots(deck: Path) -> int:
    path = deck / 'asset_plan.json'
    if not path.exists():
        return 0
    try:
        plan = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return 0
    pending = 0
    for page in plan.get('pages') or []:
        if not isinstance(page, dict):
            continue
        for slot in page.get('slots') or []:
            if not isinstance(slot, dict):
                continue
            if slot.get('status') == 'ok':
                continue
            if _coerce_str(slot.get('id') or slot.get('slot_id')):
                pending += 1
    return pending


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _NULLISH or text == '':
        return None
    if text in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if text in ('0', 'false', 'no', 'n', 'off'):
        return False
    return None


def ppt_build_outline(
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
    """Build a full deck outline in one call (preferred for build_outline step).

    Runs the fixed serial pipeline internally:
      ppt_init_deck → preflight → style → outline → ppt_publish_outline

    Prefer this over calling those stages one by one. Do NOT generate HTML here —
    that is ppt_generate_pages / generate_ppt.

    Args:
        user_query (str): Full presentation request (required).
        page_count (int): Target slide count (1-12). Default 4.
        topic (str): Short topic; inferred from user_query when empty.
        role (str): Speaker role.
        audience (str): Target audience.
        scene (str): Presentation scene.
        style_hint (str): Optional visual style guidance.
        image_source (str): 'none' | 'ai-gen' | 'web-search'. Default 'none'.
            Keep 'none' when using registered material images from collect.
        infographic_source (str): 'echarts' | 'ai-gen'. Default 'echarts'.
        ppt_mode (str): 'fast' or 'standard'. Default 'fast'.
        key_points_json (str): JSON array string like '["a","b"]', or omit.

    Returns:
        deck_dir, stages summary, and publish counts. slide_outline is already
        saved for the Outline tab — stop after success.
    """
    init_res = ppt_init_deck(
        user_query=user_query,
        page_count=page_count,
        topic=topic,
        role=role,
        audience=audience,
        scene=scene,
        style_hint=style_hint,
        image_source=image_source,
        infographic_source=infographic_source,
        ppt_mode=ppt_mode,
        key_points_json=key_points_json,
    )
    if _tool_failed(init_res):
        return tool_error(
            'ppt_build_outline',
            f'init failed: {_tool_fail_reason(init_res)}',
            detail=json.dumps(init_res, ensure_ascii=False)[:2000],
        )
    init_payload = _tool_payload(init_res)
    deck_dir = str(init_payload.get('deck_dir') or '')
    if not deck_dir:
        return tool_error('ppt_build_outline', 'ppt_init_deck returned no deck_dir')

    stages: list[dict[str, Any]] = [
        {'step': 'init', 'ok': True, 'deck_id': init_payload.get('deck_id')},
    ]

    # Late register recovery: init attaches automatically, but retry once if empty.
    if int(init_payload.get('material_images_attached') or 0) <= 0:
        attach_res = ppt_attach_material_images(deck_dir)
        if not _tool_failed(attach_res):
            stages.append({
                'step': 'attach_material_images',
                'ok': True,
                **{k: v for k, v in _tool_payload(attach_res).items()
                   if k in ('attached', 'reference_image_count')},
            })

    for stage_name in ('preflight', 'style', 'outline'):
        stage_res = ppt_run_stage(deck_dir, stage=stage_name)
        if _tool_failed(stage_res):
            return tool_error(
                'ppt_build_outline',
                f'{stage_name} failed: {_tool_fail_reason(stage_res)}',
                detail=json.dumps({
                    'deck_dir': deck_dir,
                    'stages': stages,
                    'failed_stage': stage_res,
                }, ensure_ascii=False)[:2500],
                meta={'deck_dir': deck_dir, 'failed_stage': stage_name},
            )
        payload = _tool_payload(stage_res)
        stages.append({
            'step': stage_name,
            'ok': True,
            'status': payload.get('status', 'ok'),
            'pages': payload.get('pages'),
        })

    pub_res = ppt_publish_outline(deck_dir)
    if _tool_failed(pub_res):
        return tool_error(
            'ppt_build_outline',
            f'publish_outline failed: {_tool_fail_reason(pub_res)}',
            detail=json.dumps({
                'deck_dir': deck_dir,
                'stages': stages,
                'publish': pub_res,
            }, ensure_ascii=False)[:2500],
            meta={'deck_dir': deck_dir},
        )
    pub_payload = _tool_payload(pub_res)
    stages.append({
        'step': 'publish_outline',
        'ok': True,
        'published_count': pub_payload.get('published_count'),
    })

    return tool_success('ppt_build_outline', {
        'deck_dir': deck_dir,
        'deck_id': init_payload.get('deck_id'),
        'page_count': init_payload.get('page_count'),
        'ppt_mode': init_payload.get('ppt_mode'),
        'image_source': init_payload.get('image_source'),
        'material_images_attached': init_payload.get('material_images_attached'),
        'published_count': pub_payload.get('published_count'),
        'published': pub_payload.get('published'),
        'stages': stages,
        'note': (
            'slide_outline list is published for the Outline tab. '
            'Stop here — call ppt_generate_pages in generate_ppt for HTML.'
        ),
    })


def ppt_generate_pages(
    deck_dir: Optional[str] = None,
    concurrency: Union[int, str, None] = 4,
    gen_images: Union[bool, str, None] = None,
) -> dict:
    """Generate all slide HTML pages from published slide_outline in one call.

    Preferred for the full-deck generate_ppt path. Runs:
      asset-plan → [batch-gen-image if needed] → batch-page-html
    batch-page-html auto-publishes preview_html (+ notes) page-by-page.

    Do NOT call this for single-page edits — use ppt_patch_page_outline /
    ppt_edit_page_html / ppt_run_stage(page-html) instead.
    Do NOT re-run style/outline/init here.

    Args:
        deck_dir (str): Absolute deck directory. Omit to use ppt_find_deck().
        concurrency (int): Parallel page-html workers (default 4, clamped 1-8).
        gen_images (bool): Force/skip batch-gen-image. Omit = auto:
            run only when task_pack.image_source != 'none' and asset_plan has
            pending slots.

    Returns:
        deck_dir, stages summary, page-html ok/failed counts, publish counts.
    """
    resolved = _coerce_str(deck_dir)
    if not resolved:
        found = ppt_find_deck()
        if _tool_failed(found):
            return tool_error(
                'ppt_generate_pages',
                f'no deck_dir and ppt_find_deck failed: {_tool_fail_reason(found)}',
            )
        resolved = str(_tool_payload(found).get('deck_dir') or '')
    try:
        deck = _resolve_deck_dir(resolved)
    except FileNotFoundError as exc:
        return tool_error('ppt_generate_pages', str(exc))
    deck_dir_s = str(deck.resolve())

    conc = _coerce_int(concurrency, 4, lo=1, hi=8)
    stages: list[dict[str, Any]] = []

    plan_res = ppt_run_stage(deck_dir_s, stage='asset-plan')
    if _tool_failed(plan_res):
        return tool_error(
            'ppt_generate_pages',
            f'asset-plan failed: {_tool_fail_reason(plan_res)}',
            detail=json.dumps(plan_res, ensure_ascii=False)[:2000],
            meta={'deck_dir': deck_dir_s},
        )
    plan_payload = _tool_payload(plan_res)
    stages.append({
        'step': 'asset-plan',
        'ok': True,
        'pages': plan_payload.get('pages'),
        'slots': plan_payload.get('slots'),
    })

    pending = _asset_plan_pending_slots(deck)
    img_src = _deck_image_source(deck)
    want_gen = _coerce_optional_bool(gen_images)
    if want_gen is None:
        want_gen = img_src != 'none' and pending > 0

    if want_gen:
        gen_res = ppt_run_stage(deck_dir_s, stage='batch-gen-image', concurrency=min(2, conc))
        if _tool_failed(gen_res):
            return tool_error(
                'ppt_generate_pages',
                f'batch-gen-image failed: {_tool_fail_reason(gen_res)}',
                detail=json.dumps({
                    'deck_dir': deck_dir_s,
                    'stages': stages,
                    'failed': gen_res,
                }, ensure_ascii=False)[:2500],
                meta={'deck_dir': deck_dir_s},
            )
        gen_payload = _tool_payload(gen_res)
        stages.append({
            'step': 'batch-gen-image',
            'ok': True,
            'status': gen_payload.get('status', 'ok'),
            'submitted': gen_payload.get('submitted'),
            'note': gen_payload.get('note'),
        })
    else:
        stages.append({
            'step': 'batch-gen-image',
            'ok': True,
            'status': 'skipped',
            'reason': (
                f'image_source={img_src!r}, pending_slots={pending}'
                if want_gen is not False else 'gen_images=false'
            ),
        })

    html_res = ppt_run_stage(
        deck_dir_s, stage='batch-page-html', concurrency=conc,
    )
    if _tool_failed(html_res):
        return tool_error(
            'ppt_generate_pages',
            f'batch-page-html failed: {_tool_fail_reason(html_res)}',
            detail=json.dumps({
                'deck_dir': deck_dir_s,
                'stages': stages,
                'failed': html_res,
            }, ensure_ascii=False)[:2500],
            meta={'deck_dir': deck_dir_s},
        )
    html_payload = _tool_payload(html_res)
    stages.append({
        'step': 'batch-page-html',
        'ok': True,
        'status': html_payload.get('status', 'ok'),
        'submitted': html_payload.get('submitted'),
        'ok_count': html_payload.get('ok'),
        'failed': html_payload.get('failed'),
        'published_count': html_payload.get('published_count'),
    })

    published_count = int(html_payload.get('published_count') or 0)
    if published_count <= 0 and int(html_payload.get('ok') or 0) > 0:
        pub_res = ppt_publish_pages(deck_dir_s)
        if not _tool_failed(pub_res):
            pub_payload = _tool_payload(pub_res)
            published_count = int(pub_payload.get('published_count') or 0)
            stages.append({
                'step': 'publish_pages',
                'ok': True,
                'published_count': published_count,
            })

    status = html_payload.get('status', 'ok')
    return tool_success('ppt_generate_pages', {
        'deck_dir': deck_dir_s,
        'status': status,
        'concurrency': conc,
        'image_source': img_src,
        'pending_image_slots': pending,
        'submitted': html_payload.get('submitted'),
        'ok': html_payload.get('ok'),
        'failed': html_payload.get('failed'),
        'failed_detail': html_payload.get('failed_detail'),
        'published_count': published_count or html_payload.get('published_count'),
        'published': html_payload.get('published'),
        'stages': stages,
        'note': (
            'preview_html pages published. Stop — do not export PPTX from tools.'
            if status == 'ok' else
            'Some pages failed; inspect failed_detail or redraw with page-html.'
        ),
    })


def ppt_run_stage(
    deck_dir: str,
    stage: str,
    page: int = 0,
    slot: str = '',
    concurrency: int = 4,
    start_page: int = 0,
    end_page: int = 0,
) -> dict:
    """Run one PPT HTML-pipeline stage (workflows/ppt-workflow/runtime).

    For full outline / full HTML runs prefer ppt_build_outline and
    ppt_generate_pages (they chain the fixed stages). Use this for single
    stages, recovery, or single-page page-html / refine-page.

    LLM stages use AutoModel(model='llm') in-process. Prefer batch-page-html
    over many page-html calls when generating the whole deck.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck.
        stage (str): preflight|style|outline|asset-plan|gen-image|page-html|
            batch-gen-image|batch-page-html|refine-page|batch-refine-page.
            Export is UI-only — do not pass stage=export.
        page (int): Required for gen-image / page-html / refine-page (1-based).
        slot (str): Required for gen-image.
        concurrency (int): For batch stages (default 4, clamped to 1-8).
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
    conc = _coerce_int(concurrency, 4, lo=1, hi=8)
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


def ppt_delete_page(deck_dir: str, page: int) -> dict:
    """Delete an entire slide page and renumber later pages.

    Use for whole-page removal such as "删掉第3页" / "去掉封面". This is NOT
    for deleting a bullet or one element — those use ppt_patch_page_outline or
    ppt_edit_page_html on the same page.

    Effects:
      - Removes the page from outline.json / asset_plan.json and shifts later
        page_no values down by 1.
      - Deletes pages/page_NNN.* (+ screenshot) and renames later files.
      - Removes the matching UI list items (slide_outline / preview_html /
        preview_notes) at that sort_order so the Outline and Slides tabs shrink.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck / ppt_find_deck.
        page (int): 1-based page number to delete.

    Returns:
        deleted page summary, remaining page count, UI delete results.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_delete_page', str(exc))

    page_no = _coerce_int(page, 0, lo=0)
    if page_no < 1:
        return tool_error('ppt_delete_page', 'page must be >= 1')

    try:
        outline = _load_outline(deck)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return tool_error('ppt_delete_page', str(exc))

    outline_nos: list[int] = []
    for entry in outline.get('pages') or []:
        try:
            outline_nos.append(int(entry.get('page_no', 0)))
        except (TypeError, ValueError):
            continue
    outline_nos = [n for n in outline_nos if n >= 1]
    disk_nos = _iter_page_numbers(deck)

    if page_no not in outline_nos and page_no not in disk_nos:
        available = sorted(set(outline_nos) | set(disk_nos))
        return tool_error(
            'ppt_delete_page',
            f'page {page_no} not found. Available: {available or "none"}',
        )

    remaining_before = len(outline_nos) if outline_nos else len(disk_nos)
    if remaining_before <= 1:
        return tool_error(
            'ppt_delete_page',
            'Cannot delete the last remaining page. Keep at least one slide.',
        )

    removed_title = ''
    outline_meta: dict[str, Any] = {}
    if page_no in outline_nos:
        try:
            outline_meta = _remove_outline_page(deck, page_no)
            removed_title = outline_meta.get('removed_title') or ''
        except KeyError as exc:
            return tool_error('ppt_delete_page', str(exc))
    else:
        outline_meta = {'remaining': len(outline_nos), 'note': 'page absent from outline.json'}

    asset_meta = _remove_asset_plan_page(deck, page_no)
    disk_meta = _delete_page_files_and_renumber(deck, page_no)

    remaining = int(outline_meta.get('remaining') or len(_iter_page_numbers(deck)))
    _sync_task_pack_page_count(deck, remaining)

    ui_deleted: list[dict[str, Any]] = []
    try:
        require_context()
        for slot in ('slide_outline', 'preview_html', 'preview_notes'):
            ui_deleted.append(_delete_ui_slot_item(slot, page_no))
    except Exception as exc:
        ui_deleted.append({'ok': False, 'skipped': True, 'reason': f'UI sync skipped: {exc}'})

    return tool_success('ppt_delete_page', {
        'deck_dir': str(deck.resolve()),
        'deleted_page': page_no,
        'removed_title': removed_title or None,
        'remaining_pages': remaining,
        'outline': outline_meta,
        'asset_plan': asset_meta,
        'disk': {
            'removed_count': len(disk_meta.get('removed_files') or []),
            'renamed_count': len(disk_meta.get('renamed_files') or []),
            'html_pages': disk_meta.get('html_pages_remaining'),
        },
        'ui': ui_deleted,
        'note': (
            'Later pages were renumbered (old N+1 is now N). '
            'Do not re-run outline/style unless the user asks for a full rebuild.'
        ),
    })


def ppt_publish_outline(
    deck_dir: str,
    pages: Optional[Union[str, list, int]] = None,
) -> dict:
    """Publish outline.json pages into slide_outline list artifacts for the UI.

    Call once after stage=outline. Each page becomes one editable list item
    (sort_order = page number). generate_ppt reads these briefs — including any
    human edits in the Outline tab — when building HTML.

    Args:
        deck_dir (str): Absolute deck directory from ppt_init_deck / ppt_find_deck.
        pages: Optional 1-based page filter. Omit = all outline pages.

    Returns:
        published_count and per-page titles (no full brief bodies).
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_publish_outline', str(exc))
    try:
        require_context()
    except Exception as exc:
        return tool_error('ppt_publish_outline', f'SubAgent context required: {exc}')

    try:
        page_list = _parse_page_list(pages)
    except ValueError as exc:
        return tool_error('ppt_publish_outline', str(exc))

    try:
        result = _publish_slide_outlines_from_disk(deck, page_list)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return tool_error('ppt_publish_outline', str(exc))

    if result.get('published_count', 0) <= 0:
        return tool_error(
            'ppt_publish_outline',
            'No outline pages published. Run ppt_run_stage(stage="outline") first.',
            detail=json.dumps(result, ensure_ascii=False)[:1500],
        )
    return tool_success('ppt_publish_outline', result)


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
    """Inspect one page's addressable elements (does NOT return full HTML).

    Returns the slide as a small JSON element list — each content element with its
    stable `el` id (from page-html's data-el anchors) and a text preview. Read this
    before ppt_edit_page_html to pick the exact element to delete or retext, the
    same way you would filter an element array by id.

    Full HTML is never returned: it is too large for the model context and gets
    offloaded, which used to make save_artifacts stuck. Use ppt_publish_pages to
    put slides into the UI.

    Args:
        deck_dir (str): Absolute deck directory.
        page (int): 1-based page number.

    Returns:
        page, html_path, title_hint, bytes, elements (el / group / tag / text),
        groups, and — for decks generated before data-el existed —
        repeated_classes to address with class + index.
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
        **_element_inventory(_HtmlTree(html)),
        'note': (
            'HTML body omitted on purpose. Call ppt_publish_pages(deck_dir, pages=page) '
            'to save into preview_html for the UI.'
        ),
    })


def ppt_read_page_outline(deck_dir: str, page: int) -> dict:
    """Read one page's outline content (title / bullets / data_points) before editing it.

    Call this FIRST for any single-page content edit, so the requested change can
    be turned into a concrete index — e.g. "删掉最后一个要点" becomes
    delete_bullet with the real bullet count in hand. The payload is small
    (structured outline only, never slide HTML), so it is always safe to read.

    Args:
        deck_dir (str): Absolute deck directory (from ppt_init_deck / ppt_find_deck).
        page (int): 1-based page number.

    Returns:
        page, page_kind, title, subtitle, narrative, visual_hints, 1-based indexed
        bullets and data_points, use_table / use_image, asset_slot_count.

    Next step: call ppt_patch_page_outline to change this page's content, then
    ppt_run_stage(stage='page-html', page=<same page>) to redraw only that page.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_read_page_outline', str(exc))
    page_no = _coerce_int(page, 0, lo=0)
    if page_no < 1:
        return tool_error('ppt_read_page_outline', 'page must be >= 1')

    try:
        outline = _load_outline(deck)
        page_outline = _find_outline_page(outline, page_no)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return tool_error('ppt_read_page_outline', str(exc))

    return tool_success('ppt_read_page_outline', {
        'deck_dir': str(deck),
        **_outline_page_view(page_outline),
    })


def ppt_patch_page_outline(
    deck_dir: str,
    page: int,
    ops_json: Union[str, list, dict, None] = None,
) -> dict:
    """Patch ONE page's outline content in place (single-page content edit).

    Use this for content-level page edits such as "第3页删掉最后一个要点",
    "把第2页第一条改成…", "这一页标题换成…". It edits only the target page of
    outline.json — other pages, style_spec and asset_plan are untouched, and the
    outline stage is NOT re-run.

    Do NOT use ppt_init_deck or ppt_run_stage(stage='outline'/'style') for a
    single-page edit; that rebuilds the whole deck and loses the other pages'
    approved content.

    Args:
        deck_dir (str): Absolute deck directory (from ppt_init_deck / ppt_find_deck).
        page (int): 1-based page number to patch.
        ops_json: JSON list of ops (a single op object is also accepted). Indexes
            are 1-based; a negative index counts from the end (-1 = last item).
            Instead of index, `match` selects the first entry containing that text.
            Supported ops:
              {"op": "delete_bullet", "index": -1}
              {"op": "delete_bullet", "match": "成本"}
              {"op": "replace_bullet", "index": 2, "head": "...", "detail": "..."}
              {"op": "insert_bullet", "head": "...", "detail": "...", "index": 3}
              {"op": "set_bullets", "bullets": [{"head": "...", "detail": "..."}]}
              {"op": "set_field", "field": "title", "value": "..."}
                 field is one of title | subtitle | narrative | visual_hints
              {"op": "delete_data_point", "index": 1}
              {"op": "set_data_points", "data_points": [{"label": "...", "value": "..."}]}

            When removing an item, also fix visual_hints in the same call if it
            states a count ('底部横向排列四个指标卡片'); a stale count makes
            page-html keep the old column count and invent a filler item.

    Returns:
        applied op descriptions, warnings, bullet counts before/after, and the
        patched page view. Nothing is written when any op is invalid.
        Act on every returned warning before redrawing the page.

    Next step (required): ppt_run_stage(stage='page-html', page=<same page>) to
    redraw that page from the patched outline; it auto-publishes preview_html.
    Keep all edits for one page in a single call so the page is redrawn once.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_patch_page_outline', str(exc))
    page_no = _coerce_int(page, 0, lo=0)
    if page_no < 1:
        return tool_error('ppt_patch_page_outline', 'page must be >= 1')

    try:
        ops = _parse_ops_payload(ops_json)
    except (ValueError, json.JSONDecodeError) as exc:
        return tool_error('ppt_patch_page_outline', f'invalid ops_json: {exc}')

    try:
        outline = _load_outline(deck)
        page_outline = _find_outline_page(outline, page_no)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return tool_error('ppt_patch_page_outline', str(exc))

    bullets_before = len(page_outline.get('bullets') or [])
    try:
        applied = _apply_outline_ops(page_outline, ops)
    except ValueError as exc:
        return tool_error(
            'ppt_patch_page_outline',
            f'op rejected, outline unchanged: {exc}',
        )

    bullets_after = len(page_outline.get('bullets') or [])
    if bullets_after == 0:
        return tool_error(
            'ppt_patch_page_outline',
            'refusing to leave the page with zero bullets; keep at least one or '
            'set narrative-driven content explicitly via set_bullets.',
        )

    try:
        _write_outline(deck, outline)
    except OSError as exc:
        return tool_error('ppt_patch_page_outline', f'writing outline.json failed: {exc}')

    outline_pub = None
    try:
        require_context()
        outline_pub = _publish_one_slide_outline(deck, page_no)
    except Exception as exc:
        outline_pub = {'ok': False, 'error': str(exc)}

    warnings = _stale_count_hints(page_outline, ops)
    if bullets_after < 3:
        warnings.append(
            f'page now has {bullets_after} bullets; slides below 3 bullets can render sparse.',
        )
    elif bullets_after > 6:
        warnings.append(
            f'page now has {bullets_after} bullets; above 6 the slide may overflow.',
        )

    return tool_success('ppt_patch_page_outline', {
        'deck_dir': str(deck),
        'applied': applied,
        'warnings': warnings or None,
        'bullets_before': bullets_before,
        'bullets_after': bullets_after,
        'patched_page': _outline_page_view(page_outline),
        'slide_outline_published': bool(outline_pub and outline_pub.get('ok')),
        'next_step': (
            f"ppt_run_stage(deck_dir, stage='page-html', page={page_no}) to redraw "
            'only this page (auto-publishes preview_html).'
        ),
    })


def ppt_edit_page_html(
    deck_dir: str,
    page: int,
    ops_json: Union[str, list, dict, None] = None,
) -> dict:
    """Edit one slide's existing HTML in place, without re-running the page LLM.

    Use this when the user wants a small, exact change to a slide that is already
    correct otherwise — remove one KPI card / bullet / row, or fix a wrong number
    or word. The edit is deterministic: the rest of the page stays byte-identical,
    so nothing else can drift and no filler item can appear. The page is
    republished automatically, so the UI updates.

    Prefer ppt_run_stage(stage='page-html') instead when the page genuinely needs
    redrawing (new layout, added content, "重画好看点").

    Call ppt_read_page_html first to get the element list and pick an `el` id.

    Also patch the outline for the same page (ppt_patch_page_outline) so a later
    redraw keeps the change; this tool warns when the outline still disagrees.

    Args:
        deck_dir (str): Absolute deck directory (from ppt_find_deck).
        page (int): 1-based page number.
        ops_json: JSON list of ops (a single op object is also accepted).
            Address elements by id whenever the page has them — ids do not move
            when other content changes, so this is the reliable form:
              {"op": "delete_node", "el": "kpi-4"}
              {"op": "delete_node", "group": "kpi-3"}
                 Deletes every element of that group (e.g. a small heading plus
                 its body text) in one go.
              {"op": "replace_text", "el": "kpi-2", "value": "256K"}
                 Retexts that element; add match too when it wraps nested markup.
            Fallbacks for decks generated before data-el anchors existed:
              {"op": "delete_node", "class": "stat-card", "index": 4}
              {"op": "delete_node", "match": "36T"}
                 Deletes the item containing that visible text — the enclosing
                 repeated element, not just the text. Ambiguous matches are
                 refused with the candidate list instead of guessing.
              {"op": "replace_text", "match": "128K", "value": "256K"}
                 Add "all": true for every hit.
            A CSS grid on the parent is narrowed by the number of removed items so
            the row keeps no empty cell. match/class only ever address rendered
            content, never CSS, JS or attributes. Page structure
            (html/body/.wrapper/#bg/#ct) is refused.

    Returns:
        applied edits, layout notes, warnings, bytes before/after, publish result.
        Nothing is written when any op fails to resolve.
    """
    try:
        deck = _resolve_deck_dir(deck_dir)
    except FileNotFoundError as exc:
        return tool_error('ppt_edit_page_html', str(exc))
    page_no = _coerce_int(page, 0, lo=0)
    if page_no < 1:
        return tool_error('ppt_edit_page_html', 'page must be >= 1')
    path = _page_html_path(deck, page_no)
    if not path.exists():
        return tool_error(
            'ppt_edit_page_html',
            f'missing {path.name}; run ppt_run_stage(stage="page-html", page={page_no}) first.',
        )
    try:
        ops = _parse_ops_payload(ops_json)
    except (ValueError, json.JSONDecodeError) as exc:
        return tool_error('ppt_edit_page_html', f'invalid ops_json: {exc}')

    original = path.read_text(encoding='utf-8')
    try:
        edited, applied, notes, removed_texts = _apply_html_ops(original, ops)
    except ValueError as exc:
        return tool_error('ppt_edit_page_html', f'op rejected, page unchanged: {exc}')
    if '<html' not in edited.lower() or 'wrapper' not in edited:
        return tool_error(
            'ppt_edit_page_html',
            'edit would break the page skeleton (missing <html> or .wrapper); page unchanged.',
        )

    tmp = path.with_name(path.name + '.tmp')
    try:
        tmp.write_text(edited, encoding='utf-8')
        os.replace(tmp, path)
    except OSError as exc:
        return tool_error('ppt_edit_page_html', f'writing {path.name} failed: {exc}')

    warnings = []
    stale = _outline_still_has(deck, page_no, removed_texts)
    if stale:
        warnings.append(
            f'outline for page {page_no} still contains {", ".join(stale[:5])}. '
            'Patch it with ppt_patch_page_outline, otherwise the next page-html '
            'redraw brings the deleted content back.'
        )

    published = _publish_pages_from_disk(deck, [page_no], with_notes=False)
    return tool_success('ppt_edit_page_html', {
        'deck_dir': str(deck),
        'page': page_no,
        'applied': applied,
        'layout_notes': notes or None,
        'warnings': warnings or None,
        'bytes_before': len(original.encode('utf-8')),
        'bytes_after': len(edited.encode('utf-8')),
        'published_count': published['published_count'],
        'publish_failed': published['failed'],
    })
