import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path

import pytest
import yaml


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    if name in {
        'lazyllm', 'lazyllm.tools', 'lazyllm.tools.writer', 'lazymind',
        'lazymind.chat', 'lazymind.chat.engine', 'lazymind.chat.engine.subagent',
        'lazymind.chat.engine.tools',
    }:
        module.__path__ = []
    return module


def _load_writer_bridge():
    stubs = {
        'lazyllm': _stub_module('lazyllm', AutoModel=object),
        'lazyllm.tools': _stub_module('lazyllm.tools'),
        'lazyllm.tools.writer': _stub_module('lazyllm.tools.writer'),
        'lazyllm.tools.writer.data_models': _stub_module(
            'lazyllm.tools.writer.data_models', StringReplaceSet=object,
        ),
        'lazyllm.tools.writer.tools': _stub_module(
            'lazyllm.tools.writer.tools', WriterRevisionTools=object,
        ),
        'lazymind': _stub_module('lazymind'),
        'lazymind.document_tools': _stub_module(
            'lazymind.document_tools',
            DraftMarkdownStreamEventEmitter=object,
            WriterCreateToolkit=object,
            WriterRevisionToolkit=object,
        ),
        'lazymind.chat': _stub_module('lazymind.chat'),
        'lazymind.chat.engine': _stub_module('lazymind.chat.engine'),
        'lazymind.chat.engine.subagent': _stub_module('lazymind.chat.engine.subagent'),
        'lazymind.chat.engine.subagent.context': _stub_module(
            'lazymind.chat.engine.subagent.context', require_context=lambda: None,
        ),
        'lazymind.chat.engine.subagent.tools': _stub_module(
            'lazymind.chat.engine.subagent.tools', _save_artifact=lambda **_kwargs: None,
        ),
        'lazymind.chat.engine.tools': _stub_module('lazymind.chat.engine.tools'),
        'lazymind.chat.engine.tools.writer': _stub_module(
            'lazymind.chat.engine.tools.writer',
            DraftMarkdownStreamEventEmitter=object,
            WriterCreateToolkit=object,
            WriterRevisionToolkit=object,
        ),
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        root = Path(__file__).resolve().parents[4]
        path = root / 'workflows' / 'product_solution_delivery' / 'scripts' / 'writer_bridge.py'
        spec = importlib.util.spec_from_file_location('product_writer_bridge_for_test', path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _load_contract_tools(tmp_path):
    context = types.SimpleNamespace(workspace_path=str(tmp_path))
    saved_artifacts = []

    def save_artifact(**kwargs):
        saved_artifacts.append(kwargs)
        return {'status': 'ok', 'key': kwargs.get('key')}

    stubs = {
        'lazymind': _stub_module('lazymind'),
        'lazymind.chat': _stub_module('lazymind.chat'),
        'lazymind.chat.engine': _stub_module('lazymind.chat.engine'),
        'lazymind.chat.engine.subagent': _stub_module('lazymind.chat.engine.subagent'),
        'lazymind.chat.engine.subagent.context': _stub_module(
            'lazymind.chat.engine.subagent.context', require_context=lambda: context,
        ),
        'lazymind.chat.engine.subagent.tools': _stub_module(
            'lazymind.chat.engine.subagent.tools', _save_artifact=save_artifact,
        ),
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        root = Path(__file__).resolve().parents[4]
        path = root / 'workflows' / 'product_solution_delivery' / 'scripts' / 'tools.py'
        spec = importlib.util.spec_from_file_location('product_contract_tools_for_test', path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._test_saved_artifacts = saved_artifacts
        return module
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_design_contract_loads_all_selected_domains_in_one_call(tmp_path):
    tools = _load_contract_tools(tmp_path)
    ctx = tools.require_context()
    ctx.params = {"remote_inputs": {"design_routing_record": {"data": {
        "primary_domains": list(tools.DESIGN_DOMAINS), "decisions": [],
    }}}}
    result = tools.load_product_skill_contract("design")
    for names in tools.DESIGN_DOMAIN_REFERENCES.values():
        for name in names:
            assert f"BEGIN children/product-design-full-cycle/references/{name}" in result["contract_text"]
    # Reading contracts neither accepts decisions nor changes the bound route.
    assert ctx.params["remote_inputs"]["design_routing_record"]["data"]["decisions"] == []


def test_contract_loads_only_exact_packaged_reference_resources(tmp_path):
    tools = _load_contract_tools(tmp_path)
    full_path = "children/product-design-full-cycle/references/domain-model.md"

    first = tools.load_product_skill_contract("design")
    assert full_path in first["available_resources"]
    assert full_path not in first["runtime_trace"]["loaded_resources"]

    result = tools.load_product_skill_contract(
        "design",
        ["references/domain-model.md", full_path],
    )

    assert result["runtime_trace"]["loaded_resources"].count(full_path) == 1
    assert result["ignored_reference_paths"] == []
    assert result["warning"] == ""


def test_contract_ignores_artifact_and_unknown_reference_paths_without_reading_them(
    monkeypatch, tmp_path,
):
    tools = _load_contract_tools(tmp_path)
    ctx = tools.require_context()
    ctx.params = {"remote_inputs": {"design_routing_record": {"data": {
        "primary_domains": ["domain_state"], "decisions": [],
    }}}}
    writer_path = str(tmp_path / "inputs" / "writer" / "design_document.md")
    requested = [
        writer_path,
        "inputs/material_digest.md",
        "outputs/design_document.md",
        "design_section_plan",
        "domain_state",
        "references/not-packaged.md",
        "children/write-prd/references/prd-contract.md",
    ]
    reads = []
    safe_read = tools._safe_read

    def recording_safe_read(path):
        reads.append(path)
        return safe_read(path)

    monkeypatch.setattr(tools, "_safe_read", recording_safe_read)
    result = tools.load_product_skill_contract("design", requested)

    assert result["ignored_reference_paths"] == requested
    assert "Ignored reference_paths" in result["warning"]
    assert result["runtime_trace"]["ignored_reference_paths"] == requested
    assert all(item not in reads for item in requested)
    # Bound design domains remain automatic even when the model supplies an invalid domain id.
    assert (
        "children/product-design-full-cycle/references/domain-model.md"
        in result["runtime_trace"]["loaded_resources"]
    )


@pytest.mark.parametrize(
    "reference_path",
    [
        "references/../SKILL.md",
        "..\\SKILL.md",
        "children/product-design-full-cycle/references/../../SKILL.md",
    ],
)
def test_contract_rejects_reference_path_traversal(tmp_path, reference_path):
    tools = _load_contract_tools(tmp_path)

    with pytest.raises(ValueError, match="stay inside the selected child Skill"):
        tools.load_product_skill_contract("design", [reference_path])


def test_product_outline_has_one_h1_and_contiguous_hierarchy():
    bridge = _load_writer_bridge()

    valid = bridge.validate_product_outline(
        'direction', '# 产品方向\n\n## 一句话方向\n\n## 目标用户与场景\n',
    )
    assert valid['valid'] is True
    assert valid['warnings']

    invalid = bridge.validate_product_outline(
        'direction', '# 产品方向\n\n### 跳级标题\n',
    )
    assert invalid['valid'] is False
    assert any('层级跳跃' in item for item in invalid['errors'])


def test_generated_outline_is_repaired_without_losing_outline_notes():
    bridge = _load_writer_bridge()

    normalized = bridge._normalize_generated_outline(
        'design', '### 核心流程\n\n- 保留这条说明\n\n##### 异常恢复',
    )

    assert bridge._heading_signature(normalized) == [
        (1, '产品方案'), (2, '核心流程'), (3, '异常恢复'),
    ]
    assert '- 保留这条说明' in normalized


def test_approved_outline_does_not_restore_deleted_template_sections():
    bridge = _load_writer_bridge()

    normalized = bridge._normalize_approved_outline('prd', '# 极简 PRD\n\n只保留必要内容。')

    assert normalized == '# 极简 PRD\n\n## 正文\n\n只保留必要内容。'
    assert '背景与目标' not in normalized


def test_product_draft_alignment_demotes_unapproved_headings_and_keeps_content():
    bridge = _load_writer_bridge()
    outline = '# 产品方向\n\n## 背景与证据\n\n## 范围与非目标\n'
    draft = '\n'.join([
        '# 产品方向', '## 背景与证据', '内容一。', '### 模型额外小结',
        '额外内容仍保留。', '## 范围与非目标', '内容二。',
    ])

    aligned = bridge._align_draft_headings(draft, outline)

    assert '### 模型额外小结' not in aligned
    assert '**模型额外小结**' in aligned
    assert '额外内容仍保留。' in aligned
    assert bridge._heading_signature(aligned) == bridge._heading_signature(outline)


def test_product_draft_alignment_preserves_missing_approved_heading_as_visible_gap():
    bridge = _load_writer_bridge()

    aligned = bridge._align_draft_headings(
        '# PRD\n\n## 背景与目标\n正文',
        '# PRD\n\n## 背景与目标\n\n## 验收标准\n',
    )

    assert '## 验收标准' in aligned
    assert '本节尚未生成有效正文，请在审批时补充。' in aligned
    assert bridge._heading_signature(aligned) == bridge._heading_signature(
        '# PRD\n\n## 背景与目标\n\n## 验收标准\n',
    )


def test_section_plan_uses_exact_approved_h2_order(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    task = tmp_path / 'writing_task.json'
    context = tmp_path / 'writing_context.json'
    outline = tmp_path / 'outline_document.md'
    task.write_text(json.dumps({'product_parameters': {'stage_id': 'review'}}), encoding='utf-8')
    context.write_text('{}', encoding='utf-8')
    outline.write_text('# 评审报告\n\n## 评审结论\n\n## P1 关键问题\n', encoding='utf-8')

    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)

    result = bridge.product_writer_plan_sections(str(task), str(outline), str(context))
    planned = json.loads(Path(result['section_instructions']).read_text(encoding='utf-8'))
    assert [item['section_title'] for item in planned['instructions']] == [
        '评审结论', 'P1 关键问题',
    ]
    assert all(item['instruction_id'] for item in planned['instructions'])
    assert all(item['content_ref']['heading_path'][0] == '评审报告'
               for item in planned['instructions'])
    assert all(item['section_goal'] for item in planned['instructions'])
    assert planned['meta']['deterministically_normalized'] is True


def test_section_plan_does_not_call_generative_planner(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    task = tmp_path / 'writing_task.json'
    context = tmp_path / 'writing_context.json'
    outline = tmp_path / 'outline_document.md'
    task.write_text(json.dumps({'product_parameters': {'stage_id': 'prd'}}), encoding='utf-8')
    context.write_text('{}', encoding='utf-8')
    outline.write_text('# PRD\n\n## 背景与目标\n\n## 验收标准\n', encoding='utf-8')

    class FakeToolkit:
        def __init__(self):
            raise AssertionError('the approved outline must not use a generative planner')

    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)

    result = bridge.product_writer_plan_sections(str(task), str(outline), str(context))
    planned = json.loads(Path(result['section_instructions']).read_text(encoding='utf-8'))
    assert [item['section_title'] for item in planned['instructions']] == [
        '背景与目标', '验收标准',
    ]
    assert all(set(('instruction_id', 'content_ref', 'section_goal')) <= set(item)
               for item in planned['instructions'])


def test_context_refresh_failure_preserves_completed_stage(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    content = tmp_path / 'draft.md'
    context = tmp_path / 'writing_context.json'
    content.write_text('# 已完成正文\n', encoding='utf-8')
    context.write_text(json.dumps({'meta': {'existing': True}}), encoding='utf-8')

    class FakeToolkit:
        def update_writing_context(self, **_kwargs):
            raise RuntimeError('temporary model failure')

    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)

    result = bridge.product_writer_update_context(str(content), str(context))
    updated = json.loads(Path(result).read_text(encoding='utf-8'))
    assert updated['meta']['existing'] is True
    assert 'temporary model failure' in updated['meta']['context_update_warning']


def test_prepare_context_profiles_approved_upstream_artifacts(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    profiles = tmp_path / 'resource_profiles.json'
    upstream = tmp_path / 'direction.md'
    profiles.write_text(json.dumps([{'id': 'uploaded-material'}]), encoding='utf-8')
    upstream.write_text('# 已批准产品方向\n', encoding='utf-8')

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def build_resources(self, file_paths_json, **_kwargs):
            return file_paths_json

        def profile_resources(self, **_kwargs):
            return json.dumps([{'id': 'approved-direction'}])

        def create_writing_context(self, **_kwargs):
            return '{}'

    output = tmp_path / 'output'
    output.mkdir()
    context = types.SimpleNamespace(params={'session_id': 'test-session'})
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, '_workspace_root', lambda: tmp_path)
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)

    result = bridge.product_writer_prepare_context(
        '生成产品方案',
        'design',
        json.dumps({'selected_stage': 'design'}),
        'WEB-001 evidence',
        resource_profiles_path=str(profiles),
        upstream_artifact_paths_json=json.dumps([str(upstream)]),
    )

    combined = json.loads(Path(result['resource_profiles']).read_text(encoding='utf-8'))
    assert combined == [{'id': 'uploaded-material'}, {'id': 'approved-direction'}]


def test_prepare_context_rejects_later_stage_in_planned_chain(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text('[]', encoding='utf-8')

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def create_writing_context(self, **_kwargs):
            return '{}'

    output = tmp_path / 'output'
    output.mkdir()
    context = types.SimpleNamespace(params={'session_id': 'chain-session'})
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, '_workspace_root', lambda: tmp_path)
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)
    plan = json.dumps({'selected_stage': 'direction', 'stage_chain': ['direction', 'design']})

    with pytest.raises(ValueError, match='selected_stage'):
        bridge.product_writer_prepare_context(
            '不能在当前 Session 自动继续生成产品方案',
            'design',
            plan,
            '',
            resource_profiles_path=str(profiles),
        )


def test_prepare_context_accepts_json_and_evidence_artifact_paths(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    profiles = tmp_path / 'resource_profiles.json'
    routing = tmp_path / 'execution_plan.json'
    evidence = tmp_path / 'research_evidence.md'
    profiles.write_text('[]', encoding='utf-8')
    routing.write_text(json.dumps({'stage_chain': ['direction']}), encoding='utf-8')
    evidence.write_text('KB-001 已核验材料', encoding='utf-8')

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def create_writing_context(self, **_kwargs):
            return '{}'

    output = tmp_path / 'output'
    output.mkdir()
    context = types.SimpleNamespace(params={'session_id': 'path-session'})
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, '_workspace_root', lambda: tmp_path)
    monkeypatch.setattr(bridge, '_run_root', lambda _name: output)

    result = bridge.product_writer_prepare_context(
        '生成产品方向',
        'direction',
        str(routing),
        str(evidence),
        resource_profiles_path=str(profiles),
    )

    stored = json.loads(Path(result['writing_context']).read_text(encoding='utf-8'))
    contract_fact = next(
        fact for fact in stored['facts'] if fact['fact_id'] == 'product-stage-contract'
    )
    assert isinstance(contract_fact['value'], str)
    assert json.loads(contract_fact['value'])['registered_evidence'] == 'KB-001 已核验材料'


def test_prepare_context_resolves_nested_bound_inputs_and_cross_task_artifacts(
    monkeypatch, tmp_path,
):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'current-task'
    upstream_workspace = tmp_path / 'previous-task'
    workspace.mkdir()
    upstream_workspace.mkdir()
    plan = upstream_workspace / 'execution_plan.json'
    evidence = upstream_workspace / 'research_evidence.md'
    profiles = upstream_workspace / 'resource_profiles.json'
    direction = upstream_workspace / 'direction_document.md'
    plan.write_text(json.dumps({
        'data': json.dumps({
            'execution_plan': {
                'stage_chain': [],
                'selected_stage': 'product-design-full-cycle',
                'word_target': 1200,
            },
        }, ensure_ascii=False),
    }, ensure_ascii=False), encoding='utf-8')
    evidence.write_text(json.dumps({'text': 'KB-001 已核验资料'}), encoding='utf-8')
    profiles.write_text(json.dumps(json.dumps({
        'data': [{'id': 'shared-profile'}],
    }, ensure_ascii=False), ensure_ascii=False), encoding='utf-8')
    direction.write_text('# 已批准产品方向\n', encoding='utf-8')

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return json.dumps(json.dumps({'data': {}}, ensure_ascii=False), ensure_ascii=False)

        def build_resources(self, file_paths_json, **_kwargs):
            return file_paths_json

        def profile_resources(self, **_kwargs):
            return json.dumps({'profiles': [{'id': 'approved-direction'}]})

        def create_writing_context(self, **_kwargs):
            return json.dumps({'data': json.dumps({'facts': []})})

    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={
            'session_id': 'bound-session',
            'step_id': 'build_design_outline',
            'remote_inputs': {
                'execution_plan': str(plan),
                'research_evidence': str(evidence),
                'resource_profiles': str(profiles),
                'direction_document': str(direction),
            },
        },
    )
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    result = bridge.product_writer_prepare_context('生成产品方案', 'plan')

    task = json.loads(Path(result['writing_task']).read_text(encoding='utf-8'))
    combined = json.loads(Path(result['resource_profiles']).read_text(encoding='utf-8'))
    stored_context = json.loads(Path(result['writing_context']).read_text(encoding='utf-8'))
    contract = next(
        item for item in stored_context['facts']
        if item['fact_id'] == 'product-stage-contract'
    )
    assert task['product_parameters']['stage_id'] == 'design'
    assert task['product_parameters']['word_target'] == 1200
    assert combined == [{'id': 'shared-profile'}, {'id': 'approved-direction'}]
    assert json.loads(contract['value'])['registered_evidence'] == 'KB-001 已核验资料'


def test_source_paths_reject_unbound_file_outside_current_workspace(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'current-task'
    workspace.mkdir()
    unbound = tmp_path / 'private.txt'
    unbound.write_text('not a workflow input', encoding='utf-8')
    context = types.SimpleNamespace(workspace_path=str(workspace), params={'remote_inputs': {}})
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    with pytest.raises(ValueError, match='exact bound Workflow input'):
        bridge._source_paths([str(unbound)])


def test_profile_product_materials_ignores_unbound_slot_name(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'session_id': 'router-session', 'remote_inputs': {
            'product_goal': '企业会议决策助手',
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    result = bridge.profile_product_materials(
        '企业会议决策助手',
        '["product_materials"]',
    )

    assert result['profiles'] == []
    assert result['files'] == []
    assert result['message'] == 'No product material files were bound.'
    assert json.loads(Path(result['resource_profiles']).read_text(encoding='utf-8')) == []


def test_profile_product_materials_accepts_native_empty_array(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'session_id': 'router-session', 'remote_inputs': {
            'product_goal': '企业会议决策助手',
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    result = bridge.profile_product_materials('企业会议决策助手', [])

    assert result['profiles'] == []
    assert result['files'] == []
    assert json.loads(Path(result['resource_profiles']).read_text(encoding='utf-8')) == []


def test_profile_product_materials_ignores_known_non_file_router_slots(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'session_id': 'router-session', 'remote_inputs': {
            'product_goal': '企业会议决策助手',
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    result = bridge.profile_product_materials(
        '企业会议决策助手',
        json.dumps(sorted(bridge.PRODUCT_NON_FILE_SOURCE_SLOTS)),
    )

    assert result['profiles'] == []
    assert result['files'] == []
    assert result['message'] == 'No product material files were bound.'


def test_profile_product_materials_rejects_unknown_missing_path(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={'session_id': 'router-session', 'remote_inputs': {}},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)

    with pytest.raises(FileNotFoundError, match='Product source material does not exist'):
        bridge.profile_product_materials(
            '企业会议决策助手',
            json.dumps([str(workspace / 'missing-material.md')]),
        )


def test_profile_product_materials_mixed_slots_resolve_files_and_reject_bad_path(
    monkeypatch, tmp_path,
):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'workspace'
    upload = tmp_path / 'uploads' / 'brief.md'
    workspace.mkdir()
    upload.parent.mkdir()
    upload.write_text('# 已绑定材料\n', encoding='utf-8')
    captured = {}

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def build_resources(self, file_paths_json, **_kwargs):
            captured['paths'] = json.loads(file_paths_json)
            return '{}'

        def profile_resources(self, **_kwargs):
            return '[{"id":"bound-material"}]'

    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={'session_id': 'router-session', 'remote_inputs': {
            'product_goal': '企业会议决策助手',
            'product_materials': [str(upload)],
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)

    result = bridge.profile_product_materials(
        '企业会议决策助手',
        json.dumps(['product_goal', 'product_materials']),
    )

    assert captured['paths'] == [str(upload)]
    assert result['files'] == ['brief.md']
    assert result['profiles'] == [{'id': 'bound-material'}]

    with pytest.raises(FileNotFoundError, match='Product source material does not exist'):
        bridge.profile_product_materials(
            '企业会议决策助手',
            json.dumps([
                'product_goal', 'product_materials', str(workspace / 'missing-material.md'),
            ]),
        )


def test_product_material_slot_sets_match_external_workflow_inputs():
    bridge = _load_writer_bridge()
    root = Path(__file__).resolve().parents[4]
    workflow = yaml.safe_load(
        (root / 'workflows' / 'product_solution_delivery' / 'workflow.yaml').read_text(
            encoding='utf-8',
        )
    )
    external_slots = [slot for slot in workflow['slots'] if slot.get('external') is True]
    file_slots = frozenset(
        slot['id'] for slot in external_slots if str(slot.get('type') or 'text').lower() == 'file'
    )
    non_file_slots = frozenset(
        slot['id'] for slot in external_slots if str(slot.get('type') or 'text').lower() != 'file'
    )

    assert bridge.PRODUCT_MATERIAL_SOURCE_SLOTS == file_slots
    assert bridge.PRODUCT_NON_FILE_SOURCE_SLOTS == non_file_slots


def test_profile_product_materials_resolves_bound_slot_name(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'workspace'
    upload = tmp_path / 'uploads' / 'brief.md'
    workspace.mkdir()
    upload.parent.mkdir()
    upload.write_text('# 已绑定材料\n', encoding='utf-8')
    captured = {}

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def build_resources(self, file_paths_json, **_kwargs):
            captured['paths'] = json.loads(file_paths_json)
            return '{}'

        def profile_resources(self, **_kwargs):
            return '[{"id":"bound-material"}]'

    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={'session_id': 'router-session', 'remote_inputs': {
            'product_materials': [str(upload)],
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)

    result = bridge.profile_product_materials(
        '企业会议决策助手',
        '["product_materials"]',
    )

    assert captured['paths'] == [str(upload)]
    assert result['files'] == ['brief.md']
    assert result['profiles'] == [{'id': 'bound-material'}]


def test_profile_product_materials_resolves_labeled_bound_path(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'workspace'
    material = workspace / 'inputs' / 'design.md'
    material.parent.mkdir(parents=True)
    material.write_text('# 已有产品方案\n', encoding='utf-8')
    captured = {}

    class FakeToolkit:
        def build_writing_task(self, **_kwargs):
            return '{}'

        def build_resources(self, file_paths_json, **_kwargs):
            captured['paths'] = json.loads(file_paths_json)
            return '{}'

        def profile_resources(self, **_kwargs):
            return '[{"id":"upstream-design"}]'

    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={'session_id': 'router-session', 'remote_inputs': {
            'upstream_design': str(material),
        }},
    )
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(bridge, 'WriterCreateToolkit', FakeToolkit)

    result = bridge.profile_product_materials(
        '继续完善产品需求',
        json.dumps([f'upstream_design={material}']),
    )

    assert captured['paths'] == [str(material)]
    assert result['files'] == ['design.md']
    assert result['profiles'] == [{'id': 'upstream-design'}]


def test_document_pipeline_uses_bound_inputs_without_agent_file_plumbing(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    workspace = tmp_path / 'current-task'
    upstream = tmp_path / 'previous-task'
    workspace.mkdir()
    upstream.mkdir()
    task = upstream / 'writing_task.json'
    outline = upstream / 'outline_document.md'
    context_file = upstream / 'writing_context.json'
    task.write_text('{}', encoding='utf-8')
    outline.write_text('# 产品方向\n\n## 目标\n', encoding='utf-8')
    context_file.write_text('{}', encoding='utf-8')
    chapter = workspace / 'chapter.md'
    document = workspace / 'document.md'
    chapter.write_text('## 目标\n\n明确问题。\n', encoding='utf-8')
    document.write_text('# 产品方向\n\n## 目标\n\n明确问题。\n', encoding='utf-8')
    context = types.SimpleNamespace(
        workspace_path=str(workspace),
        params={
            'step_id': 'write_direction_document',
            'remote_inputs': {
                'direction_task': {'value': {'path': str(task)}},
                'direction_outline': str(outline),
                'direction_context_approved': str(context_file),
            },
        },
    )
    calls = []
    monkeypatch.setattr(bridge, 'require_context', lambda: context)
    monkeypatch.setattr(
        bridge, 'product_writer_plan_sections',
        lambda *args: calls.append(('plan', args)) or {'section_instructions': '/out/plan.json'},
    )
    monkeypatch.setattr(
        bridge, 'product_writer_write_sections',
        lambda *args: calls.append(('write', args)) or [str(chapter)],
    )
    monkeypatch.setattr(
        bridge, 'product_writer_assemble_draft',
        lambda *args: calls.append(('assemble', args)) or str(document),
    )
    monkeypatch.setattr(
        bridge, 'product_writer_update_context',
        lambda *args: calls.append(('context', args)) or '/out/context.json',
    )

    result = bridge.product_writer_generate_document_from_inputs('not-the-runtime-stage')

    assert [name for name, _ in calls] == ['plan', 'write', 'assemble', 'context']
    assert calls[0][1] == (str(task), str(outline), str(context_file))
    assert Path(result['document_html']).is_file()
    assert result == {
        'section_plan': '/out/plan.json',
        'chapter_count': 1,
        'chapter_publish': {
            'slot': 'direction_chapters',
            'expected_count': 1,
            'published_count': 1,
            'complete': True,
            'warnings': [],
        },
        'document': str(document),
        'document_html': result['document_html'],
        'writing_context': '/out/context.json',
        'warnings': [],
    }


def test_outline_pipeline_keeps_bound_input_plumbing_inside_bridge(monkeypatch, tmp_path):
    bridge = _load_writer_bridge()
    monkeypatch.setattr(bridge, '_remote_inputs', lambda: {})
    task = tmp_path / 'task.json'
    context_file = tmp_path / 'context.json'
    outline = tmp_path / 'outline.md'
    approved = tmp_path / 'approved.json'
    for path, content in (
        (task, '{}'), (context_file, '{}'),
        (outline, '# 产品方向\n\n## 一句话方向\n'), (approved, '{}'),
    ):
        path.write_text(content, encoding='utf-8')
    calls = []
    monkeypatch.setattr(bridge, '_runtime_stage', lambda: 'direction')
    monkeypatch.setattr(
        bridge, 'product_writer_prepare_context',
        lambda **kwargs: calls.append(('prepare', kwargs)) or {
            'writing_task': str(task), 'writing_context': str(context_file),
        },
    )
    monkeypatch.setattr(
        bridge, 'product_writer_generate_outline',
        lambda *args: calls.append(('generate', args)) or str(outline),
    )
    monkeypatch.setattr(
        bridge, 'product_writer_update_context',
        lambda *args: calls.append(('context', args)) or str(approved),
    )

    result = bridge.product_writer_generate_outline_from_inputs('产品目标', 'wrong-stage')

    assert [name for name, _ in calls] == ['prepare', 'generate', 'context']
    assert result['writing_task'] == str(task)
    assert result['outline'] == str(outline)
    assert result['approved_context'] == str(approved)
    assert 'PASS' in result['outline_report']


def test_embedded_contract_and_workspace_local_html_output(tmp_path):
    tools = _load_contract_tools(tmp_path)

    contract = tools.load_product_skill_contract('prd')
    assert contract['skill_name'] == 'write-prd'
    assert '# 需求文档' in contract['contract_text']
    assert 'preserve the existing artifact structure' in contract['contract_text'].lower()

    result = tools.write_product_artifact(
        'prototype.html',
        '<!doctype html><html><head><title>原型</title>'
        '<meta name="viewport" content="width=device-width"></head>'
        '<body><h1>原型</h1><button>下一步</button></body></html>',
        validate_as='prototype',
    )
    output = Path(result['path'])
    assert result['validation']['valid'] is True
    assert output.is_relative_to(tmp_path)
    assert output.name.endswith('prototype.html')


def test_router_contract_exposes_authoritative_host_adapter_overrides(tmp_path):
    tools = _load_contract_tools(tmp_path)

    contract = tools.load_product_skill_contract('router')

    assert 'LAZYMIND HOST ADAPTER OVERRIDES' in contract['contract_text']
    assert 'Do not ask the separate reference-sample question' in contract['contract_text']
    assert 'Router only selects scope' in contract['contract_text']
    assert 'Host execution limits' in contract['contract_text']
    assert 'preserve the existing artifact structure' not in contract['contract_text'].lower()
    assert len(contract['contract_text'].encode('utf-8')) < 12 * 1024
    assert '--- BEGIN assets/workspace-template.json ---' not in contract['contract_text']


def test_skill_contract_accepts_source_skill_name_as_stage_alias(tmp_path):
    tools = _load_contract_tools(tmp_path)

    contract = tools.load_product_skill_contract('prepare-development-handoff')

    assert contract['stage_id'] == 'handoff'
    assert contract['skill_name'] == 'prepare-development-handoff'


def test_stage_contract_is_compact_and_excludes_source_snapshots(tmp_path):
    tools = _load_contract_tools(tmp_path)

    contract = tools.load_product_skill_contract('competitive')

    assert 'children/analyze-competitors/SKILL.md' in contract['contract_text']
    assert 'source-snapshots' not in contract['contract_text']
    assert '--- BEGIN SKILL.md ---' not in contract['contract_text']
    assert 'preserve the existing artifact structure' in contract['contract_text'].lower()


def test_non_writer_stage_loader_reads_only_bound_materials(tmp_path):
    tools = _load_contract_tools(tmp_path)
    evidence = tmp_path / 'evidence.json'
    direction = tmp_path / 'direction.md'
    evidence.write_text(json.dumps({'data': 'KB-001 已核验事实'}), encoding='utf-8')
    direction.write_text('# 已批准方向\n', encoding='utf-8')
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'remote_inputs': {
            'research_evidence': str(evidence),
            'direction_document': str(direction),
        }},
    )
    tools.require_context = lambda: context

    result = tools.load_product_stage_inputs('competitive')

    assert result['materials']['research_evidence'] == 'KB-001 已核验事实'
    assert result['materials']['direction_document'] == '# 已批准方向'
    assert 'material_digest' in result['missing_optional_slots']


def test_non_writer_stage_loader_accepts_inline_scalar_materials(tmp_path):
    tools = _load_contract_tools(tmp_path)
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'remote_inputs': {
            'execution_plan': {'stage_chain': ['competitive']},
            'research_evidence': 'WEB-001 已核验事实',
            'material_digest': '没有额外附件。',
        }},
    )
    tools.require_context = lambda: context

    result = tools.load_product_stage_inputs('competitive')

    assert result['materials'] == {
        'execution_plan': {'stage_chain': ['competitive']},
        'research_evidence': 'WEB-001 已核验事实',
        'material_digest': '没有额外附件。',
    }


def test_product_workflow_keeps_scalar_inputs_as_values_and_files_as_paths():
    root = Path(__file__).resolve().parents[4]
    workflow_root = root / 'workflows' / 'product_solution_delivery'
    state = (workflow_root / 'scenario' / 'state.yml').read_text(encoding='utf-8')
    workflow = (workflow_root / 'workflow.yaml').read_text(encoding='utf-8')
    slot_types = dict(re.findall(
        r'^  - \{id: ([a-z][a-z0-9_]*), .* type: ([a-z_]+),',
        workflow, flags=re.MULTILINE,
    ))

    for material, attributes in re.findall(
        r'^      - \{material: ([a-z][a-z0-9_]*)([^}]*)\}',
        state, flags=re.MULTILINE,
    ):
        transport_match = re.search(r'\btransport:\s*([a-z]+)', attributes)
        transport = transport_match.group(1) if transport_match else 'auto'
        if slot_types[material] in {'text', 'json'}:
            assert transport in {'auto', 'value'}, (
                f'{material} must remain an inline scalar for the product adapters'
            )
        else:
            assert transport in {'auto', 'path'}, (
                f'{material} must remain a file path for the product adapters'
            )


def test_heavy_design_evidence_fails_closed_when_retrieval_is_unavailable():
    root = Path(__file__).resolve().parents[4]
    workflow = yaml.safe_load(
        (root / 'workflows' / 'product_solution_delivery' / 'workflow.yaml')
        .read_text(encoding='utf-8')
    )
    state = yaml.safe_load(
        (root / 'workflows' / 'product_solution_delivery' / 'scenario' / 'state.yml')
        .read_text(encoding='utf-8')
    )
    prompt = state['steps']['collect_design_heavy_evidence']['prompt']
    normalized = ' '.join(prompt.split())

    assert 'Write the packet in Chinese' in normalized
    assert 'web_search or url_fetch is unavailable' in normalized
    assert 'classify the unsupported conclusion as unknown or a hypothesis' in normalized
    assert 'must not say that there are no gaps' in normalized
    assert 'Absence of a retrieved counterexample is not evidence' in normalized
    assert 'replying with a plan or future intention is not completion' in normalized
    assert 'through exactly one of the two publisher paths' in normalized
    assert 'call publish_design_heavy_unavailable() with exactly {}' in normalized
    assert 'do not construct value, decisions, tool_statuses or source placeholders' in normalized
    assert 'Only when retrieval returned at least one usable exact source locator' in normalized
    assert 'top-level argument named value' in normalized
    assert 'under 700 characters' in normalized
    assert 'Include at most one decision' in normalized
    assert 'Never place decisions inside tool_statuses' in normalized
    assert 'inspect the actual callable tool list' in normalized
    assert 'If web_search is actually callable' in normalized
    assert 'both a knowledge-base search tool is actually callable' in normalized
    assert 'runtime supplied exact inherited kb_ids' in normalized
    assert 'do not emit a query, an arguments fragment' in normalized
    assert 'immediately call publish_design_heavy_unavailable with exactly {}' in normalized
    assert 'never guess "default", enumerate KBs, or invent an id' in normalized
    assert 'url_fetch only with an exact URL returned by successful web_search' in normalized
    assert 'available_resources are embedded package identifiers' in normalized
    assert 'keeps unbound findings at E0' in normalized
    step = state['steps']['collect_design_heavy_evidence']
    assert step['terminal_tools'] == ['publish_design_heavy_unavailable']
    assert step['fail_fast_tools'] == ['publish_design_heavy_unavailable']
    assert 'publish_design_heavy_evidence' not in step['terminal_tools']
    assert 'publish_design_heavy_evidence' not in step['fail_fast_tools']
    publisher_tools = {
        'publish_design_heavy_evidence', 'publish_design_heavy_unavailable',
    }
    assert publisher_tools <= set(step['tools'])
    assert set(step['terminal_tools']) | set(step['fail_fast_tools']) <= set(step['tools'])
    assert step['execution']['tool_call_limits']['publish_design_heavy_evidence'] == 1
    assert step['execution']['tool_call_limits']['publish_design_heavy_unavailable'] == 1
    assert step['execution']['publisher_fallback_tool'] == 'publish_design_heavy_unavailable'
    assert 'design_heavy_evidence' in workflow['runtime']['publisher_owned_slots']
    assert 'publish_design_heavy_evidence' in {
        function
        for script in workflow['tool_scripts']
        for function in script.get('functions', [])
    }
    assert 'publish_design_heavy_unavailable' in {
        function
        for script in workflow['tool_scripts']
        for function in script.get('functions', [])
    }


def test_heavy_design_evidence_publisher_emits_conservative_chinese_packet(tmp_path):
    tools = _load_contract_tools(tmp_path)
    context = tools.require_context()
    context.task_id = 'task-heavy-evidence'
    context.db = types.SimpleNamespace(load_task=lambda _task_id: {'sources': [{
        'source_id': 'WEB-001',
        'title': '候选公开资料',
        'url': 'https://example.test/evidence',
    }]})
    context.params = {'remote_inputs': {'design_routing_record': {'data': {
        'primary_domains': [
            'behavior_policy_trust', 'journey_interaction_service',
            'content_communication',
        ],
        'linked_domains': ['ui_visual_system', 'ia_semantics'],
        'overall_effort': 'heavy',
        'decisions': [
            {
                'decision_id': 'DES-001',
                'decision_question': '谁可触发自动写入？',
                'primary_domain': 'behavior_policy_trust',
                'linked_domains': ['journey_interaction_service'],
                'effort': 'heavy',
                'effort_reasons': ['触发信任风险'],
                'hard_gates': [
                    'privacy', 'identity', 'permission', 'silent_write', 'cross_tenant',
                ],
            },
            {
                'decision_id': 'DES-002',
                'decision_question': '失败后如何恢复？',
                'primary_domain': 'journey_interaction_service',
                'linked_domains': ['behavior_policy_trust'],
                'effort': 'heavy',
                'effort_reasons': ['跨模块恢复路径'],
                'hard_gates': [],
            },
            {
                'decision_id': 'DES-003',
                'decision_question': '用户如何理解同步状态？',
                'primary_domain': 'content_communication',
                'linked_domains': ['journey_interaction_service'],
                'effort': 'light',
                'effort_reasons': ['文案可逆'],
                'hard_gates': [],
            },
        ],
        'escalation_triggers': [
            'sustained_counterexamples', 'practice_divergence', 'trust_risk',
        ],
    }}}}

    result = tools.publish_design_heavy_evidence()

    assert result['status'] == 'published'
    assert result['evidence_ceiling'] == 'E0'
    assert result['decision_count'] == 3
    assert result['registered_source_count'] == 1
    assert result['bound_source_count'] == 0
    assert result['_agent_control'] == {
        'stop': True,
        'reason': 'workflow_publisher_completed',
        'final_text': '调研与待确认事项已整理，等待确认。',
    }
    assert result['e1_source_count'] == 0
    assert result['retrieval_status'] == 'limited'
    assert result['hard_gates'] == [
        'cross_tenant', 'identity', 'permission', 'privacy', 'silent_write',
    ]
    saved = tools._test_saved_artifacts[-1]
    assert saved['key'] == 'design_heavy_evidence'
    assert saved['source_tool'] == 'publish_design_heavy_evidence'
    assert saved['internal_publish'] is True
    packet = saved['value']
    assert '谁可触发自动写入？' in packet
    assert '失败后如何恢复？' in packet
    assert '用户如何理解同步状态？' in packet
    for gate in (
        'privacy', 'identity', 'permission', 'silent_write', 'cross_tenant',
        'high_loss_irreversible',
    ):
        assert f'`{gate}`' not in packet
    assert '隐私：需要确认' in packet
    assert '高损失且不可逆：当前信息未显示有此风险' in packet
    assert '证据强度上限' not in packet
    assert '本轮未使用外部资料' in packet
    assert '候选公开资料 · https://example.test/evidence' in packet
    assert '不能据此认为没有例外' in packet
    assert '确认前不会启用' in packet
    assert '可核对的授权主体、触发条件、作用范围、拒绝/撤销、审计记录和责任归属信息' in packet
    assert '授权主体、触发条件、作用范围、拒绝/撤销、审计记录和责任归属' in packet
    assert '可核对的触发入口、关键路径、等待/失败反馈、人工接管和服务恢复信息' in packet
    assert '触发入口、关键路径、等待/失败反馈、人工接管和服务恢复' in packet

    context.db = types.SimpleNamespace(load_task=lambda _task_id: {'sources': []})
    assert len(inspect.signature(tools.publish_design_heavy_unavailable).parameters) == 1
    unavailable = tools.publish_design_heavy_unavailable()
    assert unavailable['status'] == 'published'
    assert unavailable['evidence_ceiling'] == 'E0'
    assert unavailable['retrieval_status'] == 'unavailable'
    assert unavailable['decision_count'] == 3
    unavailable_packet = tools._test_saved_artifacts[-1]['value']
    assert '本轮未使用外部资料' in unavailable_packet
    assert '`unavailable`' not in unavailable_packet
    wrapped_unavailable = tools.publish_design_heavy_unavailable({})
    assert wrapped_unavailable['retrieval_status'] == 'unavailable'
    with pytest.raises(ValueError, match='empty object'):
        tools.publish_design_heavy_unavailable({'finding': '未经验证的内容'})

    context.db = types.SimpleNamespace(load_task=lambda _task_id: {'sources': [{
        'source_id': 'WEB-001',
        'title': '候选公开资料',
        'url': 'https://example.test/evidence',
    }]})
    sourced = tools.publish_design_heavy_evidence({
        'retrieval_status': 'completed',
        'tool_statuses': {
            'web_search': {'status': 'succeeded', 'note': '取得一条候选来源'},
            'url_fetch': {'status': 'partial', 'note': '只有公开页面'},
            'kb': {'status': 'unavailable', 'note': '没有已绑定知识库'},
        },
        'decisions': [
            {
                'decision_id': 'DES-001',
                'finding': '公开材料显示高风险写入应有显式授权。',
                'source_refs': ['https://example.test/evidence'],
                'counterevidence': '尚未取得静默写入的负向样本。',
                'conditions': ['企业管理员与普通成员权限不同'],
                'remaining_gaps': ['缺少真实产品界面与撤销测试'],
            },
            {
                'decision_id': 'DES-002',
                'finding': '失败后可能需要人工恢复。',
                'source_refs': [
                    'WEB-001',
                    'https://fabricated.test/not-registered',
                ],
                'counterevidence': '另一类产品可能自动重试。',
                'conditions': ['失败可补偿时自动重试成本较低'],
            },
        ],
    })

    assert sourced['evidence_ceiling'] == 'E1'
    assert sourced['bound_source_count'] == 1
    assert sourced['e1_source_count'] == 1
    assert sourced['rejected_source_ref_count'] == 2
    assert sourced['retrieval_status'] == 'limited'
    sourced_packet = tools._test_saved_artifacts[-1]['value']
    assert '可参考资料：候选公开资料' in sourced_packet
    assert '公开材料显示高风险写入应有显式授权。' in sourced_packet
    assert '证据强度上限' not in sourced_packet
    assert '已找到可参考的资料' in sourced_packet
    assert '执行者报告 completed' in sourced_packet
    assert '受控状态保持 limited' in sourced_packet
    assert 'WEB-001、https://fabricated.test/not-registered' in sourced_packet
    assert 'https://fabricated.test/not-registered' in sourced_packet
    assert '失败后可能需要人工恢复。（仍需验证）' in sourced_packet
    assert '另一类产品可能自动重试。（仍需验证）' in sourced_packet
    assert '失败可补偿时自动重试成本较低（仍需验证）' in sourced_packet
    assert '至少六个不同产品形态' in sourced_packet
    assert '至少比较页内调整、改名串联、终态重构三档成本方案' in sourced_packet
    assert '至少覆盖官方材料、真实界面及一种一手用户反馈来源' in sourced_packet
    assert '以上内容尚未确认，确认前不会写入正式方案' in sourced_packet

    empty_finding = tools.publish_design_heavy_evidence({
        'retrieval_status': 'limited',
        'decisions': [{
            'decision_id': 'DES-001',
            'source_refs': ['https://example.test/evidence'],
        }],
    })
    assert empty_finding['bound_source_count'] == 1
    assert empty_finding['e1_source_count'] == 0
    assert empty_finding['evidence_ceiling'] == 'E0'


def test_heavy_design_evidence_reads_live_attempt_sources_before_task_snapshot(
    tmp_path, monkeypatch,
):
    tools = _load_contract_tools(tmp_path)
    context = tools.require_context()
    context.task_id = 'task-with-stale-snapshot'
    context.db = types.SimpleNamespace(load_task=lambda _task_id: {'sources': [{
        'source_id': 'STALE-001', 'title': '启动快照',
    }]})
    citation_state = {'live': True}
    modules = {
        'lazyllm': _stub_module(
            'lazyllm', globals={'agentic_config': {'citation_state': citation_state}},
        ),
        'lazymind': _stub_module('lazymind'),
        'lazymind.chat': _stub_module('lazymind.chat'),
        'lazymind.chat.service': _stub_module('lazymind.chat.service'),
        'lazymind.chat.service.utils': _stub_module('lazymind.chat.service.utils'),
        'lazymind.chat.service.utils.citations': _stub_module(
            'lazymind.chat.service.utils.citations',
            materialize_source_views=lambda state: [{
                'index': 'WEB-009',
                'title': '本轮检索来源',
                'url': 'https://live.example.test/source',
            }] if state is citation_state else [],
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sources = tools._current_attempt_sources()

    assert len(sources) == 1
    assert sources[0]['source_id'] == 'WEB-009'
    assert sources[0]['url'] == 'https://live.example.test/source'
    assert 'https://live.example.test/source' in sources[0]['keys']
    assert all(source['source_id'] != 'STALE-001' for source in sources)


def test_delivery_loader_returns_metadata_without_large_document_bodies(tmp_path):
    tools = _load_contract_tools(tmp_path)
    document = tmp_path / 'product-design.md'
    document.write_text('# 产品方案\n' + '正文' * 10000, encoding='utf-8')
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'remote_inputs': {
            'execution_plan': {'stage_chain': ['design']},
            'design_document': {
                'value': {'path': str(document), 'filename': '方案.md'},
                'seq': 3,
            },
        }},
    )
    tools.require_context = lambda: context

    result = tools.load_product_stage_inputs('delivery')

    descriptor = result['materials']['design_document']
    assert result['materials']['execution_plan'] == {'stage_chain': ['design']}
    assert descriptor['filename'] == '方案.md'
    assert descriptor['seq'] == 3
    assert descriptor['size_bytes'] == document.stat().st_size
    assert '正文' not in json.dumps(result, ensure_ascii=False)


def test_finalizer_builds_and_publishes_private_one_stage_manifest_and_workspace(
    tmp_path, monkeypatch,
):
    tools = _load_contract_tools(tmp_path)
    document = tmp_path / 'product-design.md'
    document.write_text('# 产品方案\n', encoding='utf-8')
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'session_id': 'design-session',
            'remote_inputs': {
                'routing_record': {
                    'selected_stage': 'design',
                    'route_source': 'explicit',
                    'route_reason': '用户选择产品方案',
                    'confidence': 'explicit',
                },
                'execution_plan': {
                    'selected_stage': 'design',
                    'planned_stage_chain': ['design', 'prototype'],
                    'execution_scope': ['design'],
                    'execution_depth': 'full',
                    'product_goal': '设计双层 Router',
                    'reference_sample_status': 'none-confirmed',
                },
                'design_routing_record': {
                    'primary_domains': ['behavior_policy_trust'],
                    'linked_domains': ['journey_interaction_service'],
                    'overall_effort': 'heavy',
                },
                'design_document': str(document),
            },
        },
    )
    tools.require_context = lambda: context

    result = tools.build_product_handoff_state()

    manifest = result['stage_manifest']
    workspace = result['workspace_state']
    assert manifest['visibility'] == 'agent-internal'
    assert manifest['artifact_type'] == 'product-design-spec'
    # A nonempty slot alone cannot establish child quality or supply the required
    # direction input. The result must stay exportable, but be labelled a draft.
    assert manifest['status'] == 'draft'
    assert manifest['dependencies'][0]['status'] == 'missing'
    assert workspace['visibility'] == 'agent-internal'
    assert workspace['current_run']['run_status'] == 'blocked'
    assert workspace['current_run']['stage_chain'] == ['design', 'prototype']
    assert workspace['current_run']['selected_stage'] == 'design'
    assert 'workspace_state' not in result['delivery_summary']

    saved = {}

    def capture_artifact(**kwargs):
        saved[kwargs['key']] = kwargs

    monkeypatch.setattr(tools, '_save_artifact', capture_artifact)
    assert tools.publish_product_handoff_state() == result['delivery_summary']
    assert set(saved) == {'stage_manifest', 'workspace_state', 'delivery_summary'}
    assert saved['stage_manifest']['content_type'] == 'json'
    assert saved['workspace_state']['content_type'] == 'json'
    assert saved['delivery_summary']['content_type'] == 'text'
    assert all(item['source_tool'] == 'publish_product_handoff_state' for item in saved.values())
    assert all(item['internal_publish'] is True for item in saved.values())


def test_direction_handoff_recommends_competitive_after_human_confirmation(tmp_path):
    tools = _load_contract_tools(tmp_path)
    markdown = tmp_path / 'product-direction.md'
    html = tmp_path / 'product-direction.html'
    markdown.write_text('# 产品方向\n', encoding='utf-8')
    html.write_text('<!doctype html><html><body><h1>产品方向</h1></body></html>', encoding='utf-8')
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'session_id': 'direction-session',
            'remote_inputs': {
                'routing_record': {
                    'selected_stage': 'direction',
                    'route_source': 'deterministic',
                    'route_reason': '首次进入项目，先明确产品方向。',
                    'confidence': 'high',
                },
                'execution_plan': {
                    'selected_stage': 'direction',
                    'planned_stage_chain': ['direction'],
                    'execution_scope': ['direction'],
                    'execution_depth': 'auto',
                    'product_goal': '建立门店巡检整改协同工具',
                },
                'direction_document': str(markdown),
                'direction_document_html': str(html),
            },
        },
    )

    result = tools.build_product_handoff_state()

    assert result['workspace_state']['current_run']['selected_stage'] == 'direction'
    assert result['workspace_state']['current_run']['recommended_next_stage'] == 'competitive'
    assert '建议下一步：竞品与生态位' in result['delivery_summary']
    assert result['workspace_state']['current_run']['run_status'] == 'awaiting-stage-confirmation'


def test_competitive_validation_accepts_semantic_variants_without_fake_links(tmp_path):
    tools = _load_contract_tools(tmp_path)
    html = '''<!doctype html><html><head><title>竞品分析</title>
    <meta name="viewport" content="width=device-width"></head><body>
    <h1>竞品分析</h1><h2>能力对比矩阵</h2><table><tr><td>未知</td></tr></table>
    <h2>生态地图与差异化定位</h2><svg></svg><h2>设计启示</h2>
    <details><summary>证据限制</summary>当前无检索来源。</details></body></html>'''

    assert tools._validate_competitive_report(html) == []


def test_product_file_writer_returns_exact_saveable_path(tmp_path):
    tools = _load_contract_tools(tmp_path)

    path = tools.write_product_artifact_file(
        'prototype.html',
        '<!doctype html><title>原型</title><meta name="viewport" content="width=device-width">'
        '<h1>原型</h1><button>继续</button>',
        'prototype',
    )

    assert isinstance(path, str)
    assert Path(path).is_file()


@pytest.mark.parametrize(
    ('stage_id', 'skill_name'),
    [
        ('direction', 'shape-product-direction'),
        ('competitive', 'analyze-competitors'),
        ('design', 'product-design-full-cycle'),
        ('prd', 'write-prd'),
        ('prototype', 'build-product-prototype'),
        ('review', 'review-product-artifact'),
        ('handoff', 'prepare-development-handoff'),
    ],
)
def test_all_source_stage_contracts_are_embedded(tmp_path, stage_id, skill_name):
    tools = _load_contract_tools(tmp_path)

    contract = tools.load_product_skill_contract(stage_id)

    assert contract['stage_id'] == stage_id
    assert contract['skill_name'] == skill_name
    assert contract['contract_sha256']
    assert f'children/{skill_name}/SKILL.md' in contract['contract_text']


def test_execution_plan_authorizes_only_selected_stage(tmp_path):
    tools = _load_contract_tools(tmp_path)

    result = tools.validate_product_execution_plan({
        'selected_stage': 'competitive',
        'stage_chain': ['competitive', 'design', 'prd'],
        'stage_chain_authorized': True,
    })

    assert result['valid'] is True
    assert result['execution_plan']['execution_mode'] == 'single-stage'
    assert result['execution_plan']['selected_stage'] == 'competitive'
    assert result['execution_plan']['execution_scope'] == ['competitive']
    assert result['execution_plan']['planned_stage_chain'] == [
        'competitive', 'design', 'prd',
    ]


def test_execution_plan_rejects_unauthorized_reverse_or_duplicate_chains(tmp_path):
    tools = _load_contract_tools(tmp_path)

    unauthorized = tools.validate_product_execution_plan({
        'selected_stage': 'design', 'stage_chain': ['design', 'prd'],
    })
    reverse = tools.validate_product_execution_plan({
        'selected_stage': 'prd', 'stage_chain': ['prd', 'design'],
        'stage_chain_authorized': True,
    })
    duplicate = tools.validate_product_execution_plan({
        'selected_stage': 'design', 'stage_chain': ['design', 'design'],
        'stage_chain_authorized': True,
    })

    assert unauthorized['valid'] is False
    assert any('explicit' in error for error in unauthorized['errors'])
    assert reverse['valid'] is False
    assert any('canonical forward' in error for error in reverse['errors'])
    assert duplicate['valid'] is False
    assert any('duplicate' in error for error in duplicate['errors'])


def test_parent_router_validates_contract_and_one_stage_scope(tmp_path):
    tools = _load_contract_tools(tmp_path)

    result = tools.validate_product_route(
        {
            'selected_stage': 'competitive',
            'route_source': 'explicit',
            'route_reason': '用户明确要求先分析竞品，再给产品方案。',
            'confidence': 'explicit',
            'alternatives': [],
            'stage_chain': ['competitive', 'design'],
            'stage_chain_authorized': True,
        },
        '为研发团队设计需求评审助手',
        '完整执行',
        'not-applicable',
        'not-required',
        '竞品与生态位',
    )

    assert result['routing_record']['selected_stage'] == 'competitive'
    assert result['execution_plan']['execution_scope'] == ['competitive']
    assert result['execution_plan']['planned_stage_chain'] == ['competitive', 'design']
    assert result['execution_plan']['reference_sample_status'] == 'not-required'
    assert 'hide_competitive' not in result
    assert set(result['ui_hide_flags']) == {
        'hide_direction', 'hide_design', 'hide_prd', 'hide_prototype',
        'hide_review', 'hide_handoff',
    }


def test_parent_router_defaults_clean_post_clarification_project_to_direction(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '为连锁门店建立巡检整改协同工具，服务店长和督导。',
            'remote_inputs': {'product_goal': '减少纸表记录和群聊追踪。'},
        },
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'competitive',
            'route_source': 'model',
            'route_reason': '模型建议先研究市场参与者。',
            'confidence': 'low',
            'alternatives': ['design'],
            'stage_chain': ['competitive', 'design'],
            'stage_chain_authorized': True,
        },
        '为连锁门店建立巡检整改协同工具，服务店长和督导。',
        requested_stage='由 Router 判断',
    )

    record = result['routing_record']
    assert record['selected_stage'] == 'direction'
    assert record['route_source'] == 'deterministic'
    assert record['confidence'] == 'high'
    assert record['alternatives'] == []
    assert record['stage_chain'] == []
    assert result['execution_plan']['execution_scope'] == ['direction']
    assert '先从产品方向开始' in result['routing_summary']
    assert '确认继续后，再进入竞品与生态位' in result['routing_summary']


def test_parent_router_keeps_material_based_entry_instead_of_forcing_direction(tmp_path):
    tools = _load_contract_tools(tmp_path)
    material = tmp_path / 'existing-notes.md'
    material.write_text('# 既有项目材料\n', encoding='utf-8')
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '基于已有内容继续工作。',
            'remote_inputs': {'product_materials': {'path': str(material)}},
        },
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'design',
            'route_source': 'deterministic',
            'route_reason': '已有材料足以继续细化产品机制。',
            'confidence': 'high',
            'alternatives': ['review'],
        },
        '基于已有内容继续工作。',
        requested_stage='由 Router 判断',
    )

    assert result['routing_record']['selected_stage'] == 'design'
    assert result['routing_record']['route_source'] == 'deterministic'
    assert '根据你描述的目标' in result['routing_summary']


