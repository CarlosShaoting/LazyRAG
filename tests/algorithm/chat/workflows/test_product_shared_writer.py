"""Shared project views must remain the same logical artifacts across stage runs."""
import json
import types
from pathlib import Path

import pytest
import yaml

from test_product_solution_delivery import _load_writer_bridge


SHARED_UPSTREAM_SLOTS = (
    'upstream_direction', 'upstream_competitive', 'upstream_design',
    'upstream_prd', 'upstream_prototype', 'upstream_review', 'upstream_handoff',
)


@pytest.mark.parametrize('stage', ['direction', 'design', 'prd', 'review', 'handoff'])
def test_every_writer_stage_profiles_all_shared_project_artifacts(monkeypatch, tmp_path, stage):
    bridge = _load_writer_bridge()
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    upstream_paths = {}
    for slot in SHARED_UPSTREAM_SLOTS:
        path = tmp_path / f'{slot}.md'
        path.write_text(f'# {slot}\nshared project artifact', encoding='utf-8')
        upstream_paths[slot] = str(path)
    captured_paths = []

    class Toolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def build_resources(self, **kwargs):
            captured_paths.extend(json.loads(kwargs['file_paths_json']))
            return '{}'

        def profile_resources(self, **_kwargs):
            return '[]'

        def create_writing_context(self, **_kwargs):
            return '{}'

    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': f'build_{stage}_outline', 'session_id': f'{stage}-session',
        'remote_inputs': {
            'execution_plan': {
                'selected_stage': stage, 'product_goal': '同一个产品项目',
            },
            'resource_profiles': str(profiles),
            **upstream_paths,
        },
    })
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', Toolkit)

    bridge.product_writer_prepare_context('继续完善项目', stage)

    assert set(upstream_paths.values()) <= set(captured_paths)


def test_every_workflow_step_declares_all_shared_project_artifacts():
    root = Path(__file__).resolve().parents[4]
    graph = yaml.safe_load(
        (root / 'workflows/product_solution_delivery/scenario/state.yml').read_text()
    )
    expected = set(SHARED_UPSTREAM_SLOTS)
    for step_id, step in graph['steps'].items():
        inputs = {item['material']: item for item in step.get('inputs', [])}
        assert expected <= set(inputs), step_id
        assert all(inputs[slot].get('required') is False for slot in expected), step_id


@pytest.mark.parametrize('stage', ['direction', 'design', 'prd', 'review', 'handoff'])
def test_returning_stage_binds_and_profiles_its_own_previous_version(monkeypatch, tmp_path, stage):
    bridge = _load_writer_bridge()
    baseline = tmp_path / 'previous.md'
    baseline.write_text('# 已有产物\n保留本次未修改的规则。', encoding='utf-8')
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    captured = {}

    class Toolkit:
        def build_writing_task(self, **kwargs):
            captured['query'] = kwargs['query']
            return '{}'

        def build_resources(self, **kwargs):
            captured['paths'] = json.loads(kwargs['file_paths_json'])
            return '{}'

        def profile_resources(self, **kwargs):
            return '[{"id":"prior-view"}]'

        def create_writing_context(self, **kwargs):
            return '{}'

    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': f'build_{stage}_outline', 'session_id': 'next-stage-session',
        'remote_inputs': {
            'execution_plan': {'selected_stage': stage},
            'resource_profiles': str(profiles), f'upstream_{stage}': str(baseline),
            'workspace_seed': {'workspace_id': 'same-project', 'artifacts': [
                {'artifact_id': 'logical-document', 'stage': stage, 'version': '1.0', 'status': 'draft'},
            ]},
            'stage_approval': {'approval_id': 'user-choice', 'source': 'user-interface',
                               'reference': 'command:1', 'action': 'switch-stage',
                               'selected_stage': stage, 'request_context': '只修改权限规则'},
        },
    })
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', Toolkit)
    result = bridge.product_writer_prepare_context('继续', stage)
    assert captured['paths'] == [str(baseline)]
    assert '只修改权限规则' in captured['query']
    assert '上一版底稿' in captured['query']
    persisted = json.loads(Path(result['writing_context']).read_text())
    shared = json.loads(next(fact['value'] for fact in persisted['facts']
                             if fact['fact_id'] == 'product-workspace-handoff'))
    assert shared['workspace_id'] == 'same-project'
    assert shared['current_stage_baseline']['artifact_id'] == 'logical-document'
    # The graph must actually bind what the bridge expects; a helper-only fix is insufficient.
    root = Path(__file__).resolve().parents[4]
    graph = yaml.safe_load((root / 'workflows/product_solution_delivery/scenario/state.yml').read_text())
    assert f'upstream_{stage}' in [item['material'] for item in graph['steps'][f'build_{stage}_outline']['inputs']]


