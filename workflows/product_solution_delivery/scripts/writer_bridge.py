"""Product-delivery adapters around LazyMind's shared Writer capability."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from lazymind.chat.engine.subagent.context import require_context
from lazymind.chat.engine.subagent.tools import _save_artifact
from lazymind.document_tools import (
    DraftMarkdownStreamEventEmitter,
    WriterCreateToolkit,
    WriterRevisionToolkit,
)


MARKDOWN_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
EVIDENCE_ID = re.compile(r'\b(?:WEB|KB)-\d{3}\b')
EDITABLE_SLOTS = {
    'direction_outline', 'direction_document',
    'design_outline', 'design_document',
    'prd_outline', 'prd_document',
    'review_outline', 'review_document',
    'handoff_outline', 'handoff_document',
}

TEXT_STAGE_CONTRACTS: dict[str, dict[str, Any]] = {
    'direction': {
        'artifact_type': 'direction-brief',
        'source_skill': 'shape-product-direction',
        'default_target': 1400,
        'sections': [
            '先看结论', '用户与问题', '产品价值', '范围与边界',
            '成功判断', '验证计划', '依据与待确认',
        ],
        'boundary': '只定义方向，不提前设计详细机制、页面、技术架构或排期。',
    },
    'design': {
        'artifact_type': 'product-design-spec',
        'source_skill': 'product-design-full-cycle',
        'default_target': 3500,
        'sections': [
            '先看结论', '目标用户与核心场景', '方案如何运作', '功能与规则',
            '页面、交互与文案', '角色与权限', '异常与恢复', '范围与验收',
            '依据与待确认',
        ],
        'boundary': '只决定产品机制和体验，不代替产品定位、技术架构或研发排期。',
    },
    'prd': {
        'artifact_type': 'prd',
        'source_skill': 'write-prd',
        'default_target': 4500,
        'sections': [
            '先看结论', '背景与目标', '用户与场景', '本期范围', '核心流程',
            '需求清单', '业务规则', '页面与交互', '权限与数据', '异常处理',
            '验收标准', '依赖与待确认',
        ],
        'boundary': '表达已确认产品决定；不得静默发明核心机制、技术架构或排期承诺。',
    },
    'review': {
        'artifact_type': 'review-report',
        'source_skill': 'review-product-artifact',
        'default_target': 1800,
        'sections': [
            '先看结论', '必须先解决的问题', '重要改进', '已经做好的部分',
            '修改与复验清单', '依据与待确认',
        ],
        'boundary': '默认只读评审，不静默改写原产物，也不代替用户批准业务决定。',
    },
    'handoff': {
        'artifact_type': 'development-handoff',
        'source_skill': 'prepare-development-handoff',
        'default_target': 3500,
        'sections': [
            '先看结论', '本次实现范围', '功能与流程', '数据与接口',
            '权限与安全', '状态、异常与恢复', '验收清单', '依赖与风险',
            '待研发确认',
        ],
        'boundary': '判断产品信息是否就绪，不代替研发决定架构、工期或发布日期。',
    },
}

RICH_TEXT_STAGE_GUIDANCE = {
    'direction': '优先把问题因果链、方向取舍和真实验证顺序放进对应章节。',
    'design': '优先呈现用户任务流、对象关系、状态迁移和已有界面的前后对照。',
    'prd': '优先呈现主/异常流程、状态迁移、角色权限矩阵和必要的参与者时序。',
    'review': '优先呈现问题影响链、定性风险分布和带编号的真实界面证据。',
    'handoff': '优先呈现模块依赖、交付闸门顺序和需求—页面—验收追溯矩阵。',
}

# Only exact legacy templates are migrated automatically. User-created headings remain authoritative.
LEGACY_STAGE_SECTIONS = {
    'direction': [
        '一句话方向', '背景与证据', '目标用户与场景', '问题与核心任务',
        '目标与成功信号', '范围与非目标', '约束', '关键假设与验证',
        '关键决定与未决问题',
    ],
    'design': [
        '结论与决策范围', '现状与证据边界', '对象关系与状态生命周期',
        '行为规则与权限', '信息架构与命名', '用户流程与异常恢复',
        '界面、状态与文案', '竞品启示的采用与拒绝', '验收场景',
        '风险、条件变化与未决问题',
    ],
    'prd': [
        '文档信息与结论摘要', '背景与目标', '范围与非目标', '用户、角色与权限',
        '领域模型', '状态模型', '用户流程', '功能需求', '页面与交互要求',
        '内容与通知', '数据与可观测性', '非功能约束', '验收标准',
        '依赖、风险与未决问题',
    ],
    'review': [
        '评审对象、版本与范围', '评审结论', 'P0 阻断问题', 'P1 关键问题',
        'P2 改进建议', '已通过的关键检查', '未覆盖范围与剩余风险',
        '修复与复验清单',
    ],
    'handoff': [
        '就绪结论与阻塞摘要', '交付包索引', '版本基线', '范围与场景',
        '产品规格', '体验规格', '验收与追溯矩阵', '资源与依赖清单',
        '开放项与风险', '交付确认清单',
    ],
}

ARTIFACT_TITLES = {
    'direction': '产品方向说明',
    'design': '产品方案',
    'prd': '产品需求文档',
    'review': '产品方案评审报告',
    'handoff': '研发交付文档',
}

READER_FACING_STATUS_LABELS = {
    'draft': '草稿',
    'reviewable': '可评审',
    'proposed': '待确认',
    'accepted': '已确认',
    'reopened': '重新讨论',
    'superseded': '已更新',
    'blocked': '暂不可交付',
    'hard-stop': '必须先确认',
    'not-checked': '尚未检查',
    'null': '尚未建立',
}

READER_FACING_TERM_LABELS = {
    'direction-brief': '产品方向说明',
    'product-design-spec': '产品方案',
    'review-report': '方案评审报告',
    'development-handoff': '研发交付文档',
    'cross_tenant': '跨租户隔离',
    'silent_write': '后台自动写入',
    'high_loss_irreversible': '高损失且不可逆操作',
    'behavior_policy_trust': '规则、权限与信任',
    'journey_interaction_service': '用户流程与服务体验',
    'domain_state': '业务对象与状态',
    'ia_semantics': '信息结构与命名',
    'ui_visual_system': '界面与视觉规范',
    'content_communication': '内容与沟通',
}

STAGE_ALIASES = {
    'direction': 'direction',
    'shape-product-direction': 'direction',
    'design': 'design',
    'product-design-full-cycle': 'design',
    'prd': 'prd',
    'write-prd': 'prd',
    'review': 'review',
    'review-product-artifact': 'review',
    'handoff': 'handoff',
    'prepare-development-handoff': 'handoff',
}

SHARED_UPSTREAM_SLOTS = (
    'upstream_direction', 'upstream_competitive', 'upstream_design',
    'upstream_prd', 'upstream_prototype', 'upstream_review', 'upstream_handoff',
)

UPSTREAM_SLOTS = {
    'direction': SHARED_UPSTREAM_SLOTS,
    'design': ('direction_document', 'competitive_analysis') + SHARED_UPSTREAM_SLOTS,
    'prd': ('design_document',) + SHARED_UPSTREAM_SLOTS,
    'review': (
        'direction_document', 'competitive_analysis', 'design_document',
        'prd_document', 'prototype',
    ) + SHARED_UPSTREAM_SLOTS,
    'handoff': (
        'design_document', 'prd_document', 'prototype', 'review_document',
    ) + SHARED_UPSTREAM_SLOTS,
}

PRODUCT_MATERIAL_SOURCE_SLOTS = frozenset({
    'product_materials', 'reference_sample',
    *SHARED_UPSTREAM_SLOTS,
    *(f'{slot}_view' for slot in SHARED_UPSTREAM_SLOTS),
})
PRODUCT_NON_FILE_SOURCE_SLOTS = frozenset({
    'product_goal', 'requested_stage', 'execution_depth', 'word_target',
    'reference_sample_choice', 'workspace_seed', 'stage_approval',
})


def _workspace_root() -> Path:
    context = require_context()
    if not context.workspace_path:
        raise RuntimeError('The active Workflow workspace is unavailable.')
    root = Path(context.workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_root(name: str) -> Path:
    root = _workspace_root() / 'product-writer' / f'{name}-{uuid.uuid4().hex}'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_text(path: str) -> str:
    source = Path(str(path or '')).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Writer artifact does not exist: {path}')
    return source.read_text(encoding='utf-8')


def _json_value(value: Any, default: Any = None) -> Any:
    current = value
    for _ in range(5):
        if isinstance(current, dict):
            nested = next((
                current[key] for key in ('data', 'text') if key in current
            ), current)
            if nested is current:
                return current
            current = nested
            continue
        if isinstance(current, list):
            return current
        text = re.sub(
            r'^```(?:json)?\s*|\s*```$', '', str(current or '').strip(), flags=re.I,
        )
        if not text:
            return default
        try:
            current = json.loads(text)
        except json.JSONDecodeError:
            return current
    return current


def _json_content_or_path(value: Any, default: Any = None) -> Any:
    """Accept Workflow JSON content or the path of a JSON artifact."""
    if isinstance(value, (dict, list)):
        return _json_value(value, default)
    text = str(value or '').strip()
    if not text:
        return default
    if '\n' not in text and len(text) < 4096 and text[:1] not in {'{', '[', '"'}:
        candidate = Path(text).expanduser()
        try:
            if candidate.is_file():
                text = _read_text(str(candidate))
        except OSError:
            pass
    return _json_value(text, default)


def _text_content_or_path(value: Any) -> str:
    """Accept inline evidence text or the path returned by an earlier Workflow step."""
    text = str(value or '').strip()
    if '\n' not in text and len(text) < 4096 and ('/' in text or '\\' in text):
        candidate = Path(text).expanduser()
        try:
            if candidate.is_file():
                payload = _json_value(_read_text(str(candidate)), '')
                if isinstance(payload, str):
                    return payload.strip()
                return json.dumps(payload, ensure_ascii=False)
        except OSError:
            pass
    payload = _json_value(value, value)
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)


def _read_json(path: str) -> str:
    return json.dumps(_json_value(_read_text(path), {}), ensure_ascii=False)


def _write_json(root: Path, name: str, value: str | Mapping[str, Any] | list[Any]) -> str:
    payload = _json_value(value, {}) if isinstance(value, str) else value
    path = root / f'{name}.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def _write_markdown(root: Path, name: str, value: str) -> str:
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{name} Markdown must not be empty.')
    path = root / f'{name}.md'
    path.write_text(text + '\n', encoding='utf-8')
    return str(path)


def _markdown_body(markdown: str) -> str:
    """Render the canonical Markdown without network or filesystem side effects."""
    try:
        import mistune

        renderer = mistune.HTMLRenderer(escape=True)
        parser = mistune.create_markdown(
            renderer=renderer,
            plugins=['table', 'strikethrough', 'task_lists', 'url'],
        )
        return str(parser(markdown))
    except Exception:
        # Runtime builds without the optional Writer renderer still get a readable,
        # safe HTML representation. The Markdown file remains the canonical source.
        blocks: list[str] = []
        code_lines: list[str] = []
        code_language: str | None = None

        def close_code() -> None:
            nonlocal code_language
            language = re.sub(r'[^A-Za-z0-9_-]', '', code_language or '')
            language_class = f' class="language-{language}"' if language else ''
            blocks.append(f'<pre><code{language_class}>{html_lib.escape(chr(10).join(code_lines))}</code></pre>')
            code_lines.clear()
            code_language = None

        for line in markdown.splitlines():
            fence = re.match(r'^\s*```\s*([A-Za-z0-9_-]*)\s*$', line)
            if fence:
                if code_language is None:
                    code_language = fence.group(1) or 'text'
                else:
                    close_code()
                continue
            if code_language is not None:
                code_lines.append(line)
                continue
            heading = MARKDOWN_HEADING.match(line)
            if heading:
                level = len(heading.group(1))
                blocks.append(f'<h{level}>{html_lib.escape(heading.group(2))}</h{level}>')
            elif line.strip():
                blocks.append(f'<p>{html_lib.escape(line.strip())}</p>')
        if code_language is not None:
            close_code()
        return '\n'.join(blocks)


MERMAID_BLOCK = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>',
    re.IGNORECASE | re.DOTALL,
)


def _diagram_figure(title: str, source: str, inner: str) -> str:
    """Wrap a pre-rendered diagram without requiring browser-side JavaScript."""
    return (
        '<figure class="diagram">'
        '<figcaption class="diagram-head">'
        f'<span>{html_lib.escape(title)}</span>'
        '<span class="diagram-badge">可视化</span>'
        '</figcaption>'
        f'<div class="diagram-body">{inner}</div>'
        '<details class="diagram-source"><summary>查看图表源码</summary>'
        f'<pre>{html_lib.escape(source)}</pre></details>'
        '</figure>'
    )


def _diagram_lines(source: str) -> list[str]:
    return [line.strip() for line in source.splitlines() if line.strip()]


def _render_timeline(source: str) -> str:
    items: list[str] = []
    for line in _diagram_lines(source):
        if re.match(r'^(timeline|title\b)', line, re.IGNORECASE):
            continue
        section = re.match(r'^section\s+(.+)$', line, re.IGNORECASE)
        if section:
            items.append(
                '<div class="timeline-item timeline-section">'
                f'<b>{html_lib.escape(section.group(1))}</b></div>'
            )
            continue
        parts = re.split(r'\s*:\s*', line, maxsplit=1)
        label = html_lib.escape(parts[0])
        detail = html_lib.escape(parts[1] if len(parts) > 1 else '')
        items.append(
            f'<div class="timeline-item"><b>{label}</b><div>{detail}</div></div>'
        )
    if not items:
        return '<p class="diagram-empty">时间轴没有可识别的阶段，请查看下方图表源码。</p>'
    return f'<div class="timeline">{"".join(items)}</div>'


def _render_quadrant(source: str) -> str:
    points: list[tuple[str, float, float]] = []
    for line in _diagram_lines(source):
        match = re.match(
            r'^\s*([^:]+):\s*\[\s*([.\d]+)\s*,\s*([.\d]+)\s*\]', line,
        )
        if not match:
            continue
        points.append((
            match.group(1).strip(),
            max(0.0, min(1.0, float(match.group(2)))),
            max(0.0, min(1.0, float(match.group(3)))),
        ))
    x_match = re.search(r'^\s*x-axis\s+(.+)$', source, re.IGNORECASE | re.MULTILINE)
    y_match = re.search(r'^\s*y-axis\s+(.+)$', source, re.IGNORECASE | re.MULTILINE)
    x_label = html_lib.escape(x_match.group(1).strip() if x_match else '维度一：低 → 高')
    y_label = html_lib.escape(y_match.group(1).strip() if y_match else '维度二：低 → 高')
    point_svg = []
    colors = ('#2563eb', '#0f766e', '#9333ea', '#c2410c')
    for index, (label, x_value, y_value) in enumerate(points):
        cx = 70 + x_value * 640
        cy = 400 - y_value * 370
        point_svg.append(
            f'<g><circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" '
            f'fill="{colors[index % len(colors)]}"/>'
            f'<text x="{cx + 11:.1f}" y="{cy - 10:.1f}">{html_lib.escape(label)}</text></g>'
        )
    if not points:
        point_svg.append(
            '<text x="390" y="220" text-anchor="middle" fill="#92400e">'
            '暂无可识别的坐标点</text>'
        )
    return (
        '<svg class="quadrant-svg" viewBox="0 0 760 470" role="img" '
        'aria-label="四象限坐标图"><title>四象限坐标图</title>'
        '<rect x="70" y="30" width="640" height="370" rx="8" fill="white" stroke="#b8c5d8"/>'
        '<rect x="390" y="30" width="320" height="185" fill="#eff6ff" opacity=".72"/>'
        '<rect x="70" y="215" width="320" height="185" fill="#f0fdfa" opacity=".72"/>'
        '<line x1="390" y1="30" x2="390" y2="400" stroke="#94a3b8"/>'
        '<line x1="70" y1="215" x2="710" y2="215" stroke="#94a3b8"/>'
        f'<text x="390" y="445" text-anchor="middle">{x_label}</text>'
        f'<text x="18" y="215" transform="rotate(-90 18 215)" text-anchor="middle">{y_label}</text>'
        f'{"".join(point_svg)}</svg>'
    )


def _render_sequence(source: str) -> str:
    rows: list[str] = []
    pattern = re.compile(
        r'^\s*([\w\u4e00-\u9fff .-]+?)\s*(?:--?>>?|--?\))\s*'
        r'([\w\u4e00-\u9fff .-]+?)\s*:\s*(.+)$',
    )
    for line in _diagram_lines(source):
        match = pattern.match(line)
        if not match:
            continue
        sender, receiver, message = (html_lib.escape(value.strip()) for value in match.groups())
        rows.append(
            '<div class="sequence-row">'
            f'<div class="sequence-party">{sender}</div>'
            f'<div class="sequence-msg">{message} <span aria-hidden="true">→</span></div>'
            f'<div class="sequence-party">{receiver}</div></div>'
        )
    if not rows:
        return '<p class="diagram-empty">时序图没有可识别的消息，请查看下方图表源码。</p>'
    return f'<div class="sequence">{"".join(rows)}</div>'


def _render_states(source: str) -> str:
    paths: list[str] = []
    pattern = re.compile(
        r'^\s*(\[\*\]|[^\s:]+)\s*-->\s*(\[\*\]|[^\s:]+)(?:\s*:\s*(.+))?$',
    )
    for line in _diagram_lines(source):
        match = pattern.match(line)
        if not match:
            continue
        start, end, label = match.groups()
        start = '开始 / 结束' if start == '[*]' else start
        end = '开始 / 结束' if end == '[*]' else end
        paths.append(
            '<div class="state-path">'
            f'<span class="state">{html_lib.escape(start)}</span>'
            f'<span class="state-edge">→ {html_lib.escape(label or "")}</span>'
            f'<span class="state">{html_lib.escape(end)}</span></div>'
        )
    if not paths:
        return '<p class="diagram-empty">状态图没有可识别的迁移，请查看下方图表源码。</p>'
    return f'<div class="state-grid">{"".join(paths)}</div>'


def _flow_nodes_and_edges(source: str) -> tuple[dict[str, dict[str, str]], list[tuple[str, str]]]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[tuple[str, str]] = []

    def ensure(node_id: str, label: str = '', shape: str = 'rect') -> None:
        current = nodes.get(node_id)
        if current is None:
            nodes[node_id] = {'label': label or node_id, 'shape': shape}
        elif label and current['label'] == node_id:
            current.update(label=label, shape=shape or current['shape'])

    node_pattern = re.compile(
        r'([A-Za-z0-9_]+)\s*(?:\["([^"]+)"\]|\[([^\]]+)\]|'
        r'\("([^"]+)"\)|\(([^)]+)\)|\{"([^"]+)"\}|\{([^}]+)\})',
    )
    for match in node_pattern.finditer(source):
        groups = match.groups()
        label = next((value for value in groups[1:] if value is not None), groups[0])
        ensure(groups[0], label.strip('"\''), 'decision' if groups[5] or groups[6] else 'rect')

    for line in _diagram_lines(source):
        if re.match(r'^(flowchart|graph)\b', line, re.IGNORECASE) or line.startswith('%%'):
            continue
        relation = re.sub(r'\|[^|]*\|', '', line)
        parts = re.split(r'\s*(?:-->|==>|-\.->)\s*', relation)
        if len(parts) < 2:
            continue
        ids: list[str] = []
        for part in parts:
            match = re.match(r'^\s*([A-Za-z0-9_]+)', part)
            if match:
                ids.append(match.group(1))
                ensure(match.group(1))
        for start, end in zip(ids, ids[1:]):
            edge = (start, end)
            if edge not in edges:
                edges.append(edge)
    return nodes, edges


def _render_flow(source: str) -> str:
    nodes, edges = _flow_nodes_and_edges(source)
    if not nodes:
        return '<p class="diagram-empty">图中没有可识别的节点，请查看下方图表源码。</p>'

    direction_match = re.search(r'^\s*(?:flowchart|graph)\s+(LR|RL|TD|TB|BT)\b', source, re.I | re.M)
    direction = (direction_match.group(1).upper() if direction_match else 'TD')
    indegree = {node_id: 0 for node_id in nodes}
    ranks = {node_id: 0 for node_id in nodes}
    for _, end in edges:
        indegree[end] = indegree.get(end, 0) + 1
    queue = [node_id for node_id, count in indegree.items() if count == 0]
    visited: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        visited.add(node_id)
        for start, end in edges:
            if start != node_id:
                continue
            ranks[end] = max(ranks.get(end, 0), ranks.get(start, 0) + 1)
            indegree[end] -= 1
            if indegree[end] == 0:
                queue.append(end)
    last_rank = max(ranks.values(), default=0)
    for node_id in nodes:
        if node_id not in visited:
            last_rank += 1
            ranks[node_id] = last_rank

    levels: dict[int, list[str]] = {}
    for node_id, rank in ranks.items():
        levels.setdefault(rank, []).append(node_id)
    groups = [levels[key] for key in sorted(levels)]
    node_width, node_height, gap_x, gap_y, margin = 210, 72, 54, 54, 34
    max_count = max((len(group) for group in groups), default=1)
    # A long left-to-right chain becomes illegible when the document preview
    # scales it down to the content width. Preserve LR/RL for compact diagrams
    # and switch longer chains to a readable top-to-bottom document layout.
    if direction in {'LR', 'RL'} and len(groups) > 5:
        direction = 'TD'
    horizontal = direction in {'LR', 'RL'}
    if horizontal:
        width = margin * 2 + len(groups) * node_width + max(0, len(groups) - 1) * gap_x
        height = max(300, margin * 2 + max_count * node_height + max(0, max_count - 1) * gap_y)
    else:
        width = max(720, margin * 2 + max_count * node_width + max(0, max_count - 1) * gap_x)
        height = margin * 2 + len(groups) * node_height + max(0, len(groups) - 1) * gap_y

    positions: dict[str, tuple[float, float]] = {}
    for rank_index, group in enumerate(groups):
        if horizontal:
            column_height = len(group) * node_height + max(0, len(group) - 1) * gap_y
            start_y = (height - column_height) / 2
            x = margin + rank_index * (node_width + gap_x)
            if direction == 'RL':
                x = width - margin - node_width - rank_index * (node_width + gap_x)
            for item_index, node_id in enumerate(group):
                positions[node_id] = (x, start_y + item_index * (node_height + gap_y))
        else:
            row_width = len(group) * node_width + max(0, len(group) - 1) * gap_x
            start_x = (width - row_width) / 2
            y = margin + rank_index * (node_height + gap_y)
            if direction == 'BT':
                y = height - margin - node_height - rank_index * (node_height + gap_y)
            for item_index, node_id in enumerate(group):
                positions[node_id] = (start_x + item_index * (node_width + gap_x), y)

    edge_svg: list[str] = []
    for start, end in edges:
        if start not in positions or end not in positions:
            continue
        start_x, start_y = positions[start]
        end_x, end_y = positions[end]
        if horizontal:
            reverse = direction == 'RL'
            x1 = start_x if reverse else start_x + node_width
            x2 = end_x + node_width if reverse else end_x
            y1 = start_y + node_height / 2
            y2 = end_y + node_height / 2
            middle = (x1 + x2) / 2
            path = f'M {x1:.1f} {y1:.1f} C {middle:.1f} {y1:.1f}, {middle:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}'
        else:
            reverse = direction == 'BT'
            y1 = start_y if reverse else start_y + node_height
            y2 = end_y + node_height if reverse else end_y
            x1 = start_x + node_width / 2
            x2 = end_x + node_width / 2
            middle = (y1 + y2) / 2
            path = f'M {x1:.1f} {y1:.1f} C {x1:.1f} {middle:.1f}, {x2:.1f} {middle:.1f}, {x2:.1f} {y2:.1f}'
        edge_svg.append(f'<path class="flow-edge" d="{path}" marker-end="url(#flow-arrow)"/>')

    node_svg: list[str] = []
    for node_id, node in nodes.items():
        x, y = positions[node_id]
        center_x, center_y = x + node_width / 2, y + node_height / 2
        if node['shape'] == 'decision':
            shape = (
                f'<polygon class="flow-node-shape decision" points="{center_x:.1f},{y:.1f} '
                f'{x + node_width:.1f},{center_y:.1f} {center_x:.1f},{y + node_height:.1f} '
                f'{x:.1f},{center_y:.1f}"/>'
            )
        else:
            shape = (
                f'<rect class="flow-node-shape" x="{x:.1f}" y="{y:.1f}" '
                f'width="{node_width}" height="{node_height}" rx="12"/>'
            )
        chars = list(node['label'])
        wrapped: list[str] = []
        while chars and len(wrapped) < 3:
            wrapped.append(''.join(chars[:15]))
            del chars[:15]
        if chars and wrapped:
            wrapped[-1] = wrapped[-1][:13] + '…'
        first_y = center_y - (len(wrapped) - 1) * 10
        tspans = ''.join(
            f'<tspan x="{center_x:.1f}" dy="{0 if index == 0 else 20}">'
            f'{html_lib.escape(line)}</tspan>'
            for index, line in enumerate(wrapped)
        )
        node_svg.append(
            f'<g>{shape}<text class="flow-label" x="{center_x:.1f}" y="{first_y:.1f}" '
            f'text-anchor="middle">{tspans}</text></g>'
        )

    return (
        f'<svg class="flow-svg" viewBox="0 0 {width:.1f} {height:.1f}" role="img" '
        'aria-label="数据流图"><title>数据流图</title><defs>'
        '<marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#5b7fb8"/></marker></defs>'
        f'{"".join(edge_svg)}{"".join(node_svg)}</svg>'
    )


def _render_mermaid_blocks(body: str) -> str:
    """Replace Mermaid code fences with self-contained, sandbox-safe markup."""
    def replace(match: re.Match[str]) -> str:
        source = html_lib.unescape(match.group(1)).strip()
        first = (_diagram_lines(source) or [''])[0].lower()
        try:
            if first.startswith('timeline'):
                return _diagram_figure('时间轴', source, _render_timeline(source))
            if first.startswith('quadrantchart'):
                return _diagram_figure('象限坐标图', source, _render_quadrant(source))
            if first.startswith('sequencediagram'):
                return _diagram_figure('参与者时序图', source, _render_sequence(source))
            if first.startswith('statediagram'):
                return _diagram_figure('状态迁移图', source, _render_states(source))
            return _diagram_figure('数据流图', source, _render_flow(source))
        except (TypeError, ValueError, KeyError, IndexError):
            return _diagram_figure(
                '图表', source,
                '<p class="diagram-error">图表暂未转换，请查看下方图表源码。</p>',
            )
    return MERMAID_BLOCK.sub(replace, body)


def _add_heading_ids_and_toc(body: str) -> tuple[str, str]:
    links: list[str] = []
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        index += 1
        content = match.group(1)
        plain = html_lib.unescape(re.sub(r'<[^>]+>', '', content)).strip()
        section_id = f'section-{index}'
        links.append(f'<a href="#{section_id}">{html_lib.escape(plain)}</a>')
        return f'<h2 id="{section_id}">{content}</h2>'

    rendered = re.sub(r'<h2>(.*?)</h2>', replace, body, flags=re.IGNORECASE | re.DOTALL)
    return rendered, ''.join(links)


HTML_DIAGRAM_SCRIPT = r'''(()=>{
 const doc=document.getElementById('document'),toc=document.getElementById('toc');
 const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 document.querySelectorAll('#document h2').forEach((h,i)=>{h.id='section-'+(i+1);const a=document.createElement('a');a.href='#'+h.id;a.textContent=h.textContent;toc.appendChild(a)});
 const figure=(title,src,inner)=>{const f=document.createElement('figure');f.className='diagram';f.innerHTML='<figcaption class="diagram-head"><span>'+esc(title)+'</span><span class="diagram-badge">可视化</span></figcaption><div class="diagram-body">'+inner+'</div><details class="diagram-source"><summary>查看图表源码</summary><pre>'+esc(src)+'</pre></details>';return f};
 const splitLines=src=>src.split(/\n/).map(x=>x.trim()).filter(Boolean);
 const timeline=src=>{const rows=splitLines(src).filter(x=>!(/^(timeline|title\b)/i.test(x)));return '<div class="timeline">'+rows.map(x=>{if(/^section\s+/i.test(x))return '<div class="timeline-item timeline-section"><b>'+esc(x.replace(/^section\s+/i,''))+'</b></div>';const p=x.split(/\s*:\s*/);return '<div class="timeline-item"><b>'+esc(p.shift())+'</b><div>'+esc(p.join('：'))+'</div></div>'}).join('')+'</div>'};
 const quadrant=src=>{let pts=[];splitLines(src).forEach(line=>{const m=line.match(/^\s*([^:]+):\s*\[\s*([.\d]+)\s*,\s*([.\d]+)\s*\]/);if(m)pts.push([m[1].trim(),Math.max(0,Math.min(1,+m[2])),Math.max(0,Math.min(1,+m[3]))])});const x=(src.match(/x-axis\s+([^\n]+)/i)||[])[1]||'维度一：低 → 高',y=(src.match(/y-axis\s+([^\n]+)/i)||[])[1]||'维度二：低 → 高';return '<svg class="quadrant-svg" viewBox="0 0 760 470" role="img" aria-label="四象限坐标图"><title>四象限坐标图</title><rect x="70" y="30" width="640" height="370" rx="8" fill="white" stroke="#b8c5d8"/><rect x="390" y="30" width="320" height="185" fill="#eff6ff" opacity=".72"/><rect x="70" y="215" width="320" height="185" fill="#f0fdfa" opacity=".72"/><line x1="390" y1="30" x2="390" y2="400" stroke="#94a3b8"/><line x1="70" y1="215" x2="710" y2="215" stroke="#94a3b8"/><text x="390" y="445" text-anchor="middle">'+esc(x)+'</text><text x="18" y="215" transform="rotate(-90 18 215)" text-anchor="middle">'+esc(y)+'</text>'+pts.map((p,i)=>{const cx=70+p[1]*640,cy=400-p[2]*370;return '<g><circle cx="'+cx+'" cy="'+cy+'" r="8" fill="'+(i?'#0f766e':'#2563eb')+'"/><text x="'+(cx+11)+'" y="'+(cy-10)+'">'+esc(p[0])+'</text></g>'}).join('')+'</svg>'};
 const sequence=src=>{const rows=[];splitLines(src).forEach(line=>{const m=line.match(/^\s*([\w\u4e00-\u9fff -]+)\s*-+>>?\s*([\w\u4e00-\u9fff -]+)\s*:\s*(.+)$/);if(m)rows.push(m)});return '<div class="sequence">'+rows.map(m=>'<div class="sequence-row"><div class="sequence-party">'+esc(m[1])+'</div><div class="sequence-msg">'+esc(m[3])+' <span aria-hidden="true">→</span></div><div class="sequence-party">'+esc(m[2])+'</div></div>').join('')+'</div>'};
 const states=src=>{const parts=[];splitLines(src).forEach(line=>{const m=line.match(/^\s*(\[\*\]|[^\s:]+)\s*-->\s*(\[\*\]|[^\s:]+)(?:\s*:\s*(.+))?/);if(m)parts.push('<div class="state-path"><span class="state">'+esc(m[1]==='[*]'?'开始 / 结束':m[1])+'</span><span class="state-edge">→ '+esc(m[3]||'')+'</span><span class="state">'+esc(m[2]==='[*]'?'开始 / 结束':m[2])+'</span></div>')});return '<div class="state-grid">'+parts.join('')+'</div>'};
 const flow=src=>{
   const nodes=new Map(),edges=[];
   const ensure=(id,label,shape)=>{if(!nodes.has(id))nodes.set(id,{id,label:label||id,shape:shape||'rect'});else if(label&&nodes.get(id).label===id)nodes.set(id,{id,label,shape:shape||nodes.get(id).shape})};
   const nodePattern=/([A-Za-z0-9_]+)\s*(?:\["([^"]+)"\]|\[([^\]]+)\]|\("([^"]+)"\)|\(([^)]+)\)|\{"([^"]+)"\}|\{([^}]+)\})/g;
   for(const m of src.matchAll(nodePattern)){const label=m[2]||m[3]||m[4]||m[5]||m[6]||m[7]||m[1];ensure(m[1],label.replace(/^['"]|['"]$/g,''),(m[6]||m[7])?'decision':'rect')}
   splitLines(src).forEach(line=>{
     if(/^(flowchart|graph)\b/i.test(line)||/^%%/.test(line))return;
     const relation=line.replace(/\|[^|]*\|/g,'');
     const parts=relation.split(/\s*(?:-->|==>|-.->)\s*/);
     if(parts.length<2)return;
     const ids=parts.map(part=>{const m=part.trim().match(/^([A-Za-z0-9_]+)/);return m?m[1]:''}).filter(Boolean);
     ids.forEach(id=>ensure(id,id,'rect'));
     for(let i=0;i<ids.length-1;i+=1){if(!edges.some(e=>e[0]===ids[i]&&e[1]===ids[i+1]))edges.push([ids[i],ids[i+1]])}
   });
   if(!nodes.size)return '<p class="diagram-empty">图中没有可识别的节点，请查看下方图表源码。</p>';
   const indegree=new Map([...nodes.keys()].map(id=>[id,0])),rank=new Map([...nodes.keys()].map(id=>[id,0]));
   edges.forEach(([,to])=>indegree.set(to,(indegree.get(to)||0)+1));
   const queue=[...nodes.keys()].filter(id=>indegree.get(id)===0),visited=new Set();
   while(queue.length){const id=queue.shift();visited.add(id);edges.filter(e=>e[0]===id).forEach(([,to])=>{rank.set(to,Math.max(rank.get(to)||0,(rank.get(id)||0)+1));indegree.set(to,indegree.get(to)-1);if(indegree.get(to)===0)queue.push(to)})}
   let lastRank=Math.max(0,...rank.values());
   [...nodes.keys()].filter(id=>!visited.has(id)).forEach(id=>rank.set(id,++lastRank));
   const levels=[];[...nodes.keys()].forEach(id=>{const r=rank.get(id)||0;(levels[r]||(levels[r]=[])).push(id)});
   const groups=levels.filter(Boolean),nodeW=210,nodeH=72,gapX=34,gapY=74,margin=34;
   const maxCount=Math.max(1,...groups.map(g=>g.length)),width=Math.max(720,margin*2+maxCount*nodeW+(maxCount-1)*gapX),height=margin*2+groups.length*nodeH+Math.max(0,groups.length-1)*gapY;
   const pos=new Map();groups.forEach((group,row)=>{const rowWidth=group.length*nodeW+(group.length-1)*gapX;const start=(width-rowWidth)/2;group.forEach((id,col)=>pos.set(id,{x:start+col*(nodeW+gapX),y:margin+row*(nodeH+gapY)}))});
   const wrap=value=>{const chars=Array.from(String(value||''));const lines=[];while(chars.length&&lines.length<3)lines.push(chars.splice(0,15).join(''));if(chars.length)lines[2]=lines[2].slice(0,13)+'…';return lines};
   const edgeSvg=edges.map(([from,to])=>{const a=pos.get(from),b=pos.get(to);if(!a||!b)return '';const x1=a.x+nodeW/2,y1=a.y+nodeH,x2=b.x+nodeW/2,y2=b.y,mid=(y1+y2)/2;return '<path class="flow-edge" d="M '+x1+' '+y1+' C '+x1+' '+mid+', '+x2+' '+mid+', '+x2+' '+y2+'" marker-end="url(#flow-arrow)"/>'}).join('');
   const nodeSvg=[...nodes.values()].map(node=>{const p=pos.get(node.id),cx=p.x+nodeW/2,cy=p.y+nodeH/2;const shape=node.shape==='decision'?'<polygon class="flow-node-shape decision" points="'+cx+','+p.y+' '+(p.x+nodeW)+','+cy+' '+cx+','+(p.y+nodeH)+' '+p.x+','+cy+'"/>':'<rect class="flow-node-shape" x="'+p.x+'" y="'+p.y+'" width="'+nodeW+'" height="'+nodeH+'" rx="12"/>';const lines=wrap(node.label),first=cy-(lines.length-1)*10;return '<g>'+shape+'<text class="flow-label" x="'+cx+'" y="'+first+'" text-anchor="middle">'+lines.map((line,i)=>'<tspan x="'+cx+'" dy="'+(i?20:0)+'">'+esc(line)+'</tspan>').join('')+'</text></g>'}).join('');
   return '<svg class="flow-svg" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="数据流图"><title>数据流图</title><defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#5b7fb8"/></marker></defs>'+edgeSvg+nodeSvg+'</svg>';
 };
 document.querySelectorAll('pre code.language-mermaid').forEach(code=>{try{const src=code.textContent.trim(),first=(splitLines(src)[0]||'').toLowerCase();let name='数据流图',inner=flow(src);if(first.startsWith('timeline')){name='时间轴';inner=timeline(src)}else if(first.startsWith('quadrantchart')){name='象限坐标图';inner=quadrant(src)}else if(first.startsWith('sequencediagram')){name='参与者时序图';inner=sequence(src)}else if(first.startsWith('statediagram')){name='状态迁移图';inner=states(src)}code.parentElement.replaceWith(figure(name,src,inner))}catch(error){const note=document.createElement('p');note.className='diagram-error';note.textContent='图表暂未转换，已保留下方源码。';code.parentElement.before(note)}});
 const expand=document.querySelector('[data-action="expand"]'),collapse=document.querySelector('[data-action="collapse"]');
 if(expand)expand.onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=true);
 if(collapse)collapse.onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=false);
})();'''


def _render_markdown_html(stage: str, markdown_path: str) -> str:
    """Create the default, self-contained interactive view from one Markdown source.

    The renderer deliberately does not ask a second model to rewrite the document.
    Tables, wording, evidence labels and Mermaid sources therefore stay byte-bound to
    the editable Markdown representation. Supported Mermaid relations are rendered
    into accessible SVG/HTML before the sandboxed preview opens.
    """
    markdown = _read_text(markdown_path)
    title = ARTIFACT_TITLES[stage]
    body = _render_mermaid_blocks(_markdown_body(markdown))
    # Models may emit navigation anchors for downstream processors. Mistune escapes
    # them for safety; remove only the exact, anchor-only paragraph from the reader
    # view so it does not appear as noisy literal HTML.
    body = re.sub(
        r'<p>\s*&lt;a\s+id=&quot;[A-Za-z0-9_-]+&quot;&gt;&lt;/a&gt;\s*</p>\s*',
        '', body, flags=re.IGNORECASE,
    )
    body, toc_html = _add_heading_ids_and_toc(body)
    source_json = json.dumps(markdown, ensure_ascii=False).replace('</', '<\\/')
    page = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_lib.escape(title)}</title>
<style>
:root{{--ink:#172033;--muted:#64748b;--line:#dbe3ef;--soft:#f5f8fc;--brand:#2563eb;--accent:#0f766e;--paper:#fff}}
*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
.shell{{max-width:1320px;margin:auto;background:var(--paper);min-height:100vh;box-shadow:0 18px 60px #1e293b14}}
.hero{{padding:44px clamp(24px,4vw,54px) 28px;background:linear-gradient(135deg,#eff6ff,#f0fdfa);border-bottom:1px solid var(--line)}}
.eyebrow{{color:var(--brand);font-weight:700;letter-spacing:.08em}}h1{{font-size:36px;line-height:1.25;margin:.35rem 0 .6rem}}.sub{{margin:0;color:var(--muted)}}
.toolbar{{position:sticky;top:0;z-index:3;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px clamp(24px,4vw,54px);background:#ffffffee;backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
.toolbar-note{{color:var(--muted);font-size:14px}}
.layout{{display:grid;grid-template-columns:minmax(180px,220px) minmax(0,1fr);gap:28px;padding:32px clamp(24px,4vw,54px) 70px}}nav{{position:sticky;top:70px;align-self:start;max-height:calc(100vh - 90px);overflow:auto}}nav a{{display:block;padding:7px 10px;color:#475569;text-decoration:none;border-left:2px solid var(--line)}}nav a:hover{{color:var(--brand);border-color:var(--brand)}}
article{{min-width:0;overflow-wrap:anywhere}}article h1:first-child{{display:none}}h2{{font-size:25px;margin:2.2rem 0 1rem;padding-bottom:.45rem;border-bottom:2px solid var(--ink)}}h3{{font-size:19px;margin-top:1.8rem}}p,li{{color:#334155}}blockquote{{margin:1.2rem 0;padding:.7rem 1rem;border-left:4px solid var(--brand);background:#eff6ff}}
table{{width:100%;border-collapse:collapse;margin:1.2rem 0;display:block;max-width:100%;overflow-x:auto}}th,td{{border:1px solid var(--line);padding:10px 12px;min-width:120px;vertical-align:top}}th{{background:#eef4fb;text-align:left}}code{{background:#eff3f8;padding:.12em .35em;border-radius:4px}}pre{{max-width:100%;overflow:auto;background:#111827;color:#e5e7eb;padding:18px;border-radius:10px}}
.diagram{{margin:1.5rem 0;border:1px solid var(--line);border-radius:14px;background:var(--soft);overflow:hidden}}.diagram-head{{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;padding:11px 16px;background:#eaf1fb;font-weight:700}}.diagram-badge{{font-size:12px;font-weight:600;color:#1d4ed8;background:#fff;border:1px solid #bfd2f4;border-radius:999px;padding:2px 9px}}.diagram-body{{padding:clamp(12px,2vw,20px);overflow-x:auto}}.diagram svg{{display:block;width:100%;max-width:100%;height:auto}}.diagram text{{font-family:inherit;fill:#24324a}}.diagram-source{{padding:0 16px 14px}}.diagram-source pre{{font-size:12px;white-space:pre-wrap}}.diagram-error,.diagram-empty{{padding:12px 16px;border:1px solid #f59e0b;background:#fffbeb;border-radius:10px;color:#92400e}}
.flow-svg{{min-width:0}}.flow-node-shape{{fill:#fff;stroke:#93afd8;stroke-width:1.5}}.flow-node-shape.decision{{fill:#eff6ff;stroke:#5b7fb8}}.flow-edge{{fill:none;stroke:#5b7fb8;stroke-width:2}}.flow-label{{font-size:14px;font-weight:650}}.timeline{{position:relative;display:grid;gap:14px;padding-left:28px}}.timeline:before{{content:"";position:absolute;left:8px;top:6px;bottom:6px;width:2px;background:#8eb1e8}}.timeline-item{{position:relative;background:white;border:1px solid var(--line);border-radius:10px;padding:10px 14px}}.timeline-item:before{{content:"";position:absolute;left:-26px;top:17px;width:10px;height:10px;border-radius:50%;background:var(--brand);box-shadow:0 0 0 4px #dbeafe}}.timeline-item b{{color:var(--brand)}}.timeline-section{{background:#eff6ff}}
.sequence{{display:grid;gap:9px;min-width:560px}}.sequence-row{{display:grid;grid-template-columns:minmax(110px,150px) minmax(180px,1fr) minmax(110px,150px);gap:10px;align-items:center}}.sequence-party{{border:1px solid #99aac2;background:white;border-radius:8px;padding:7px;text-align:center;font-weight:700}}.sequence-msg{{text-align:center;border-bottom:2px solid #6d8fc4;color:#334155}}.state-grid{{display:grid;gap:10px}}.state-path{{display:grid;grid-template-columns:minmax(120px,1fr) minmax(100px,1fr) minmax(120px,1fr);gap:10px;align-items:center}}.state{{padding:10px 14px;border:1px solid #8aa6ce;border-radius:999px;background:white;text-align:center}}.state-edge{{color:#475569;text-align:center}}
img{{max-width:100%;height:auto;border-radius:10px}}.source-note{{margin-top:34px;padding:14px 16px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;color:var(--muted)}}
@media(max-width:980px){{.layout{{display:block}}nav{{position:static;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));max-height:none;margin-bottom:24px}}}}
@media(max-width:620px){{.hero,.toolbar,.layout{{padding-left:18px;padding-right:18px}}h1{{font-size:29px}}button{{flex:1 1 auto}}.diagram-body{{padding:10px}}.sequence{{min-width:500px}}.state-path{{min-width:500px}}}}
@media print{{body{{background:white}}.shell{{box-shadow:none}}.toolbar,nav{{display:none}}.layout{{display:block;padding:10px}}}}
</style>
</head>
<body><main class="shell">
<header class="hero"><span class="eyebrow">共享产品产物 · HTML 交互视图</span><h1>{html_lib.escape(title)}</h1><p class="sub">与 Markdown 内容同源、同版本；图表只表达正文已有关系。</p></header>
<div class="toolbar"><span class="toolbar-note">文档与图表均为离线内容，可在 LazyMind 内直接查看。</span></div>
<div class="layout"><nav aria-label="文档目录" id="toc">{toc_html}</nav><article id="document">{body}<p class="source-note">本页面由同版本 Markdown 确定性渲染；若图形不可用，请以图后的文字说明和 Markdown 正文为准。</p></article></div>
</main>
<script type="application/json" id="markdown-source">{source_json}</script>
</body></html>'''
    root = _run_root('html-document')
    path = root / f'{stage}-document.html'
    path.write_text(page, encoding='utf-8')
    return str(path)


def _stage_contract(stage_id: str) -> dict[str, Any]:
    stage = _normalize_stage_id(stage_id)
    if stage not in TEXT_STAGE_CONTRACTS:
        raise ValueError(f'stage_id must be one of {sorted(TEXT_STAGE_CONTRACTS)}.')
    return TEXT_STAGE_CONTRACTS[stage]


def _normalize_stage_id(stage_id: Any) -> str:
    raw = str(stage_id or '').strip().lower().replace('_', '-')
    return STAGE_ALIASES.get(raw, raw)


def _reader_facing_rules(stage: str) -> str:
    title = ARTIFACT_TITLES[stage]
    technical_allowance = (
        '研发交付阶段可保留接口、数据结构、权限、安全、错误状态和验收所需的专业术语，'
        '但首次出现时必须用一句中文说明其含义。'
        if stage == 'handoff'
        else '面向产品、设计和业务读者，不使用实现层术语替代业务说明。'
    )
    return f"""最终产物的读者是产品、设计和研发协作人员，显示标题必须是“{title}”。