def test_parent_router_restores_conflicting_explicit_stage(tmp_path):
    tools = _load_contract_tools(tmp_path)

    result = tools.validate_product_route(
        {
            'selected_stage': 'prd',
            'route_source': 'model_recommendation',
            'route_reason': '错误改选',
            'confidence': 'high',
            'alternatives': ['direction', 'prototype', 'review'],
            'stage_chain': ['direction', 'design'],
            'stage_chain_authorized': True,
        },
        '写产品方案', 'light', '800', 'none-confirmed', '产品方案',
    )

    assert result['routing_record']['selected_stage'] == 'design'
    assert result['routing_record']['route_source'] == 'explicit'
    assert result['routing_record']['confidence'] == 'explicit'
    assert result['routing_record']['alternatives'] == []
    assert result['routing_record']['stage_chain'] == []
    assert '## 产品方案' in result['routing_summary']
    assert '已根据你的要求，从这里开始' in result['routing_summary']
    assert '功能如何运作、关键流程、界面与文案' in result['routing_summary']
    assert '路由来源' not in result['routing_summary']
    assert '置信度' not in result['routing_summary']
    assert '`design`' not in result['routing_summary']


def test_parent_router_recovers_explicit_stage_from_original_runtime_request(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '直接从「产品方案」阶段开始，一级 Router 必须进入产品方案。',
            'remote_inputs': {},
        },
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'direction',
            'route_source': 'high-confidence deterministic rule',
            'route_reason': '从问题陈述开始。',
            'confidence': 'high',
            'alternatives': ['competitive', 'design', 'prd'],
        },
        '面向企业的会议决策助手',
        requested_stage='由 Router 判断',
    )

    assert result['routing_record']['selected_stage'] == 'design'
    assert result['routing_record']['route_source'] == 'explicit'
    assert result['routing_record']['alternatives'] == []
    assert '已根据你的要求，从这里开始' in result['routing_summary']