def test_shared_context_keeps_only_current_questions_and_latest_binding():
    bridge = _load_writer_bridge()
    shared = bridge._shared_project_context({'workspace_seed': {
        'workspace_id': 'project',
        'artifacts': [
            {'artifact_id': 'design', 'artifact_type': 'product-design-spec', 'version': '1.1', 'status': 'needs-update',
             'open_questions': ['Current question']},
            {'artifact_id': 'design', 'artifact_type': 'product-design-spec', 'version': '1.0', 'status': 'draft',
             'open_questions': ['Old question']},
            {'artifact_id': 'prd', 'stage': 'prd', 'version': '2.0', 'status': 'superseded',
             'open_questions': ['Superseded question']},
            None,
        ],
        'host_artifact_bindings': [
            {'material_id': 'upstream_design', 'revision_id': 'old'},
            {'material_id': 'upstream_design', 'revision_id': 'new'},
        ],
    }}, 'design')
    assert shared['open_questions'] == ['Current question']
    assert shared['selected_upstream_versions'] == [{'material_id': 'upstream_design', 'revision_id': 'new'}]
    assert shared['current_stage_baseline']['status'] == 'needs-update'


def test_other_stage_or_unsourced_request_is_not_replayed():
    bridge = _load_writer_bridge()
    shared = bridge._shared_project_context({
        'workspace_seed': {'workspace_id': 'project'},
        'stage_approval': {'selected_stage': 'prd', 'request_context': 'obsolete request'},
    }, 'design')
    assert shared['stage_request'] == ''


@pytest.mark.parametrize('value', [
    'write-prd', '继续进入 PRD', '切换到 PRD', '用户明确授权continue阶段：prd',
])
def test_pure_stage_navigation_is_not_used_as_writer_business_request(value):
    bridge = _load_writer_bridge()
    assert bridge._is_navigation_only_stage_request(value, 'prd') is True


def test_navigation_with_a_real_change_request_is_preserved():
    bridge = _load_writer_bridge()
    assert bridge._is_navigation_only_stage_request(
        '继续进入 PRD，并加入异常状态与回滚验收', 'prd',
    ) is False


def test_writer_uses_bound_product_goal_in_task_and_context(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    captured = {}

    class Toolkit:
        def build_writing_task(self, **kwargs):
            captured['query'] = kwargs['query']
            return json.dumps({'query': kwargs['query']}, ensure_ascii=False)

        def create_writing_context(self, **_kwargs):
            return '{}'

    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': 'build_prd_outline', 'session_id': 'prd-session',
        'remote_inputs': {
            'execution_plan': {
                'selected_stage': 'prd',
                'product_goal': '为研发团队设计减少漏项的需求评审助手',
            },
            'resource_profiles': str(profiles),
            'workspace_seed': {
                'workspace_id': 'same-project',
                'project_overview': {'target_users': ['研发负责人'], 'scope': '需求评审'},
            },
        },
    })
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', Toolkit)

    result = bridge.product_writer_prepare_context('write-prd', 'prd')

    assert captured['query'].startswith('产品目标：为研发团队设计减少漏项的需求评审助手')
    assert '本阶段要求：基于同一项目的共享输入完成 prd' in captured['query']
    assert captured['query'].count('write-prd') == 1  # Contract name, never the business topic.
    task = json.loads(Path(result['writing_task']).read_text())
    assert task['product_parameters']['product_goal'] == '为研发团队设计减少漏项的需求评审助手'
    assert task['product_parameters']['project_overview']['scope'] == '需求评审'
    writing_context = json.loads(Path(result['writing_context']).read_text())
    brief = json.loads(next(
        fact['value'] for fact in writing_context['facts']
        if fact['fact_id'] == 'product-project-brief'
    ))
    assert brief == {
        'product_goal': '为研发团队设计减少漏项的需求评审助手',
        'project_overview': {'target_users': ['研发负责人'], 'scope': '需求评审'},
        'stage_request': '',
    }