先写读者需要采取行动的结论，再写背景和依据；一个段落只表达一个要点，长内容优先使用短表格或清单。
正文必须把结果和过程分开：方案、需求、流程、规则和验收放在主体；来源、推断方法、资料缺口和待确认项只放在最后的“依据与待确认”类章节。
不得把内部工作流信息写进交付正文，包括 artifact_type、source_skill、Manifest、Workspace、slot、revision_id、content_hash、source_session_id、证据等级、运行状态和工具状态。
不得出现 direction-brief、product-design-spec、review-report、development-handoff、draft、proposed、accepted、reopened、null、E0/E1 或 WEB-NNN/KB-NNN 等内部写法；需要表达时改成自然中文。
不得用【已核验事实】【用户陈述】【推断】【拟议决定】【已接受决定】【未知/待验证】给每个段落加前缀。已确认内容直接写结论；建议集中写成“建议”；未决内容集中写进“待确认”。
若本轮没有外部资料，不要描述“未登记来源”或来源系统，只需在文末写“本轮未使用外部资料，需要数据支持的判断仍待验证”。
{technical_allowance}
{_rich_text_presentation_rules(stage)}"""


def _rich_text_presentation_rules(stage: str) -> str:
    stage_guidance = RICH_TEXT_STAGE_GUIDANCE[stage]
    design_branch_rule = (
        '产品方案只呈现第二层 Router 实际选中的分支：overall_effort=light 时不生成 Heavy '
        '空框、占位或证据区；overall_effort=heavy 时不生成 Light 空框、占位或证据区。'
        '正文不得展示 Light/Heavy、Router 或分支判断过程。'
        if stage == 'design'
        else ''
    )
    return f"""保持用户批准的大纲、标题层级、章节顺序和字段不变；图表只放入最相关的现有章节，