@pytest.mark.parametrize('separator', ['\n', '\n\n'])
@pytest.mark.parametrize('envelope', ['', 'Original workflow request:\n'])
def test_parent_router_ignores_selected_workflow_launcher_copy(tmp_path, separator, envelope):
    tools = _load_contract_tools(tmp_path)
    request = (
        envelope
        +
        '请使用「产品方案交付」的完整能力，根据我接下来提供的需求完成任务。'
        '可综合使用的功能包括：方向梳理、竞品与生态位、产品方案、需求文档、'
        f'交互原型、方案评审、研发交付。{separator}'
        '我要做一个面向连锁品牌的门店巡检与整改协同产品，目标用户是店长、督导和'
        '区域运营，希望减少纸表巡检与微信群追踪。请输出竞品与生态位、产品方案、'
        'PRD 和核心流程交互原型。'
        + ('\n\nClarification answers:\n原型完成度：可点击演示页面' if envelope else '')
    )
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'user_input': request, 'remote_inputs': {}},
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'competitive',
            'route_source': 'explicit',
            'route_reason': '用户要求依次输出竞品与生态位、产品方案、PRD 和交互原型。',
            'confidence': 'explicit',
            'alternatives': [],
            'stage_chain': ['competitive', 'design', 'prd', 'prototype'],
            'stage_chain_authorized': True,
        },
        request,
        requested_stage='由 Router 判断',
    )

    assert result['routing_record']['selected_stage'] == 'competitive'
    assert result['execution_plan']['planned_stage_chain'] == [
        'competitive', 'design', 'prd', 'prototype',
    ]