def test_returning_view_keeps_existing_outline_without_regenerating_template(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    baseline = tmp_path / 'previous.md'
    baseline.write_text('# 团队方案\n\n## 自定义规则\n完整正文\n\n## 已有异常处理\n保留正文', encoding='utf-8')
    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': 'build_design_outline', 'remote_inputs': {'upstream_design': str(baseline)},
    })
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'product_writer_prepare_context', lambda **_: {
        'writing_task': 'task', 'writing_context': 'context',
    })
    monkeypatch.setattr(bridge, 'product_writer_generate_outline', lambda *_: pytest.fail('must not regenerate template'))
    monkeypatch.setattr(bridge, 'product_writer_update_context', lambda *_: 'context')
    result = bridge.product_writer_generate_outline_from_inputs('调整规则', 'design')
    assert Path(result['outline']).read_text().strip() == '# 团队方案\n\n## 自定义规则\n\n## 已有异常处理'


def test_returning_document_uses_revision_not_full_generation(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    files = {}
    for slot, content in {
        'upstream_prd': '# PRD\n\n## 自定义需求\n完整原文',
        'prd_task': '{}', 'prd_context_approved': '{}',
        'prd_outline': '# PRD\n\n## 自定义需求',
    }.items():
        path = tmp_path / (slot + '.md')
        path.write_text(content, encoding='utf-8')
        files[slot] = str(path)
    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': 'write_prd_document', 'remote_inputs': files,
    })
    captured = {}
    revised_document = tmp_path / 'new-draft.md'
    revised_document.write_text('# PRD\n\n## 自定义需求\n修订正文', encoding='utf-8')
    def revise(**kwargs):
        captured.update(kwargs)
        return {'prd_document': str(revised_document), 'modify_plan': 'changes.json'}
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'product_writer_revise_markdown', revise)
    monkeypatch.setattr(bridge, 'product_writer_plan_sections', lambda *_: pytest.fail('no full regeneration'))
    monkeypatch.setattr(bridge, 'product_writer_update_context', lambda *_: 'context')
    result = bridge.product_writer_generate_document_from_inputs('prd')
    assert captured['base_document_path'] == files['upstream_prd']
    assert captured['document_slot'] == 'prd_document'
    assert '不整篇重新生成' in captured['instruction']
    assert result['document'] == str(revised_document)
    assert Path(result['document_html']).suffix == '.html'
    assert '<!doctype html>' in Path(result['document_html']).read_text()
    assert result['chapter_publish']['mode'] == 'revision'
    assert Path(files['upstream_prd']).read_text() == '# PRD\n\n## 自定义需求\n完整原文'


def test_reader_facing_document_contract_is_result_first_and_plain_chinese():
    bridge = _load_writer_bridge()

    for stage, contract in bridge.TEXT_STAGE_CONTRACTS.items():
        assert contract['sections'][0] == '先看结论'
        rules = bridge._reader_facing_rules(stage)
        assert '结果和过程分开' in rules
        assert '不得把内部工作流信息写进交付正文' in rules
        assert '不得用【已核验事实】' in rules
        if stage == 'handoff':
            assert '可保留接口、数据结构、权限、安全' in rules