不得新增“可视化”“图表汇总”或“富文本展示”章节，也不得为了配图拆分、合并或重排章节。
根据真实内容关系选择表达：三个以上同构对象使用 GFM 表格；有步骤、分支或依赖时使用 fenced Mermaid flowchart；
有状态转换时使用 stateDiagram-v2；有多角色交互顺序时使用 sequenceDiagram；有真实里程碑时使用 timeline；
有两个定义清楚的取舍维度时使用 quadrantChart，并在没有数值时注明“定性相对位置”。
只有当前项目提供了可访问的真实截图、原型画面或可追溯图表时才使用 Markdown 图片；不得生成装饰图或想象截图。
没有真实日期时只使用 T0、T+1 或阶段顺序，不得编造日期。每张图只回答一个主要问题，节点使用短语，
图后保留一至两句文字说明，使图形无法渲染时仍可理解。图形不能替代规则、异常、验收、依据或待确认项；
不设置机械配图数量，简单结论用重点摘要即可。{stage_guidance}{design_branch_rule}"""


def _present_reader_facing_markdown(stage: str, markdown: str) -> str:
    """Remove workflow vocabulary from a generated business document.

    The Writer prompt owns the semantic rewrite. This deterministic final pass is deliberately
    conservative: it translates leaked control-plane labels without inventing or deleting product
    decisions, and keeps source traceability readable when a real source id is present.
    """
    text = str(markdown or '').strip()
    for internal, readable in READER_FACING_TERM_LABELS.items():
        text = re.sub(rf'`?{re.escape(internal)}`?', readable, text, flags=re.I)
    for internal, readable in READER_FACING_STATUS_LABELS.items():
        text = re.sub(rf'`{re.escape(internal)}`', readable, text, flags=re.I)
        text = re.sub(
            rf'(?<![A-Za-z0-9_-]){re.escape(internal)}(?![A-Za-z0-9_-])',
            readable,
            text,
            flags=re.I,
        )
    prefix_replacements = {
        '【已核验事实】': '',
        '【用户陈述】': '',
        '【推断】': '**判断：**',
        '【拟议决定】': '**建议：**',
        '【已接受决定】': '**已确认：**',
        '【未知/待验证】': '**待确认：**',
        '【未知项】': '**待确认：**',
    }
    for internal, readable in prefix_replacements.items():
        text = text.replace(internal, readable)
    text = re.sub(r'\bWEB-(\d{3})\b', r'公开资料 \1', text)
    text = re.sub(r'\bKB-(\d{3})\b', r'项目资料 \1', text)
    text = re.sub(r'WEB-NNN/KB-NNN|WEB-NNN|KB-NNN', '资料编号', text, flags=re.I)
    text = re.sub(
        r'当前(?:运行|本次运行)[^。\n]*(?:资料编号|公开资料|项目资料)[^。\n]*[。.]?',
        '本轮未使用外部资料，需要数据支持的判断仍待验证。',
        text,
    )
    text = re.sub(
        r'(?:证据强度|证据等级)(?:上限)?\s*(?:为|：|:)\s*E[01][^。\n]*[。.]?',
        '',
        text,
        flags=re.I,
    )
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _runtime_stage() -> str:
    context = require_context()
    step_id = str((context.params or {}).get('step_id') or '').strip().lower()
    match = re.match(
        r'(?:build_(direction|design|prd|review|handoff)_outline|'
        r'write_(direction|design|prd|review|handoff)_document)$',
        step_id,
    )
    return next((value for value in match.groups() if value), '') if match else ''


def _remote_inputs() -> dict[str, Any]:
    values = (require_context().params or {}).get('remote_inputs') or {}
    return values if isinstance(values, dict) else {}


def _remote_path_set() -> set[Path]:
    paths: set[Path] = set()

    def collect(value: Any) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
            return
        if isinstance(value, dict):
            for key in ('path', 'value', 'data'):
                if key in value:
                    collect(value[key])
            return
        text = str(value or '').strip()
        if not text:
            return
        try:
            candidate = Path(text).expanduser().resolve()
            if candidate.is_file():
                paths.add(candidate)
        except OSError:
            return

    for remote_value in _remote_inputs().values():
        collect(remote_value)
    return paths


def _target_words(raw: str, default: int) -> int:
    match = re.search(r'\d+', str(raw or '').replace(',', ''))
    if not match:
        return default
    return max(300, int(match.group()))


def _source_paths(
    value: Any,
    *,
    material_slots: frozenset[str] = frozenset(),
) -> list[str]:
    parsed = _json_content_or_path(value, [])
    if isinstance(parsed, dict):
        parsed = next((
            parsed[key] for key in ('file_list', 'paths', 'files', 'value')
            if key in parsed
        ), [])
    if not isinstance(parsed, list):
        raise ValueError('source_material_paths_json must be a JSON array.')
    workspace = _workspace_root().resolve()
    remote_paths = _remote_path_set()
    remote_inputs = _remote_inputs()
    resolved_slots: set[str] = set()
    paths: list[str] = []
    pending = list(parsed)
    while pending:
        item = pending.pop(0)
        if isinstance(item, (list, tuple)):
            pending[0:0] = list(item)
            continue
        if isinstance(item, dict):
            pending[0:0] = [
                item[key] for key in ('path', 'value', 'data', 'file_list', 'paths', 'files')
                if key in item
            ]
            continue
        raw_path = item
        text = str(raw_path or '').strip()
        if text.startswith('file://'):
            text = text[7:]
        if not text:
            continue
        # Workflow prompts expose bound file inputs as ``slot=path`` so the
        # model can keep the material's role. Strip only declared material-slot
        # prefixes; the path still has to pass the workspace/exact-binding
        # checks below, so an arbitrary key cannot grant file access.
        slot_name, separator, bound_path = text.partition('=')
        if separator and slot_name.strip() in material_slots:
            text = bound_path.strip()
            if not text:
                continue
        # Models occasionally copy an input-slot label from the prompt instead of
        # the slot's bound path. Resolve a declared material slot through the
        # authoritative Workflow bindings, and treat an unbound optional slot as
        # absent. Never resolve arbitrary strings this way: real paths still pass
        # through the strict workspace/binding checks below.
        if text in material_slots:
            if text in resolved_slots:
                continue
            resolved_slots.add(text)
            bound_value = remote_inputs.get(text)
            if bound_value not in (None, '', []):
                pending.insert(0, bound_value)
            continue
        # The parent Router exposes both scalar/JSON inputs and file inputs.
        # Some small models copy every input-slot label into the file list.
        # Known non-file labels are metadata, never paths, so ignoring them is
        # both deterministic and safer than resolving them relative to the app.
        if material_slots and text in PRODUCT_NON_FILE_SOURCE_SLOTS:
            continue
        path = Path(text).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Product source material does not exist: {path}')
        try:
            path.relative_to(workspace)
        except ValueError:
            if path not in remote_paths:
                raise ValueError(
                    'Source material must be in this workspace or an exact bound Workflow input.'
                )
        paths.append(str(path))
    return list(dict.fromkeys(paths))


def _preserve_business_contract(
    writing_context_json: str,
    stage_id: str,
    contract: dict[str, Any],
    research_evidence: str,
    design_routing_record: Mapping[str, Any] | None = None,
) -> str:
    context = _json_value(writing_context_json, {})
    if not isinstance(context, dict):
        context = {}
    facts = [
        fact for fact in list(context.get('facts') or [])
        if not isinstance(fact, dict) or fact.get('fact_id') != 'product-stage-contract'
    ]
    contract_value = {
        'stage_id': stage_id,
        'artifact_type': contract['artifact_type'],
        'source_skill': contract['source_skill'],
        'required_sections': contract['sections'],
        'boundary': contract['boundary'],
        'registered_evidence': str(research_evidence or '').strip(),
    }
    if stage_id == 'design' and design_routing_record:
        contract_value['design_routing_record'] = dict(design_routing_record)
    facts.append({
        'fact_id': 'product-stage-contract',
        'key': 'product_stage_contract_and_registered_evidence',
        # Shared Writer's DocumentFact schema requires a string value. Keep the
        # business contract structured without violating that generic contract.
        'value': json.dumps(contract_value, ensure_ascii=False),
        'source': ['product-solution-delivery', 'web_search', 'selected_knowledge_bases'],
        'applies_to': [],
        'locked': True,
    })
    context['facts'] = facts
    context.setdefault('meta', {})['product_stage_contract_preserved'] = True
    return json.dumps(context, ensure_ascii=False)


def _business_contract(context: Mapping[str, Any]) -> dict[str, Any]:
    for fact in list(context.get('facts') or []):
        if not isinstance(fact, dict) or fact.get('fact_id') != 'product-stage-contract':
            continue
        value = fact.get('value')
        if isinstance(value, dict):  # Compatibility with artifacts from older runs.
            return value
        try:
            parsed = _json_value(str(value or ''), {})
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_navigation_only_stage_request(value: Any, stage: str) -> bool:
    """Recognize relay boilerplate without discarding a real change request."""
    compact = re.sub(r'[\s，,。.!！:：；;]+', '', str(value or '').strip().lower())
    if not compact:
        return True
    for prefix in (
        '用户明确授权', '用户已明确授权', 'userauthorized',
    ):
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break
    for prefix in (
        '继续进入', '继续到', '继续至', '切换到', '切换至', '切换为',
        '进入', '转到', '前往', '开始', '执行', '生成',
        'continuetostage', 'continue', 'switchtostage', 'switchto', 'goto',
    ):
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break
    if compact.startswith('阶段'):
        compact = compact[2:]
    if compact.endswith('阶段'):
        compact = compact[:-2]
    return _normalize_stage_id(compact) == stage


def _shared_project_context(remote: Mapping[str, Any], stage: str) -> dict[str, Any]:
    """A compact, current projection; historical content remains in the host store."""
    workspace = _json_content_or_path(remote.get('workspace_seed'), {})
    if not isinstance(workspace, dict) or not workspace:
        return {}
    # Manifest lists are append-only. Do not pass superseded questions or obsolete
    # bindings as if all versions were simultaneously authoritative.
    latest_artifacts: dict[str, dict[str, Any]] = {}
    for artifact in workspace.get('artifacts') or []:
        if not isinstance(artifact, dict) or artifact.get('status') == 'superseded':
            continue
        stage_by_type = {value['artifact_type']: key for key, value in TEXT_STAGE_CONTRACTS.items()}
        stage_by_type.update({'competitive-analysis': 'competitive', 'prototype': 'prototype'})
        key = str(artifact.get('stage') or stage_by_type.get(artifact.get('artifact_type'))
                  or artifact.get('artifact_type') or artifact.get('artifact_id') or '')
        if not key:
            continue
        def version(item: Mapping[str, Any]) -> tuple[int, int]:
            match = re.fullmatch(r'(\d+)\.(\d+)', str(item.get('version') or ''))
            return (int(match[1]), int(match[2])) if match else (0, 0)
        if key not in latest_artifacts or version(artifact) >= version(latest_artifacts[key]):
            latest_artifacts[key] = artifact
    latest_bindings: dict[str, dict[str, Any]] = {}
    for binding in workspace.get('host_artifact_bindings') or []:
        if isinstance(binding, dict) and binding.get('material_id'):
            latest_bindings[str(binding['material_id'])] = binding
    approval = _json_content_or_path(remote.get('stage_approval'), {})
    request = ''
    if (isinstance(approval, dict) and approval.get('selected_stage', approval.get('stage')) == stage
            and approval.get('action') in ('continue', 'switch-stage')
            and approval.get('source') in ('user-interface', 'user-message')
            and approval.get('approval_id') and approval.get('reference')):
        request = str(approval.get('request_context') or '').strip()
    return {
        'workspace_id': workspace.get('workspace_id'),
        'project_overview': workspace.get('project_overview', {}),
        'accepted_decisions': [
            item for item in workspace.get('decisions') or []
            if isinstance(item, dict) and item.get('status') == 'accepted'
            and item.get('accepted_by') and item.get('acceptance_ref')
        ],
        'selected_upstream_versions': list(latest_bindings.values()),
        'current_stage_baseline': latest_artifacts.get(stage),
        'stage_request': request,
        'open_questions': [
            question for artifact in latest_artifacts.values()
            for question in artifact.get('open_questions') or []
        ],
        'artifact_statuses': [
            {key: artifact.get(key) for key in ('artifact_id', 'stage', 'version', 'status')}
            for artifact in latest_artifacts.values()
        ],
    }


def product_writer_prepare_context(
    user_request: str,
    stage_id: str,
    routing_record_json: Any = '',
    research_evidence: Any = '',
    source_material_paths_json: str = '[]',
    resource_profiles_path: str = '',
    upstream_artifact_paths_json: str = '[]',
    word_target: str = '',
) -> dict[str, str]:
    """Create Writer context from authoritative bindings for one product stage.

    Explicit arguments remain supported for tests and non-Workflow callers. During a
    Workflow step, omitted or empty values are resolved from immutable ``remote_inputs`` so
    the SubAgent never needs to read and re-serialize routing JSON or upstream path lists.
    """
    remote = _remote_inputs()
    runtime_stage = _runtime_stage()
    stage = runtime_stage or _normalize_stage_id(stage_id)
    contract = _stage_contract(stage)
    execution_plan = _json_content_or_path(remote.get('execution_plan'), {})
    if not isinstance(execution_plan, dict):
        execution_plan = {}
    routing = _json_content_or_path(routing_record_json, {})
    if not isinstance(routing, dict) or not routing:
        routing = execution_plan
    if isinstance(routing, dict):
        nested_plan = next((
            routing[key] for key in ('execution_plan', 'plan', 'routing_record')
            if isinstance(routing.get(key), dict)
        ), None)
        if nested_plan is not None:
            routing = nested_plan
    if not isinstance(routing, dict):
        routing = {}
    if not str(research_evidence or '').strip():
        research_evidence = remote.get('research_evidence') or ''
    evidence = _text_content_or_path(research_evidence)
    design_routing: dict[str, Any] = {}
    if stage == 'design':
        design_routing_value = _json_content_or_path(remote.get('design_routing_record'), {})
        if isinstance(design_routing_value, dict):
            design_routing = design_routing_value
        escalation = _json_content_or_path(remote.get('design_escalation'), {})
        if isinstance(escalation, dict) and isinstance(escalation.get('effective_route'), dict):
            effective = escalation['effective_route']
            same_scope = all(
                effective.get(key) == design_routing.get(key)
                for key in ('primary_domains', 'linked_domains')
            )
            if not same_scope or effective.get('overall_effort') != 'heavy':
                raise ValueError('design escalation must preserve scope and only increase effort')
            design_routing = effective
        branch_evidence = next((
            _text_content_or_path(remote[slot])
            for slot in ('design_heavy_evidence', 'design_light_evidence')
            if remote.get(slot) not in (None, '', [])
        ), '')
        if branch_evidence:
            evidence = '\n\n'.join(item for item in (evidence, branch_evidence) if item).strip()
    selected_for_session = routing.get('selected_stage') if isinstance(routing, dict) else None
    if not selected_for_session and isinstance(routing, dict):
        planned = routing.get('stage_chain')
        if isinstance(planned, list) and len(planned) == 1:
            selected_for_session = planned[0]
    if routing and _normalize_stage_id(selected_for_session) != stage:
        raise ValueError('stage_id must match execution_plan.selected_stage for this session.')

    target_source: Any = word_target
    parsed_target = _json_content_or_path(word_target, word_target)
    if isinstance(parsed_target, dict):
        target_source = parsed_target.get('word_target')
    if not str(target_source or '').strip():
        target_source = routing.get('word_target')
    target = _target_words(str(target_source or ''), int(contract['default_target']))

    if not str(resource_profiles_path or '').strip():
        resource_profiles_path = remote.get('resource_profiles') or ''
    if _json_content_or_path(source_material_paths_json, []) in (None, []):
        bound_sources = [
            remote[slot] for slot in ('product_materials', 'reference_sample')
            if remote.get(slot)
        ]
        source_material_paths_json = bound_sources
    if _json_content_or_path(upstream_artifact_paths_json, []) in (None, []):
        upstream_artifact_paths_json = [
            remote[slot] for slot in UPSTREAM_SLOTS.get(stage, ()) if remote.get(slot)
        ]
    shared = _shared_project_context(remote, stage)
    project_overview = (
        shared.get('project_overview')
        or execution_plan.get('project_overview')
        or routing.get('project_overview')
        or {}
    )
    if not isinstance(project_overview, dict):
        project_overview = {}
    product_goal = str(
        execution_plan.get('product_goal') or routing.get('product_goal')
        or project_overview.get('user_goal')
        or user_request or ''
    ).strip()
    if not product_goal:
        raise ValueError('The Writer requires execution_plan.product_goal or a non-empty user_request.')
    stage_request = str(shared.get('stage_request') or user_request or '').strip()
    if (
        _is_navigation_only_stage_request(stage_request, stage)
        or stage_request.lower() in {'continue', 'next', '继续', '下一步'}
        or stage_request == product_goal
    ):
        # Router/approval control words describe navigation, not the product. Feeding
        # "write-prd" to Writer as the only topic produced a meta-PRD about writing PRDs.
        stage_request = ''
    revision_instruction = ''
    if remote.get(f'upstream_{stage}'):
        revision_instruction = (
            '\n这是同一项目当前阶段产物的修订。绑定的 upstream_' + stage
            + ' 是上一版底稿，不是另一个项目或新样例。保留未被本次要求影响的内容、术语和已接受决定，'
            '仅根据本次变更与真实依赖影响更新；生成新版本，不覆盖历史版本。'
            '上游若标记需更新或存在冲突，保留缺口，不把过期内容当作已确认约束。'
        )
    if shared.get('stage_request'):
        revision_instruction += '\n用户在本次阶段选择时明确补充的要求：\n' + shared['stage_request']
    sections = '、'.join(str(item) for item in contract['sections'])
    design_route_instruction = ''
    if stage == 'design':
        if design_routing:
            design_route_instruction = (
                '\n第二层产品设计 Router 的权威范围与研究强度如下；只覆盖已激活的主责和联动类，'
                '不得机械补齐全部六类：\n'
                + json.dumps(design_routing, ensure_ascii=False)
            )
    reader_rules = _reader_facing_rules(stage)
    query = f"""产品目标：{product_goal}