def test_direct_current_request_overrides_a_conflicting_prefilled_stage(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '直接从「产品方案」阶段开始，不要求我补充材料。',
            'remote_inputs': {},
        },
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'direction',
            'route_source': 'explicit',
            'route_reason': '沿用预填阶段。',
            'confidence': 'explicit',
            'alternatives': [],
        },
        '企业会议决策助手',
        requested_stage='产品方向',
    )

    assert result['routing_record']['selected_stage'] == 'design'
    assert result['routing_record']['route_source'] == 'explicit'
    assert '## 产品方案' in result['routing_summary']


def test_parent_router_keeps_full_material_digest_but_shows_a_plain_language_card(tmp_path):
    tools = _load_contract_tools(tmp_path)
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text(json.dumps([
        {'summary': '该评审报告包含 DES-002、PRT-001 与 proposed 决定。'},
        {'summary': '该材料是一份概念级交互原型及其规格说明。'},
    ], ensure_ascii=False), encoding='utf-8')

    evidence, digest, research_log = tools._router_profile_summary(str(profiles))

    assert '## 已收到的内容' in evidence
    assert '- 你的产品目标' in evidence
    assert '- 方案评审' in evidence
    assert '- 交互原型' in evidence
    assert 'DES-002' not in evidence
    assert 'proposed' not in evidence
    assert 'DES-002' in digest
    assert '父 Router 未执行外部检索' in research_log