def test_noncompetitive_text_documents_enrich_presentation_without_changing_structure():
    bridge = _load_writer_bridge()

    for stage in bridge.TEXT_STAGE_CONTRACTS:
        rules = bridge._reader_facing_rules(stage)
        assert '保持用户批准的大纲、标题层级、章节顺序和字段不变' in rules
        assert '不得新增“可视化”' in rules
        assert 'GFM 表格' in rules
        assert 'Mermaid flowchart' in rules
        assert 'quadrantChart' in rules
        assert '不得生成装饰图或想象截图' in rules

    design_rules = bridge._reader_facing_rules('design')
    assert 'overall_effort=light 时不生成 Heavy' in design_rules
    assert 'overall_effort=heavy 时不生成 Light' in design_rules


def test_reader_facing_cleanup_translates_leaked_workflow_vocabulary():
    bridge = _load_writer_bridge()
    raw = '''# Demo development-handoff

【已核验事实】当前运行未登记任何可引用的 WEB-NNN/KB-NNN 外部来源。

【拟议决定】status is `proposed`, artifact is `draft`, value is `null`.

参考 WEB-001 与 KB-002；风险是 `cross_tenant` 和 `silent_write`。
'''

    cleaned = bridge._present_reader_facing_markdown('handoff', raw)

    for leaked in (
        'development-handoff', 'WEB-NNN', 'KB-NNN', 'WEB-001', 'KB-002',
        '`proposed`', '`draft`', '`null`', '`cross_tenant`', '`silent_write`',
        '【已核验事实】', '【拟议决定】',
    ):
        assert leaked not in cleaned
    assert '研发交付文档' in cleaned
    assert '本轮未使用外部资料' in cleaned
    assert '公开资料 001' in cleaned
    assert '项目资料 002' in cleaned
    assert '**建议：**' in cleaned


def test_only_exact_legacy_outline_is_migrated_to_reader_facing_structure(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    legacy = tmp_path / 'legacy.md'
    legacy.write_text(
        '# 旧版研发交付\n\n'
        + '\n\n'.join(f'## {title}' for title in bridge.LEGACY_STAGE_SECTIONS['handoff']),
        encoding='utf-8',
    )
    context = types.SimpleNamespace(workspace_path=str(tmp_path), params={
        'step_id': 'build_handoff_outline',
        'remote_inputs': {'upstream_handoff': str(legacy)},
    })
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'product_writer_prepare_context', lambda **_: {
        'writing_task': 'task', 'writing_context': 'context',
    })
    monkeypatch.setattr(bridge, 'product_writer_update_context', lambda *_: 'context')

    result = bridge.product_writer_generate_outline_from_inputs('调整表达', 'handoff')
    outline = Path(result['outline']).read_text(encoding='utf-8')

    assert '# 研发交付文档' in outline
    assert '## 先看结论' in outline
    assert '## 待研发确认' in outline
    assert '## 就绪结论与阻塞摘要' not in outline