本阶段要求：{stage_request or f'基于同一项目的共享输入完成 {contract["artifact_type"]}。'}

当前阶段在系统中的内部类型为 {contract['artifact_type']}，遵循原子 Skill 合同 {contract['source_skill']}；这些内部名称只用于执行，不得出现在交付正文。
建议篇幅约 {target} 个中文字符，可根据实际信息密度合理增多，不得因资料不足填充虚构事实。
初始大纲应覆盖：{sections}。{contract['boundary']}
事实、建议、已确认决定和待确认内容必须保持语义准确，但用章节和自然语言区分，不使用内部状态标签逐段标注。
真实来源编号仅可在文末依据中转换为“公开资料 001”或“项目资料 001”；不得伪造来源、现状、指标或接受状态。
用户批准大纲后，最新 Markdown 标题层级是唯一正文结构，不得从旧模板补回已删除章节。
样例仅影响结构、字段、语气和颗粒度，不得把样例业务事实当作当前项目事实。

{reader_rules}
{design_route_instruction}
{revision_instruction}""".strip()

    toolkit = WriterCreateToolkit()
    task = _json_value(toolkit.build_writing_task(
        query=query,
        task_id=str(require_context().params.get('session_id') or uuid.uuid4().hex),
    ), {})
    if not isinstance(task, dict):
        task = {}
    task['output'] = {**dict(task.get('output') or {}), 'representation': 'markdown'}
    task['product_parameters'] = {
        'stage_id': stage,
        'artifact_type': contract['artifact_type'],
        'source_skill': contract['source_skill'],
        'word_target': target,
        'product_goal': product_goal,
        'project_overview': project_overview,
        'stage_request': stage_request,
    }
    task_json = json.dumps(task, ensure_ascii=False)
    profiles_value: list[Any] = []
    profiled_paths: set[str] = set()
    if str(resource_profiles_path or '').strip():
        stored_profiles = _json_content_or_path(resource_profiles_path, [])
        if isinstance(stored_profiles, dict):
            stored_profiles = next((
                stored_profiles[key] for key in ('profiles', 'resource_profiles', 'data')
                if isinstance(stored_profiles.get(key), list)
            ), [])
        if not isinstance(stored_profiles, list):
            stored_profiles = []
        profiles_value.extend(stored_profiles)
    else:
        paths = _source_paths(source_material_paths_json)
        profiled_paths.update(paths)
        resources = toolkit.build_resources(
            file_paths_json=json.dumps(paths, ensure_ascii=False),
            knowledge_text=evidence,
        )
        generated_profiles = _json_value(toolkit.profile_resources(
            writing_task_json=task_json,
            user_input=query,
            resources_json=resources,
        ), [])
        if isinstance(generated_profiles, dict):
            generated_profiles = generated_profiles.get('profiles') or []
        if not isinstance(generated_profiles, list):
            generated_profiles = []
        profiles_value.extend(generated_profiles)

    upstream_paths = [
        path for path in _source_paths(upstream_artifact_paths_json)
        if path not in profiled_paths
    ]
    if upstream_paths:
        upstream_resources = toolkit.build_resources(
            file_paths_json=json.dumps(upstream_paths, ensure_ascii=False),
        )
        upstream_profiles = _json_value(toolkit.profile_resources(
            writing_task_json=task_json,
            user_input=(
                '提取这些选定上游产品产物中的目标、范围、对象、规则、状态、流程、'
                '验收、决定状态、版本和未决项。被选中或上传不代表已接受；'
                '只有带用户接受来源的决定可作正式约束，其他保持proposed/未知标签。'
            ),
            resources_json=upstream_resources,
        ), [])
        if isinstance(upstream_profiles, dict):
            upstream_profiles = upstream_profiles.get('profiles') or []
        if not isinstance(upstream_profiles, list):
            upstream_profiles = []
        profiles_value.extend(upstream_profiles)

    profiles = json.dumps(profiles_value, ensure_ascii=False)
    writing_context = toolkit.create_writing_context(
        writing_task_json=task_json,
        resource_profiles_json=profiles,
    )
    writing_context = _preserve_business_contract(
        writing_context, stage, contract, evidence, design_routing,
    )
    context_value = _json_value(writing_context, {})
    if not isinstance(context_value, dict):
        context_value = {}
    context_value['facts'] = [
        fact for fact in list(context_value.get('facts') or [])
        if not isinstance(fact, dict) or fact.get('fact_id') != 'product-project-brief'
    ]
    context_value['facts'].append({
        'fact_id': 'product-project-brief',
        'key': 'authoritative_product_goal_project_overview_and_stage_request',
        'value': json.dumps({
            'product_goal': product_goal,
            'project_overview': project_overview,
            'stage_request': stage_request,
        }, ensure_ascii=False),
        'source': ['workflow-execution-plan', 'product-workspace'],
        'applies_to': [],
        'locked': True,
    })
    writing_context = json.dumps(context_value, ensure_ascii=False)
    if shared:
        context_value = _json_value(writing_context, {})
        context_value.setdefault('facts', []).append({
            'fact_id': 'product-workspace-handoff',
            'key': 'internal_accepted_decisions_and_selected_versions',
            'value': json.dumps(shared, ensure_ascii=False),
            'source': ['workflow-bound-workspace'], 'applies_to': [], 'locked': True,
        })
        writing_context = json.dumps(context_value, ensure_ascii=False)
    root = _run_root('prepare')
    return {
        'writing_task': _write_json(root, 'writing_task', task_json),
        'resource_profiles': _write_json(root, 'resource_profiles', profiles),
        'writing_context': _write_json(root, 'writing_context', writing_context),
    }


def profile_product_materials(
    user_request: str,
    source_material_paths_json: str | list[str] = '[]',
) -> dict[str, Any]:
    """Profile only file-like product materials already bound to this Workflow.

    Args:
        user_request: The original product request, used only to scope extraction.
        source_material_paths_json: A JSON-array string or native array of exact ``kind=path``
            values from Workflow Material Bindings. Pass ``[]`` when no file is bound. Never pass
            scalar/JSON slot labels such as ``product_goal``, ``requested_stage`` or
            ``workspace_seed``; known accidental slot labels are ignored safely and arbitrary
            missing paths are rejected.
    """
    paths = _source_paths(
        source_material_paths_json,
        material_slots=PRODUCT_MATERIAL_SOURCE_SLOTS,
    )
    profiles: Any = []
    if paths:
        toolkit = WriterCreateToolkit()
        task_json = toolkit.build_writing_task(
            query=(
                '仅分析这些产品材料中明确存在的目标、范围、对象、规则、状态、流程、'
                '验收、版本和未知项，不补写材料中没有的事实。\n\n'
                + str(user_request or '').strip()
            ),
            task_id=str(require_context().params.get('session_id') or uuid.uuid4().hex),
        )
        resources = toolkit.build_resources(
            file_paths_json=json.dumps(paths, ensure_ascii=False),
        )
        profiles = _json_value(toolkit.profile_resources(
            writing_task_json=task_json,
            user_input=str(user_request or '').strip(),
            resources_json=resources,
        ), [])
    root = _run_root('resource-profiles')
    return {
        'profiles': profiles if isinstance(profiles, list) else [],
        'resource_profiles': _write_json(
            root, 'resource_profiles', profiles if isinstance(profiles, list) else [],
        ),
        'files': [Path(path).name for path in paths],
        'message': (
            'Profiles contain model-extracted summaries; unresolved details remain unknown.'
            if paths else 'No product material files were bound.'
        ),
    }


def product_writer_generate_outline(
    writing_task_path: str,
    writing_context_path: str,
) -> str:
    task = _json_value(_read_text(writing_task_path), {})
    if not isinstance(task, dict):
        task = {}
    stage = str((task.get('product_parameters') or {}).get('stage_id') or '')
    try:
        generated = WriterCreateToolkit().generate_outline(
            writing_task_json=_read_json(writing_task_path),
            writing_context_json=_read_json(writing_context_path),
        )
    except Exception:  # A canonical editable outline is safer than failing the stage.
        generated = ''
    try:
        parsed = _json_value(generated, None)
    except json.JSONDecodeError:
        parsed = generated
    if isinstance(parsed, dict):
        parsed = next((
            parsed.get(key) for key in ('outline_document', 'outline', 'markdown', 'content')
            if isinstance(parsed.get(key), str) and parsed.get(key).strip()
        ), '')
    if not isinstance(parsed, str) or not parsed.strip():
        parsed = ''
    normalized = _normalize_generated_outline(stage, parsed)
    return _write_markdown(_run_root('outline'), 'outline_document', normalized)


def _heading_signature(markdown: str) -> list[tuple[int, str]]:
    return [
        (len(match.group(1)), match.group(2).strip())
        for line in str(markdown or '').splitlines()
        if (match := MARKDOWN_HEADING.match(line.strip()))
    ]


def _uses_legacy_stage_template(stage: str, markdown: str) -> bool:
    legacy = {_normalized_title(item) for item in LEGACY_STAGE_SECTIONS.get(stage, [])}
    h2_titles = {
        _normalized_title(title) for level, title in _heading_signature(markdown) if level == 2
    }
    if not legacy or not h2_titles:
        return False
    matched = len(legacy & h2_titles)
    return matched >= max(2, (len(legacy) + 1) // 2)


def _normalize_generated_outline(stage_id: str, markdown: str) -> str:
    """Recover a usable relative Markdown hierarchy from imperfect model output."""
    contract = _stage_contract(stage_id)
    text = re.sub(
        r'^```(?:markdown|md)?\s*|\s*```$', '', str(markdown or '').strip(), flags=re.I,
    )
    headings = _heading_signature(text)
    if headings:
        has_title = headings[0][0] == 1
        if has_title:
            title = headings[0][1]
            body = headings[1:]
        else:
            title = ARTIFACT_TITLES[stage_id]
            body = headings
        if not body:
            return '\n\n'.join([
                f'# {title}',
                *[f'## {section}' for section in contract['sections']],
            ])
        base = min(level for level, _ in body)
        normalized_body: list[tuple[int, str]] = []
        previous = 1
        for raw_level, heading_title in body:
            candidate = max(2, raw_level - base + 2)
            level = min(5, candidate, previous + 1)
            normalized_body.append((level, heading_title))
            previous = level
        replacements = iter(normalized_body)
        output = [f'# {title}', ''] if not has_title else []
        heading_index = 0
        for line in text.splitlines():
            match = MARKDOWN_HEADING.match(line.strip())
            if not match:
                output.append(line)
                continue
            if has_title and heading_index == 0:
                output.append(f'# {title}')
            else:
                level, heading_title = next(replacements)
                output.append(f"{'#' * level} {heading_title}")
            heading_index += 1
        return '\n'.join(output).strip()
    else:
        candidates = []
        for line in text.splitlines():
            value = re.sub(r'^\s*(?:[-*+] |\d+[.)、]\s*)', '', line).strip()
            if value and len(value) <= 80:
                candidates.append(value)
        body_titles = candidates or list(contract['sections'])
        return '\n\n'.join([
            f'# {ARTIFACT_TITLES[stage_id]}',
            *[f'## {item}' for item in body_titles],
        ])


def _normalize_approved_outline(stage_id: str, markdown: str) -> str:
    """Normalize user-approved structure without restoring deleted template sections."""
    text = re.sub(
        r'^```(?:markdown|md)?\s*|\s*```$', '', str(markdown or '').strip(), flags=re.I,
    )
    headings = _heading_signature(text)
    if len(headings) >= 2 or (headings and headings[0][0] != 1):
        return _normalize_generated_outline(stage_id, text)
    if headings:
        title = headings[0][1]
        non_heading = '\n'.join(
            line for line in text.splitlines()
            if not MARKDOWN_HEADING.match(line.strip())
        ).strip()
    else:
        title = ARTIFACT_TITLES[stage_id]
        non_heading = text
    body = '## 正文'
    if non_heading:
        body += f'\n\n{non_heading}'
    return f'# {title}\n\n{body}'.strip()


def validate_product_outline(stage_id: str, outline_markdown: str) -> dict[str, Any]:
    """Validate structure deterministically while leaving content decisions to the user."""
    contract = _stage_contract(stage_id)
    headings = _heading_signature(outline_markdown)
    errors: list[str] = []
    warnings: list[str] = []
    if not headings or headings[0][0] != 1:
        errors.append('大纲必须以一个 H1 文档标题开始')
    if sum(1 for level, _ in headings if level == 1) != 1:
        errors.append('大纲必须且只能包含一个 H1 标题')
    if not any(level == 2 for level, _ in headings):
        errors.append('大纲至少需要一个 H2 正文章节')
    previous = 0
    for index, (level, title) in enumerate(headings, 1):
        if not title:
            errors.append(f'第 {index} 个标题为空')
        if previous and level > previous + 1:
            errors.append(f'标题“{title}”发生层级跳跃')
        previous = level
    normalized_titles = ''.join(title.lower() for _, title in headings)
    missing = [
        title for title in contract['sections']
        if re.sub(r'[\s、，,：:与和/]', '', title.lower())
        not in re.sub(r'[\s、，,：:与和/]', '', normalized_titles)
    ]
    if missing:
        warnings.append('建议确认原业务合同章节：' + '、'.join(missing))
    status = 'PASS' if not errors else 'FAIL'
    report = [
        '# 产品文档大纲检查', '', f'## {status}', '',
        f'- 业务阶段：{stage_id}',
        f'- H2 章节数：{sum(1 for level, _ in headings if level == 2)}',
        '- 结构来源：当前可编辑 Markdown（唯一权威）',
    ]
    if errors:
        report.extend(['', '## 必须修复', *[f'- {item}' for item in errors]])
    if warnings:
        report.extend(['', '## 建议确认', *[f'- {item}' for item in warnings]])
    return {'valid': not errors, 'errors': errors, 'warnings': warnings, 'report': '\n'.join(report)}


def product_writer_update_context(content_path: str, writing_context_path: str) -> str:
    original = _json_value(_read_text(writing_context_path), {})
    try:
        updated = _json_value(WriterCreateToolkit().update_writing_context(
            content_artifact_json=_read_text(content_path),
            writing_context_json=json.dumps(original, ensure_ascii=False),
        ), {})
        if not isinstance(updated, dict):
            raise ValueError('Writer returned a non-object writing context.')
    except Exception as exc:  # Context refresh must not discard a completed artifact.
        updated = dict(original) if isinstance(original, dict) else {}
        meta = updated.get('meta')
        if not isinstance(meta, dict):
            meta = {}
            updated['meta'] = meta
        meta['context_update_warning'] = str(exc)[:500]
    return _write_json(_run_root('context'), 'writing_context', updated)


def _required_bound_file(slot: str) -> str:
    """Resolve one immutable Workflow input without asking the SubAgent to read it."""
    value = _remote_inputs().get(slot)
    paths = _source_paths([value]) if value not in (None, '', []) else []
    if not paths:
        raise ValueError(f"Required Workflow input '{slot}' is missing or is not a file artifact.")
    return paths[0]


def product_writer_generate_outline_from_inputs(
    user_request: str,
    stage_id: str,
) -> dict[str, Any]:
    """Generate one canonical outline without exposing Workflow file bindings to the Agent."""
    stage = _runtime_stage() or _normalize_stage_id(stage_id)
    prepared = product_writer_prepare_context(user_request=user_request, stage_id=stage)
    baseline_slot = f'upstream_{stage}'
    if _remote_inputs().get(baseline_slot):
        baseline = _read_text(_required_bound_file(baseline_slot))
        # Returning to a view starts from its actual structure, not the generic
        # stage template. Exact legacy templates are the exception: migrate them
        # to the clearer reader-facing structure while preserving custom outlines.
        if _uses_legacy_stage_template(stage, baseline):
            headings = '\n\n'.join([
                f'# {ARTIFACT_TITLES[stage]}',
                *[f'## {section}' for section in _stage_contract(stage)['sections']],
            ])
        else:
            headings = '\n\n'.join(
                '#' * level + ' ' + title for level, title in _heading_signature(baseline)
            )
        outline = _write_markdown(
            _run_root('outline'), 'outline_document', _normalize_approved_outline(stage, headings or baseline),
        )
    else:
        outline = product_writer_generate_outline(
            prepared['writing_task'], prepared['writing_context'],
        )
    validation = validate_product_outline(stage, _read_text(outline))
    if not validation['valid']:
        raise ValueError(
            'Generated product outline is structurally invalid after normalization: '
            + '; '.join(validation['errors'])
        )
    approved_context = product_writer_update_context(outline, prepared['writing_context'])
    return {
        'writing_task': prepared['writing_task'],
        'writing_context': prepared['writing_context'],
        'outline': outline,
        'outline_report': validation['report'],
        'approved_context': approved_context,
        'warnings': list(validation.get('warnings') or []),
    }


def product_writer_generate_document_from_inputs(stage_id: str) -> dict[str, Any]:
    """Run the shared Writer pipeline directly from authoritative bound artifacts.

    The shared Writer still emits section deltas and resumes its stage checkpoint. This business
    adapter only removes error-prone file lookup and intermediate-path plumbing from the SubAgent.
    """
    stage = _runtime_stage() or _normalize_stage_id(stage_id)
    _stage_contract(stage)
    task_path = _required_bound_file(f'{stage}_task')
    outline_path = _required_bound_file(f'{stage}_outline')
    context_path = _required_bound_file(f'{stage}_context_approved')

    if _remote_inputs().get(f'upstream_{stage}'):
        baseline = _required_bound_file(f'upstream_{stage}')
        shared = _shared_project_context(_remote_inputs(), stage)
        instruction = (
            '在同一项目的上一版正文上做定向修订，不整篇重新生成。保留未受影响的正文、术语和已接受决定。'
            '根据本轮要求和绑定的最新上游，只修改实际受影响的内容；未知事实保留为假设或待确认。'
            '不要宣称用户已确认新的业务决定。遵循当前窗口批准的大纲；结构调整不得静默丢弃无关正文。'
            '同时把旧正文统一整理为面向读者的表达：先给结论，再给可执行内容，最后集中放依据和待确认；'
            '删除逐段的内部状态标签、证据等级、工具状态、内部字段名和来源系统说明。'
            + _reader_facing_rules(stage)
            + '\n本轮变更要求：' + (shared.get('stage_request') or '核对共享上游并完善当前阶段产物。')
            + '\n当前批准的大纲：\n' + _read_text(outline_path)
        )
        revised = product_writer_revise_markdown(
            base_document_path=baseline, writing_context_path=context_path,
            instruction=instruction, document_slot=f'{stage}_document',
        )
        document = revised[f'{stage}_document']
        document_html = _render_markdown_html(stage, document)
        final_context = product_writer_update_context(document, context_path)
        return {
            'section_plan': revised['modify_plan'],
            'chapter_count': 0,
            'chapter_publish': {'expected_count': 0, 'published_count': 0, 'complete': True, 'mode': 'revision'},
            'document': document, 'document_html': document_html,
            'writing_context': final_context, 'warnings': [],
        }

    plan = product_writer_plan_sections(task_path, outline_path, context_path)
    section_plan = str(plan['section_instructions'])
    chapters = product_writer_write_sections(task_path, section_plan, context_path)
    document = product_writer_assemble_draft(chapters[0], context_path, outline_path)
    document_html = _render_markdown_html(stage, document)
    final_context = product_writer_update_context(document, context_path)
    chapter_publish = _publish_chapter_artifacts(stage, chapters)
    return {
        'section_plan': section_plan,
        'chapter_count': len(chapters),
        'chapter_publish': chapter_publish,
        'document': document,
        'document_html': document_html,
        'writing_context': final_context,
        'warnings': [
            *list(plan.get('warnings') or []),
            *list(chapter_publish.get('warnings') or []),
        ],
    }


def _publish_chapter_artifacts(stage: str, chapters: list[str]) -> dict[str, Any]:
    """Publish optional chapter files as deterministic items without blocking the draft."""
    slot = f'{stage}_chapters'
    published = 0
    warnings: list[str] = []
    reader_root = _run_root('reader-chapters')
    for list_index, chapter in enumerate(chapters):
        try:
            reader_chapter = chapter
            if Path(str(chapter)).is_file():
                reader_chapter = _write_markdown(
                    reader_root,
                    f'chapter_{list_index + 1:04d}',
                    _present_reader_facing_markdown(stage, _read_text(chapter)),
                )
            _save_artifact(
                key=slot,
                value=reader_chapter,
                content_type='file',
                source_tool='product_writer_generate_document_from_inputs',
                caption=f'{ARTIFACT_TITLES[stage]} · 第 {list_index + 1} 章',
                internal_publish=True,
                publisher_list_index=list_index,
            )
            published += 1
        except Exception as exc:
            warnings.append(
                f'{slot}[{list_index + 1}] publish failed: {str(exc)[:300]}'
            )
    return {
        'slot': slot,
        'expected_count': len(chapters),
        'published_count': published,
        'complete': published == len(chapters),
        'warnings': warnings,
    }


def product_writer_plan_sections(
    writing_task_path: str,
    outline_document_path: str,
    writing_context_path: str,
) -> dict[str, Any]:
    """Build a stable Writer section contract from the approved Markdown outline."""
    task = _json_value(_read_text(writing_task_path), {})
    if not isinstance(task, dict):
        task = {}
    stage = str((task.get('product_parameters') or {}).get('stage_id') or '')
    outline = _normalize_approved_outline(stage, _read_text(outline_document_path))
    context = _json_value(_read_text(writing_context_path), {})
    if not isinstance(context, dict):
        context = {}
    validation = validate_product_outline(stage, outline)
    if not validation['valid']:
        raise ValueError('Approved product outline is structurally invalid: ' + '; '.join(validation['errors']))
    headings = _heading_signature(outline)
    document_title = next((title for level, title in headings if level == 1), ARTIFACT_TITLES[stage])
    contract = _business_contract(context)
    instructions: list[dict[str, Any]] = []
    for index, (level, title) in enumerate(headings):
        if level != 2:
            continue
        descendants: list[tuple[int, str]] = []
        for child_level, child_title in headings[index + 1:]:
            if child_level <= 2:
                break
            descendants.append((child_level, child_title))
        expected = [child_title for _, child_title in descendants] or [title]
        structure = '；'.join(
            f"输出 `{'#' * child_level} {child_title}`"
            for child_level, child_title in descendants
        ) or '直接完成本 H2 章节正文。'
        instructions.append({
            'instruction_id': f'product-{stage}-section-{len(instructions) + 1}',
            'content_ref': {'heading_path': [document_title, title]},
            'section_title': title,
            'section_goal': f'依据写作任务、批准大纲和已注册证据完成“{title}”章节。',
            'required_points': [
                '标题硬约束：正文必须以当前 section_title 作为唯一 H2 根标题。',
                f'子结构指引：{structure}',
                (
                    '内容约束：只能使用写作上下文中的用户材料和已登记资料；'
                    '已确认内容、建议和待确认事项必须语义准确，不得虚构来源或确认状态。'
                ),
                '阅读约束：本节只写读者需要理解或执行的内容；研究过程、工具状态和内部编号放到文末依据章节，不在正文重复。',
                '不得增加批准大纲之外的 H1/H2 章节。',
            ],
            'fact_constraints': ['不得虚构来源、指标、接受状态或业务事实。'],
            'style_constraints': [
                '使用团队日常会写的简洁产品文档语言，短句优先，避免空泛套话。',
                '不显示内部工作流术语、英文状态值、证据等级或逐段状态前缀。',
                '研发交付之外的阶段使用业务语言；研发交付可保留必要专业术语并在首次出现时用中文解释。',
            ],
            'expected_blocks': expected,
            'meta': {
                'product_stage': stage,
                'source_skill': str(contract.get('source_skill') or ''),
                'deterministically_normalized': True,
            },
        })
    fingerprint = hashlib.sha256(json.dumps(
        instructions, ensure_ascii=False, sort_keys=True,
    ).encode('utf-8')).hexdigest()[:20]
    instructions_doc = {
        'instruction_set_id': f'product-{stage}-{fingerprint}',
        'instructions': instructions,
        'meta': {
            'representation': 'markdown',
            'document_title': document_title,
            'deterministically_normalized': True,
        },
    }
    root = _run_root('section-plan')
    return {
        'section_instructions': _write_json(root, 'section_instructions', instructions_doc),
        'warnings': [],
    }


def product_writer_write_sections(
    writing_task_path: str,
    section_instructions_path: str,
    writing_context_path: str,
) -> list[str]:
    """Stream or resume product-document sections using shared Writer checkpoints."""
    ctx = require_context()
    task_json = _read_json(writing_task_path)
    task = _json_value(task_json, {})
    if not isinstance(task, dict):
        task = {}
    stage = str((task.get('product_parameters') or {}).get('stage_id') or 'unknown')
    events = DraftMarkdownStreamEventEmitter(ctx.emit, slot=f'{stage}_document')
    try:
        sections = _json_value(WriterCreateToolkit().stream_draft_blocks_markdown(
            writing_task_json=task_json,
            section_instructions_json=_read_json(section_instructions_path),
            writing_context_json=_read_json(writing_context_path),
            on_delta=events.feed,
            on_section_end=events.flush,
            on_progress=lambda payload: ctx.emit({'type': 'progress', **payload}),
            checkpoint_dir=str(
                _workspace_root() / 'product-writer' / 'draft-checkpoints' / stage
            ),
        ), [])
        if not isinstance(sections, list) or not sections:
            plan = _json_value(_read_text(section_instructions_path), {})
            instructions = list(plan.get('instructions') or []) if isinstance(plan, dict) else []
            sections = [
                '## {}\n\n本节生成未返回有效正文，请在审批时补充。'.format(
                    str(item.get('section_title') or '待补充章节').strip(),
                )
                for item in instructions if isinstance(item, dict)
            ]
        if not sections:
            sections = ['## 待补充章节\n\n本阶段生成未返回有效正文，请在审批时补充。']
        root = _run_root('draft-sections')
        paths = [
            _write_markdown(root, f'draft_section_{index:04d}', str(section))
            for index, section in enumerate(sections, 1)
        ]
    except Exception as exc:
        events.abort(str(exc))
        raise
    events.end()
    return paths


def _normalized_title(value: str) -> str:
    return re.sub(r'[\s\W_]+', '', str(value or ''), flags=re.UNICODE).lower()


def _align_draft_headings(draft: str, outline: str) -> str:
    """Preserve approved headings and demote model-added headings without losing prose."""
    approved = _heading_signature(outline)
    indices_by_title: dict[str, list[int]] = {}
    for index, (_, title) in enumerate(approved):
        indices_by_title.setdefault(_normalized_title(title), []).append(index)
    used: set[int] = set()
    chunks: dict[int, list[str]] = {index: [] for index in range(len(approved))}
    preamble: list[str] = []
    current: int | None = None
    for line in str(draft or '').splitlines():
        match = MARKDOWN_HEADING.match(line.strip())
        if not match:
            (chunks[current] if current is not None else preamble).append(line)
            continue
        key = _normalized_title(match.group(2))
        candidate = next((index for index in indices_by_title.get(key, []) if index not in used), None)
        if candidate is None:
            (chunks[current] if current is not None else preamble).append(
                f'**{match.group(2).strip()}**',
            )
            continue
        current = candidate
        used.add(candidate)

    rendered: list[str] = []
    for index, (level, title) in enumerate(approved):
        if rendered:
            rendered.append('')
        rendered.append(f"{'#' * level} {title}")
        content = list(chunks[index])
        if index == 0 and preamble:
            content = [*preamble, *content]
        if content:
            rendered.extend(content)
        elif level > 1:
            rendered.extend(['', '本节尚未生成有效正文，请在审批时补充。'])
    return '\n'.join(rendered).strip()


def product_writer_assemble_draft(
    draft_sections_anchor_path: str,
    writing_context_path: str,
    outline_document_path: str,
) -> str:
    anchor = Path(str(draft_sections_anchor_path or '')).resolve()
    directory = anchor if anchor.is_dir() else anchor.parent
    paths = sorted(directory.glob('draft_section_*.md'))
    if not paths:
        raise ValueError('No Writer product section files were found.')
    raw_outline = _read_text(outline_document_path)
    context = _json_value(_read_text(writing_context_path), {})
    if not isinstance(context, dict):
        context = {}
    stage = str(_business_contract(context).get('stage_id') or '')
    outline = _normalize_approved_outline(stage, raw_outline)
    section_markdown = [_read_text(str(path)) for path in paths]
    try:
        payload = _json_value(WriterCreateToolkit().generate_draft_document_markdown(
            draft_sections_json=json.dumps(section_markdown, ensure_ascii=False),
            writing_context_json=_read_json(writing_context_path),
            outline_json=outline,
            title='',
        ), {})
        generated = str(payload.get('draft_document') or '').strip()
    except Exception:
        generated = ''
    draft = _align_draft_headings(generated or '\n\n'.join(section_markdown), outline)
    draft = _present_reader_facing_markdown(stage, draft)
    return _write_markdown(_run_root('draft-document'), 'draft_document', draft)


def product_writer_revise_markdown(
    base_document_path: str,
    writing_context_path: str,
    instruction: str,
    document_slot: str,
) -> dict[str, str]:
    if document_slot not in EDITABLE_SLOTS:
        raise ValueError(f'document_slot must be one of {sorted(EDITABLE_SLOTS)}.')
    document = _read_text(base_document_path)
    toolkit = WriterRevisionToolkit()
    context_json = _read_json(writing_context_path)
    revision_task = toolkit.build_revision_task(
        query=str(instruction or '').strip(),
        writer_document_json=document,
        allow_outline=True,
    )
    locate = toolkit.locate_revision_target(
        writing_task_json=revision_task,
        writer_document_json=document,
        writing_context_json=context_json,
    )
    plan = toolkit.generate_modify_plan(
        writing_task_json=revision_task,
        writer_document_json=document,
        locate_result_json=locate,
        writing_context_json=context_json,
    )
    replace_set = toolkit.generate_string_replace_set(
        markdown_document=document,
        modify_plan_json=plan,
        writing_context_json=context_json,
    )
    applied = _json_value(toolkit.apply_string_replace(
        markdown_document=document,
        string_replace_set_json=replace_set,
        writing_context_json=context_json,
    ), {})
    revised = str(applied.get('revised_document') or '').strip()
    if not revised:
        raise ValueError('Shared Writer revision returned no revised document.')
    if document_slot.endswith('_outline'):
        revised = _normalize_approved_outline(document_slot.removesuffix('_outline'), revised)
    elif document_slot.endswith('_document'):
        revised = _present_reader_facing_markdown(
            document_slot.removesuffix('_document'), revised,
        )
    root = _run_root(f'revise-{document_slot}')
    return {
        'revision_task': _write_json(root, 'revision_task', revision_task),
        'locate_result': _write_json(root, 'locate_result', locate),
        'modify_plan': _write_json(root, 'modify_plan', plan),
        'revision_set': _write_json(root, 'revision_set', replace_set),
        'revision_result': _write_json(root, 'revision_result', applied),
        document_slot: _write_markdown(root, document_slot, revised),
    }