def test_parent_router_shows_a_clear_starting_point_when_no_extra_materials_exist(tmp_path):
    tools = _load_contract_tools(tmp_path)
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text('[]', encoding='utf-8')

    evidence, digest, research_log = tools._router_profile_summary(str(profiles))

    assert '- 你的产品目标' in evidence
    assert '暂未附加其他资料，可以先继续' in evidence
    assert '需要补充或验证的内容会在方案中标出' in evidence
    assert '父 Router' not in evidence
    assert '本次没有绑定可读取的产品材料' in digest
    assert '父 Router 未执行外部检索' in research_log


def test_parent_router_tab_only_exposes_the_two_user_facing_start_cards():
    root = Path(__file__).resolve().parents[4]
    workflow = yaml.safe_load(
        (root / 'workflows' / 'product_solution_delivery' / 'workflow.yaml').read_text(
            encoding='utf-8',
        )
    )
    slots = {slot['id']: slot for slot in workflow['slots']}
    routing_tab = next(tab for tab in workflow['ui']['tabs'] if tab['id'] == 'routing')

    assert routing_tab['label'] == '开始'
    assert routing_tab['slots'] == [{'id': 'routing_summary'}, {'id': 'research_evidence'}]
    assert slots['routing_summary']['label'] == '本次计划'
    assert slots['research_evidence']['label'] == '本次依据'
    assert slots['material_digest']['exposed'] is False
    assert slots['research_log']['exposed'] is False
    assert routing_tab['composite_layout']['children'] == [
        {'slot': 'routing_summary', 'weight': 2},
        {'slot': 'research_evidence', 'weight': 1},
    ]