def test_project_defaults_do_not_remove_human_confirmation_boundaries():
    root = Path(__file__).resolve().parents[4] / 'workflows/product_solution_delivery'
    workflow = yaml.safe_load((root / 'workflow.yaml').read_text())
    graph = yaml.safe_load((root / 'scenario/state.yml').read_text())
    clarification_fields = workflow['runtime']['clarification_fields']
    assert [field['id'] for field in clarification_fields] == ['product_goal']
    assert clarification_fields[0]['binding'] == 'request_context'
    parent = graph['steps']['route_product_stage']
    assert parent['tools'] == [
        'load_product_skill_contract', 'publish_product_route', 'profile_product_materials',
    ]
    assert parent['terminal_tools'] == ['publish_product_route']
    assert parent['execution']['tool_call_limits']['publish_product_route'] == 2
    # One malformed model call may be corrected without bypassing the bounded Router loop.
    assert parent['execution']['tool_call_limits']['profile_product_materials'] == 2
    assert 'Input slot labels are schema names, not paths' in parent['prompt']
    assert 'pass [] exactly' in parent['prompt']
    assert 'Never invent placeholders' in parent['prompt']
    assert 'never pass an embedded:// Skill resource' in parent['prompt']
    assert graph['steps']['analyze_competitive_position']['execution'][
        'tool_call_limits'
    ]['load_product_skill_contract'] == 2
    assert {item['material'] for item in parent['outputs']} <= set(
        workflow['runtime']['publisher_owned_slots']
    )
    design_router = graph['steps']['route_design_scope']
    assert design_router['tools'] == [
        'load_product_skill_contract', 'publish_design_route_compact',
    ]
    assert design_router['terminal_tools'] == ['publish_design_route_compact']
    assert design_router['execution']['tool_call_limits']['publish_design_route_compact'] == 1
    tool_functions = {
        function
        for script in workflow['tool_scripts']
        for function in script.get('functions', [])
    }
    assert 'publish_design_route_compact' in tool_functions
    assert 'never JSON objects or arrays' in design_router['prompt']
    assert {item['material'] for item in design_router['outputs']} <= set(
        workflow['runtime']['publisher_owned_slots']
    )
    finalizer = graph['steps']['finalize_product_delivery']
    assert finalizer['tools'] == ['publish_product_handoff_state']
    assert finalizer['terminal_tools'] == ['publish_product_handoff_state']
    assert finalizer['fail_fast_tools'] == ['publish_product_handoff_state']
    assert finalizer['execution']['publisher_fallback_tool'] == 'publish_product_handoff_state'
    assert finalizer['execution']['tool_call_limits']['publish_product_handoff_state'] == 1
    assert {item['material'] for item in finalizer['outputs']} <= set(
        workflow['runtime']['publisher_owned_slots']
    )
    for evidence_step in ('collect_design_light_evidence', 'collect_design_heavy_evidence'):
        evidence_prompt = graph['steps'][evidence_step]['prompt']
        assert 'reference_paths omitted' in evidence_prompt
        assert 'domain id as reference_paths' in evidence_prompt
        assert 'available_resources' in evidence_prompt
    design_tab = next(tab for tab in workflow['ui']['tabs'] if tab['id'] == 'design_router')
    assert design_tab['composite_behavior']['visible_when'] == [
        {'slot': 'design_light_evidence', 'material': 'design_routing_record', 'path': 'data.overall_effort', 'equals': 'light'},
        {'slot': 'design_heavy_evidence', 'material': 'design_routing_record', 'path': 'data.overall_effort', 'equals': 'heavy'},
    ]
    router_inputs = {item['material']: item.get('required', True)
                     for item in parent['inputs']}
    assert router_inputs['product_goal'] is True
    assert all(router_inputs[field] is False for field in (
        'requested_stage', 'execution_depth', 'word_target', 'reference_sample_choice',
    ))
    for checkpoint in ('route_product_stage', 'route_design_scope',
                       'collect_design_light_evidence', 'collect_design_heavy_evidence',
                       'analyze_competitive_position', 'build_interactive_prototype',
                       *(f'build_{stage}_outline' for stage in ['direction', 'design', 'prd', 'review', 'handoff']),
                       *(f'write_{stage}_document' for stage in ['direction', 'design', 'prd', 'review', 'handoff'])):
        assert graph['steps'][checkpoint]['mode'] == 'human'
    assert sum(step.get('route') == 'choice' for step in graph['steps'].values()) == 2
    slots = {slot['id']: slot for slot in workflow['slots']}
    for stage in ('direction', 'design', 'prd', 'review', 'handoff'):
        document_step = graph['steps'][f'write_{stage}_document']
        prompt = document_step['prompt']
        normalized_prompt = ' '.join(prompt.split())
        required_outputs = {
            item['material'] for item in document_step['outputs']
            if item.get('required', True)
        }
        assert required_outputs == {
            f'{stage}_assessment', f'{stage}_document', f'{stage}_document_html',
            f'{stage}_context_final',
        }
        assert slots[f'{stage}_assessment']['type'] == 'json'
        assert slots[f'{stage}_assessment']['cardinality'] == 'single'
        assert slots[f'{stage}_assessment']['exposed'] is False
        assert 'Completion requires this exact order' in prompt
        assert 'Do not call save_artifacts before the' in prompt
        assert f'{stage}_assessment is unsaved' in prompt
        assert next(item for item in document_step['outputs']
                    if item['material'] == f'{stage}_assessment').get('required', True) is True
        assert 'authoritative stage-aware JSON Schema' in normalized_prompt
        assert f'value={{"stage":"{stage}","status":"draft"}}' in normalized_prompt
        assert 'never pass stage as a sibling/top-level tool argument' in normalized_prompt
        assert 'retry once only' in prompt
        assert (
            f'load_product_skill_contract(stage_id="{stage}") with reference_paths omitted'
            in normalized_prompt
        )
        assert 'Never pass input/output material paths, runtime/workspace paths' in normalized_prompt
        assert 'Writer-returned section_plan, document or writing_context paths' in normalized_prompt
        assert document_step['execution']['tool_call_limits'][
            'validate_product_stage_assessment'
        ] == 2
        assert 'at most 80 Chinese' in prompt
        assert 'Never expose assessment/Manifest/Workspace JSON' in prompt
    for stage_step in ('analyze_competitive_position', 'build_interactive_prototype'):
        prompt = graph['steps'][stage_step]['prompt']
        assert 'authoritative stage-aware JSON Schema' in prompt
        assert 'never pass stage as a sibling/top-level tool argument' in ' '.join(prompt.split())
        assert 'retry once only' in prompt
        assert graph['steps'][stage_step]['execution']['tool_call_limits'][
            'validate_product_stage_assessment'
        ] == 2
        assert 'at most 80 Chinese' in prompt
    final_prompt = graph['steps']['finalize_product_delivery']['prompt']
    assert 'publish_product_handoff_state() once with exactly {} and no arguments' in final_prompt
    assert 'atomically saves stage_manifest' in final_prompt
    assert 'never call save_artifacts' in final_prompt
    assert 'complete visible Chinese delivery summary' in final_prompt