def test_parent_router_restores_explicit_stage_before_rejecting_model_alias(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '直接从「产品方案」阶段开始。',
            'remote_inputs': {},
        },
    )

    result = tools.validate_product_route(
        {
            'selected_stage': 'product_scheme',
            'route_source': 'router',
            'route_reason': '模型使用了非规范别名。',
            'confidence': 'explicit',
            'alternatives': [],
        },
        '企业会议决策助手',
    )

    assert result['routing_record']['selected_stage'] == 'design'
    assert result['routing_record']['route_source'] == 'explicit'


def test_parent_router_terminal_publisher_saves_one_normalized_unit(tmp_path):
    tools = _load_contract_tools(tmp_path)
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '直接从产品方案阶段开始。',
            'remote_inputs': {},
        },
    )

    result = tools.publish_product_route(
        {
            'selected_stage': 'direction',
            'route_source': 'model_recommendation',
            'route_reason': '模型推断。',
            'confidence': 'high',
            'alternatives': ['competitive', 'design', 'prd'],
        },
        '企业会议决策助手',
        str(profiles),
        requested_stage='由 Router 判断',
    )

    assert result['status'] == 'published'
    assert result['selected_stage'] == 'design'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    assert set(result['saved_slots']) == set(saved)
    assert saved['routing_record']['value']['selected_stage'] == 'design'
    assert saved['routing_record']['value']['route_source'] == 'explicit'
    assert saved['resource_profiles']['content_type'] == 'file'
    assert 'hide_design' not in saved


def test_parent_router_accepts_nested_routing_record_wrapper(tmp_path):
    tools = _load_contract_tools(tmp_path)
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    request = (
        'Original workflow request:\n'
        '请使用「产品方案交付」的完整能力，根据我接下来提供的需求完成任务。'
        '可综合使用的功能包括：方向梳理、竞品与生态位、产品方案、需求文档、'
        '交互原型、方案评审、研发交付。\n\n'
        '请输出竞品与生态位、产品方案、PRD 和核心流程交互原型。'
    )
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={'user_input': request, 'remote_inputs': {}},
    )

    result = tools.publish_product_route(
        {'routing_record': {
            'selected_stage': 'competitive',
            'route_source': 'explicit',
            'route_reason': '用户要求按顺序交付四个阶段。',
            'confidence': 'explicit',
            'alternatives': [],
            'stage_chain': ['competitive', 'design', 'prd', 'prototype'],
            'stage_chain_authorized': True,
        }},
        request,
        str(profiles),
    )

    assert result['selected_stage'] == 'competitive'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    assert saved['execution_plan']['value']['planned_stage_chain'] == [
        'competitive', 'design', 'prd', 'prototype',
    ]


def test_parent_router_ignores_model_placeholders_for_unbound_optional_scalars(tmp_path):
    tools = _load_contract_tools(tmp_path)
    profiles = tmp_path / 'resource_profiles.json'
    profiles.write_text('[]', encoding='utf-8')
    tools.require_context = lambda: types.SimpleNamespace(
        workspace_path=str(tmp_path),
        params={
            'user_input': '直接从产品方案阶段开始。',
            'remote_inputs': {'product_goal': '企业会议决策助手'},
        },
    )

    result = tools.publish_product_route(
        {
            'selected_stage': '产品方案',
            'route_source': 'explicit',
            'route_reason': '用户明确选择产品方案。',
            'confidence': 'explicit',
            'alternatives': [],
        },
        '企业会议决策助手',
        str(profiles),
        execution_depth='auto',
        word_target='stage-specific',
        reference_sample_choice='default',
        requested_stage='由 Router 判断',
    )

    assert result['status'] == 'published'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    plan = saved['execution_plan']['value']
    assert plan['selected_stage'] == 'design'
    assert plan['word_target'] == 3500
    assert plan['reference_sample_status'] == 'none-confirmed'
    assert plan['preference_sources']['word_target'] == 'project-default'


def test_parent_router_replaces_embedded_profile_path_when_no_files_are_bound(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {
        'product_goal': {'data': '企业会议决策助手'},
    }}

    result = tools.publish_product_route(
        {
            'selected_stage': 'design',
            'route_source': 'explicit',
            'route_reason': '用户明确选择产品方案。',
            'confidence': 'explicit',
            'alternatives': [],
        },
        product_goal='模型重复的目标',
        resource_profiles_path='embedded://product-solution-delivery/assets/artifact-template.json',
        requested_stage='design',
    )

    assert result['status'] == 'published'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    path = Path(saved['resource_profiles']['value'])
    assert path.parent == tmp_path
    assert json.loads(path.read_text(encoding='utf-8')) == []
    assert saved['execution_plan']['value']['product_goal'] == '企业会议决策助手'


def test_parent_router_does_not_skip_profiling_when_a_file_slot_is_bound(tmp_path):
    tools = _load_contract_tools(tmp_path)
    material = tmp_path / 'brief.md'
    material.write_text('# brief\n', encoding='utf-8')
    tools.require_context().params = {'remote_inputs': {
        'product_goal': '企业会议决策助手',
        'product_materials': {'path': str(material)},
    }}

    with pytest.raises(ValueError, match='profile_product_materials must run'):
        tools.publish_product_route(
            {
                'selected_stage': 'design',
                'route_source': 'explicit',
                'route_reason': '用户明确选择产品方案。',
                'confidence': 'explicit',
                'alternatives': [],
            },
            resource_profiles_path='',
            requested_stage='design',
        )


def test_parent_router_recovers_real_profile_after_model_rewrites_its_path(tmp_path):
    tools = _load_contract_tools(tmp_path)
    material = tmp_path / 'brief.md'
    material.write_text('# brief\n', encoding='utf-8')
    profile_dir = tmp_path / 'product-writer' / 'resource-profiles-valid'
    profile_dir.mkdir(parents=True)
    profile = profile_dir / 'resource_profiles.json'
    profile.write_text(json.dumps([{'name': 'brief.md', 'summary': '明确目标用户'}]), encoding='utf-8')
    tools.require_context().params = {'remote_inputs': {
        'product_goal': '企业会议决策助手',
        'product_materials': {'path': str(material)},
    }}

    result = tools.publish_product_route({
        'selected_stage': 'design', 'route_source': 'explicit',
        'route_reason': '用户明确选择产品方案。', 'confidence': 'explicit', 'alternatives': [],
    }, resource_profiles_path=str(tmp_path / 'invented' / 'resource_profiles.json'),
        requested_stage='design')

    assert result['status'] == 'published'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    assert saved['resource_profiles']['value'] == str(profile)