def test_markdown_and_html_are_one_semantic_artifact_with_interactive_visuals(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    source = tmp_path / 'direction.md'
    source.write_text(
        '# 产品方向说明\n\n<a id="block-validation"></a>\n\n## 验证计划\n\n'
        '```mermaid\n'
        'timeline\n  T0 : 明确问题\n  T+1 : 验证假设\n'
        '```\n\n'
        '```mermaid\n'
        'flowchart LR\n  A[提交方案] --> B{校验通过}\n  B --> C[进入评审]\n  B --> D[返回修改]\n'
        '```\n\n'
        '```mermaid\n'
        'quadrantChart\n  x-axis 低成本 --> 高成本\n  y-axis 低价值 --> 高价值\n  方向A: [0.3, 0.8]\n'
        '```\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path), params={'step_id': 'write_direction_document'},
    ))
    html_path = Path(bridge._render_markdown_html('direction', str(source)))
    html = html_path.read_text(encoding='utf-8')
    assert '<!doctype html>' in html
    assert 'HTML 交互视图' in html
    assert 'timeline' in html and 'quadrantChart' in html
    assert '四象限坐标图' in html and '数据流图' in html and '查看图表源码' in html
    assert 'flow-svg' in html and 'flow-edge' in html
    assert '<svg' in html and 'role="img"' in html
    assert '\x08' not in html
    assert '&lt;a id=&quot;block-validation&quot;&gt;' not in html
    assert 'min-width:max-content' not in html
    assert '<nav aria-label="文档目录"' in html
    assert 'cdn' not in html.lower()


def test_product_workflow_has_bounded_prompts_and_pure_routers():
    root = Path(__file__).resolve().parents[4] / 'workflows/product_solution_delivery'
    graph = yaml.safe_load((root / 'scenario/state.yml').read_text())
    retrieval_tools = {'web_search', 'url_fetch', 'kb'}

    for router in ('route_product_stage', 'route_design_scope'):
        assert retrieval_tools.isdisjoint(graph['steps'][router]['tools'])
    for step_id, step in graph['steps'].items():
        policy = step['execution']
        assert policy['max_rounds'] >= 2
        assert policy['timeout_seconds'] > 0
        assert policy['hard_repeat_limit'] == 3
        assert policy['disable_artifact_reads'] is True
        assert policy['compact_summary'] is True
        prompt = step.get('prompt', '')
        assert not ('exactly once' in prompt and 'retry' in prompt), step_id