def test_design_router_forces_hard_gate_decision_to_heavy(tmp_path):
    tools = _load_contract_tools(tmp_path)

    with pytest.raises(ValueError, match='must be heavy'):
        tools.validate_design_route({
            'primary_domains': ['behavior_policy_trust'],
            'linked_domains': ['content_communication'],
            'overall_effort': 'light',
            'decisions': [{
                'decision_id': 'DES-001',
                'decision_question': '是否允许自动写入？',
                'primary_domain': 'behavior_policy_trust',
                'linked_domains': ['content_communication'],
                'effort': 'light',
                'effort_reasons': ['看似局部'],
                'hard_gates': ['silent_write'],
            }],
            'escalation_triggers': [
                'sustained_counterexamples', 'practice_divergence', 'trust_risk',
            ],
        })


def test_design_router_keeps_scope_and_effort_as_two_axes(tmp_path):
    tools = _load_contract_tools(tmp_path)

    result = tools.validate_design_route({
        'primary_domains': ['domain_state', 'behavior_policy_trust'],
        'linked_domains': ['journey_interaction_service'],
        'overall_effort': 'heavy',
        'decisions': [
            {
                'decision_id': 'DES-001',
                'decision_question': '技能对象状态如何流转？',
                'primary_domain': 'domain_state',
                'linked_domains': ['behavior_policy_trust'],
                'effort': 'light',
                'effort_reasons': ['低成本且可逆'],
                'hard_gates': [],
            },
            {
                'decision_id': 'DES-002',
                'decision_question': '谁可触发自动写入？',
                'primary_domain': 'behavior_policy_trust',
                'linked_domains': ['journey_interaction_service'],
                'effort': 'heavy',
                'effort_reasons': ['权限与信任风险'],
                'hard_gates': ['permission', 'silent_write'],
            },
        ],
        'escalation_triggers': [
            'sustained_counterexamples', 'practice_divergence', 'trust_risk',
        ],
    })

    assert result['design_effort_route'] == 'heavy'
    assert result['design_routing_record']['primary_domains'] == [
        'domain_state', 'behavior_policy_trust',
    ]
    assert '产品机制' not in result['design_routing_record']['primary_domains']
    assert '- 分析方式：需要深入核验' in result['design_routing_summary']
    assert '权限、静默写入' in result['design_routing_summary']
    assert 'Handoff:' not in result['design_routing_summary']


def test_design_router_terminal_publisher_saves_only_deterministic_outputs(tmp_path):
    tools = _load_contract_tools(tmp_path)

    result = tools.publish_design_route({
        'primary_domains': ['ui_visual_system'],
        'linked_domains': ['content_communication'],
        'overall_effort': 'light',
        'decisions': [{
            'decision_id': 'DES-UI-001',
            'decision_question': '如何调整信息层级？',
            'primary_domain': 'ui_visual_system',
            'linked_domains': ['content_communication'],
            'effort': 'light',
            'effort_reasons': ['局部、可逆且没有风险门槛'],
            'hard_gates': [],
        }],
        'escalation_triggers': [
            'sustained_counterexamples', 'practice_divergence', 'trust_risk',
        ],
    })

    assert result['status'] == 'published'
    assert result['overall_effort'] == 'light'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    assert set(saved) == {
        'design_routing_record', 'design_effort_route', 'design_routing_summary',
    }
    assert saved['design_effort_route']['value'] == 'light'
    assert '- 分析方式：可直接整理' in saved['design_routing_summary']['value']
    assert '请确认这些重点是否合适' in saved['design_routing_summary']['value']
    assert all(item['source_tool'] == 'publish_design_route' for item in saved.values())
    assert all(item['internal_publish'] is True for item in saved.values())


def test_design_router_compact_publisher_restores_goal_hard_gates(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {'execution_plan': {'data': {
        'product_goal': '会议助手涉及企业身份、跨部门权限、敏感内容和跨租户数据隔离。',
    }}}}

    result = tools.publish_design_route_compact(
        primary_domains='journey_interaction_service',
        linked_domains='content_communication',
        decision_summary='明确会议决策同步的权限边界，整体选择 Heavy 路由',
    )

    assert result['status'] == 'published'
    assert result['overall_effort'] == 'heavy'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    record = saved['design_routing_record']['value']
    assert record['primary_domains'][0] == 'behavior_policy_trust'
    trust = next(item for item in record['decisions']
                 if item['primary_domain'] == 'behavior_policy_trust')
    assert trust['effort'] == 'heavy'
    assert set(trust['hard_gates']) == {'privacy', 'identity', 'permission', 'cross_tenant'}
    light = next(item for item in record['decisions']
                 if item['primary_domain'] == 'journey_interaction_service')
    assert 'Heavy' not in light['effort_reasons'][0]
    assert light['decision_question'].endswith('应如何满足当前产品目标并保持可验证？')
    assert saved['design_effort_route']['value'] == 'heavy'
    assert all(item['source_tool'] == 'publish_design_route_compact'
               for item in saved.values())


def test_design_router_uses_latest_stage_request_for_new_hard_gate(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {
        'execution_plan': {'data': {'product_goal': '优化会议助手的使用体验。'}},
        'stage_approval': {'data': {
            'selected_stage': 'design',
            'request_context': '本阶段新增跨租户共享会议记录，须明确租户隔离。',
        }},
    }}

    result = tools.publish_design_route_compact(
        primary_domains='journey_interaction_service',
        decision_summary='设计会议记录共享流程',
    )

    assert result['overall_effort'] == 'heavy'
    record = next(item['value'] for item in tools._test_saved_artifacts
                  if item['key'] == 'design_routing_record')
    trust = next(item for item in record['decisions']
                 if item['primary_domain'] == 'behavior_policy_trust')
    assert 'cross_tenant' in trust['hard_gates']


def test_design_router_does_not_silently_drop_declared_paraphrased_risk(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {'execution_plan': {'data': {
        'product_goal': '优化会议助手的使用体验。',
    }}}}

    result = tools.publish_design_route_compact(
        primary_domains='journey_interaction_service',
        hard_gates='permission',
        decision_summary='不同成员应看到不同的会议操作入口',
    )

    assert result['overall_effort'] == 'heavy'
    record = next(item['value'] for item in tools._test_saved_artifacts
                  if item['key'] == 'design_routing_record')
    trust = next(item for item in record['decisions']
                 if item['primary_domain'] == 'behavior_policy_trust')
    assert trust['hard_gates'] == ['permission']


def test_design_router_compact_publisher_defaults_to_light_for_local_ui_change(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {'execution_plan': {'data': {
        'product_goal': '调整设置页按钮层级和空状态文案。',
    }}}}

    result = tools.publish_design_route_compact(
        primary_domains='ui_visual_system',
        linked_domains='content_communication',
        decision_summary='改善设置页的信息层级',
    )

    assert result['overall_effort'] == 'light'
    saved = {item['key']: item for item in tools._test_saved_artifacts}
    assert saved['design_routing_record']['value']['primary_domains'] == ['ui_visual_system']


def test_design_router_compact_publisher_filters_copied_domains_and_gates(tmp_path):
    tools = _load_contract_tools(tmp_path)
    tools.require_context().params = {'remote_inputs': {'execution_plan': {'data': {
        'product_goal': (
            '会议决策助手读取会议内容与对象数据并同步项目系统；涉及企业身份、权限、'
            '敏感内容和跨租户隔离。'
        ),
    }}}}

    tools.publish_design_route_compact(
        primary_domains=','.join(tools.DESIGN_DOMAINS),
        heavy_domains=','.join(tools.DESIGN_DOMAINS),
        hard_gates=','.join(sorted(tools.DESIGN_HARD_GATES)),
        decision_summary='围绕身份、权限、隐私与跨租户隔离采用重型取证',
    )

    saved = {item['key']: item for item in tools._test_saved_artifacts}
    record = saved['design_routing_record']['value']
    assert record['primary_domains'] == [
        'domain_state', 'behavior_policy_trust', 'journey_interaction_service',
    ]
    assert record['linked_domains'] == ['content_communication']
    gates = {gate for item in record['decisions'] for gate in item['hard_gates']}
    assert gates == {'privacy', 'identity', 'permission', 'cross_tenant'}
    assert 'silent_write' not in gates
    assert 'high_loss_irreversible' not in gates


def test_legacy_preflight_adapter_rejects_multi_stage_execution(tmp_path):
    tools = _load_contract_tools(tmp_path)

    with pytest.raises(ValueError, match='exactly one stage'):
        tools.normalize_product_parameters(
            '先竞品再方案', '竞品与生态位 → 产品方案', 'full',
            'not-applicable', 'not-required',
        )


@pytest.mark.parametrize('stage_id', ['direction', 'design', 'prd', 'review', 'handoff'])
def test_writer_steps_fail_fast_without_terminal_success_semantics(stage_id):
    root = Path(__file__).resolve().parents[4]
    state = (root / 'workflows' / 'product_solution_delivery' / 'scenario' / 'state.yml').read_text(
        encoding='utf-8',
    )

    for kind, tool in (
        ('build', 'product_writer_generate_outline_from_inputs'),
        ('write', 'product_writer_generate_document_from_inputs'),
    ):
        suffix = 'outline' if kind == 'build' else 'document'
        step_id = f'{kind}_{stage_id}_{suffix}'
        match = re.search(
            rf'^  {re.escape(step_id)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_]*:\n|\Z)',
            state,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert match, step_id
        body = match.group('body')
        fail_fast = next(
            line for line in body.splitlines()
            if line.lstrip().startswith('fail_fast_tools:')
        )
        assert tool in fail_fast
        assert 'product_writer_revise_markdown' in fail_fast
        assert 'terminal_tools:' not in body
