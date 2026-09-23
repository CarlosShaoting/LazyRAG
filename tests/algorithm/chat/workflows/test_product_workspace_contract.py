"""Regressions for real Skill/workflow boundary failures, using host-shaped inputs."""
import copy
import hashlib
import html
import json
import types

import pytest

from test_product_solution_delivery import _load_contract_tools


def _context(tools, tmp_path, stage, **inputs):
    remote = {
        'execution_plan': {
            'selected_stage': stage, 'execution_scope': [stage],
            'planned_stage_chain': [stage], 'product_goal': '研发团队的需求评审助手',
            'reference_sample_status': 'none-confirmed', 'execution_depth': 'auto',
        },
        **inputs,
    }
    context = types.SimpleNamespace(
        workspace_path=str(tmp_path), params={'session_id': 'session-1', 'remote_inputs': remote},
    )
    tools.require_context = lambda: context
    return context


def _assessment(stage, **values):
    return {'stage': stage, 'status': 'reviewable', 'execution_depth': 'light', **values}


def _html_view(markdown):
    """Represent the same test content in the required paired HTML view."""
    return f'<!doctype html><html><body><main>{html.escape(markdown)}</main></body></html>'


def _artifact(kind, content, *, artifact_id='A-1', version='1.0', status='accepted'):
    return {
        'artifact_id': artifact_id, 'artifact_type': kind, 'version': version,
        'status': status, 'dependencies': [], 'open_questions': [],
        'host_artifact': {'content_sha256': hashlib.sha256(content.encode()).hexdigest()},
    }


def _seed(*artifacts):
    return {
        'schema_version': '1.1', 'visibility': 'agent-internal', 'workspace_id': 'W-1',
        'workspace_mode': 'saved', 'artifacts': list(artifacts), 'decisions': [], 'approvals': [],
    }


@pytest.mark.parametrize('value', [None, '', {}, {'revision_id': 'R-1'}, {'data': ''}, []])
def test_empty_transport_metadata_is_not_a_document(tmp_path, value):
    tools = _load_contract_tools(tmp_path)
    assert tools._bound_artifact_descriptor(value)['present'] is False


def test_missing_or_empty_file_cannot_be_reported_as_reviewable(tmp_path):
    tools = _load_contract_tools(tmp_path)
    empty = tmp_path / 'empty.html'
    empty.write_text('  \n', encoding='utf-8')
    for path in (empty, tmp_path / 'does-not-exist.html'):
        _context(tools, tmp_path, 'prototype', prototype={'path': str(path)},
                 prototype_assessment=_assessment('prototype'))
        result = tools.build_product_handoff_state()
        assert result['stage_manifest']['host_artifact']['present'] is False
        assert result['stage_manifest']['status'] == 'draft'
        assert result['workspace_state']['artifacts'] == []
        assert result['workspace_state']['current_run']['run_status'] == 'blocked'


def test_markdown_without_paired_html_cannot_be_reported_as_reviewable(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'direction', direction_document='# Direction',
             direction_assessment=_assessment('direction'))
    manifest = tools.build_product_handoff_state()['stage_manifest']
    assert manifest['status'] == 'draft'
    assert any('html' in item['question'].lower() for item in manifest['open_questions'])


def test_non_writer_tools_cannot_escape_selected_stage(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'direction')
    with pytest.raises(ValueError, match='selected_stage'):
        tools.load_product_stage_inputs('prototype')
    with pytest.raises(ValueError, match='selected_stage'):
        tools.write_product_artifact('prototype.html', '<h1>Prototype</h1>', 'prototype')
    with pytest.raises(ValueError, match='selected HTML stage'):
        tools.write_product_artifact('prototype.html', '<h1>Prototype</h1>')


def test_child_contract_loading_is_scoped_and_internal(tmp_path):
    tools = _load_contract_tools(tmp_path)
    context = _context(tools, tmp_path, 'design')
    contract = tools.load_product_skill_contract('design')
    assert contract['package_release'] == 'psd-2026-08-11-portable-lazymind-competitive-analysis-v1'
    assert 'BEGIN children/product-design-full-cycle/references/domain-model.md' not in contract['contract_text']
    assert 'runtime_trace' in contract
    assert 'skill_receipt' not in contract
    assert context.params['product_skill_loads']['design']['selected_child_loaded'] is True
    contract = tools.load_product_skill_contract('design', ['references/domain-model.md'])
    assert 'BEGIN children/product-design-full-cycle/references/domain-model.md' in contract['contract_text']
    with pytest.raises(ValueError, match='inside the selected'):
        tools.load_product_skill_contract('design', ['../write-prd/SKILL.md'])


def test_design_contract_ignores_domain_ids_passed_as_reference_paths(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design')
    domain_ids = [
        'behavior_policy_trust', 'domain_state',
        'journey_interaction_service', 'ui_visual_system',
    ]
    contract = tools.load_product_skill_contract('design', [
        *domain_ids,
    ])
    for filename in (
        'product-behavior-decisions.md', 'domain-model.md',
        'journey-interaction.md', 'ui-quick-decisions.md', 'ui-heavy-research.md',
    ):
        marker = f'BEGIN children/product-design-full-cycle/references/{filename}'
        assert marker not in contract['contract_text']
    assert contract['ignored_reference_paths'] == domain_ids
    assert contract['runtime_trace']['ignored_reference_paths'] == domain_ids
    assert 'not exact packaged references/*.md' in contract['warning']


def test_readable_equivalent_input_supports_direct_middle_stage_entry(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design', design_document='# 新方案\n规则和验收',
             design_document_html=_html_view('# 新方案\n规则和验收'),
             product_materials='用户是研发负责人；问题是评审遗漏；边界为需求评审。',
             design_assessment=_assessment('design', dependencies=[{
                 'artifact_type': 'direction-brief', 'source_slot': 'product_materials',
                 'evidence': '用户、问题、产品边界均在上传材料第一段。',
             }]))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['status'] == 'reviewable'
    assert result['stage_manifest']['dependencies'][0]['status'] == 'available'
    assert result['workspace_state']['current_run']['execution_depth'] == 'light'


def test_upstream_digest_survives_inline_text_to_file_transport(tmp_path):
    tools = _load_contract_tools(tmp_path)
    content = '# 已确认方案\n\n对象、状态和验收。\n'
    path = tmp_path / 'upstream.md'
    path.write_text(content, encoding='utf-8')
    artifact = _artifact('product-design-spec', content)
    _context(tools, tmp_path, 'prd', upstream_design=str(path), prd_document='# PRD\n验收',
             workspace_seed=_seed(artifact), prd_assessment=_assessment('prd'))
    result = tools.build_product_handoff_state()
    dependency = result['stage_manifest']['dependencies'][0]
    assert dependency['artifact_id'] == 'A-1'
    assert dependency['version'] == '1.0'
    assert result['workspace_state']['workspace_id'] == 'W-1'
    assert result['workspace_state']['workspace_mode'] == 'saved'


def test_new_workspace_defaults_to_shared_project_and_relay_keeps_its_identity(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(
        tools, tmp_path, 'direction', direction_document='# Direction\n',
        direction_assessment=_assessment('direction'),
    )
    first = tools.build_product_handoff_state()['workspace_state']
    assert first['workspace_mode'] == 'shared-project'
    workspace_id = first['workspace_id']

    context = _context(
        tools, tmp_path, 'prd', workspace_seed=first,
        upstream_direction='# Direction\n', prd_document='# PRD\n',
        prd_assessment=_assessment('prd'),
    )
    context.params['session_id'] = 'relayed-session-2'
    second = tools.build_product_handoff_state()['workspace_state']

    assert second['workspace_id'] == workspace_id
    assert second['workspace_mode'] == 'shared-project'


def test_new_version_keeps_history_and_marks_downstream_outdated(tmp_path):
    tools = _load_contract_tools(tmp_path)
    direction = _artifact('direction-brief', '# Old direction\n', artifact_id='D-1')
    design = _artifact('product-design-spec', '# Design\n', artifact_id='DES-1')
    design['dependencies'] = [{
        'artifact_id': 'D-1', 'version': '1.0', 'kind': 'required', 'status': 'available',
    }]
    prd = _artifact('prd', '# PRD\n', artifact_id='PRD-1')
    prd['dependencies'] = [{
        'artifact_id': 'DES-1', 'version': '1.0', 'kind': 'required', 'status': 'available',
    }]
    seed = _seed(direction, design, prd)
    original = copy.deepcopy(seed)
    context = _context(tools, tmp_path, 'direction', workspace_seed=seed,
                       direction_document='# Revised direction\n',
                       direction_document_html=_html_view('# Revised direction\n'),
                       direction_assessment=_assessment('direction'))
    result = tools.build_product_handoff_state()
    assert seed == original  # No mutation of the immutable input revision.
    manifest = result['stage_manifest']
    assert manifest['version'] == '1.1'
    assert manifest['supersedes'] == 'D-1'
    records = result['workspace_state']['artifacts']
    assert len(records) == 4
    assert records[0]['status'] == 'superseded'
    assert records[1]['status'] == records[2]['status'] == 'needs-update'
    assert records[1]['dependencies'][0]['version'] == '1.0'
    assert records[1]['dependencies'][0]['status'] == 'outdated'
    context.params['remote_inputs']['workspace_seed'] = result['workspace_state']
    retry = tools.build_product_handoff_state()
    assert retry['stage_manifest']['artifact_id'] == manifest['artifact_id']
    assert len(retry['workspace_state']['artifacts']) == 4


def test_unchanged_content_accepts_fresh_assessment_without_minting_content_version(tmp_path):
    tools = _load_contract_tools(tmp_path)
    context = _context(tools, tmp_path, 'direction', direction_document='# Same direction\n',
                       direction_document_html=_html_view('# Same direction\n'),
                       direction_assessment=_assessment('direction', status='draft'))
    first = tools.build_product_handoff_state()
    remote = context.params['remote_inputs']
    remote['workspace_seed'] = first['workspace_state']
    remote['direction_assessment'] = _assessment('direction', checks={
        'business_review': {'status': 'passed', 'evidence': 'Direction section 2 reviewed against requirements.'},
    })
    second = tools.build_product_handoff_state()
    old, current = first['stage_manifest'], second['stage_manifest']
    assert current['artifact_id'] == old['artifact_id']
    assert current['version'] == old['version'] == '1.0'
    assert current['status'] == 'reviewable'
    assert current['assessment_record']['revision'] == 2
    assert current['assessment_record']['content_sha256'] == current['host_artifact']['content_sha256']
    assert current['assessment_history'][0]['status'] == 'draft'
    assert current['checks']['business_review']['evidence_source'] == 'child-assessment'
    assert len(second['workspace_state']['artifacts']) == 1
    remote['workspace_seed'] = second['workspace_state']
    retry = tools.build_product_handoff_state()
    assert retry['stage_manifest'] == current
    assert retry['workspace_state']['artifacts'] == second['workspace_state']['artifacts']


def test_failed_reassessment_revokes_readiness_and_preserves_acceptance_history(tmp_path):
    tools = _load_contract_tools(tmp_path)
    design = '# Accepted design\n'
    checks = {key: {'status': 'passed', 'evidence': 'Gate review: document section ' + key}
              for key in ('rules', 'acceptance', 'traceability', 'risks', 'resources')}
    context = _context(tools, tmp_path, 'handoff', upstream_design=design,
                       workspace_seed=_seed(_artifact('product-design-spec', design)),
                       handoff_document='# Unchanged handoff\n',
                       handoff_document_html=_html_view('# Unchanged handoff\n'),
                       handoff_assessment=_assessment('handoff', implementation_readiness='ready', checks=checks))
    first = tools.build_product_handoff_state()
    initial = first['stage_manifest']
    assert initial['implementation_readiness'] == 'ready'
    # A host-recorded user acceptance is a distinct event, not a child assessment.
    accepted = copy.deepcopy(first['workspace_state'])
    accepted['artifacts'][-1].update(status='accepted', accepted_by='user-1', acceptance_ref='history:accept-1')
    remote = context.params['remote_inputs']
    remote['workspace_seed'] = accepted
    retained = tools.build_product_handoff_state()['stage_manifest']
    assert retained['status'] == 'accepted'
    assert retained['assessment_record']['revision'] == 1
    checks['risks'] = {'status': 'failed', 'evidence': 'A blocking permission risk was found.'}
    second = tools.build_product_handoff_state()
    failed = second['stage_manifest']
    assert failed['artifact_id'] == initial['artifact_id']
    assert failed['version'] == initial['version']
    assert failed['status'] == 'draft'
    assert failed['implementation_readiness'] == 'blocked'
    assert failed['acceptance_recheck_required'] is True
    assert failed['assessment_history'][0]['artifact_status'] == 'accepted'
    assert failed['assessment_history'][0]['acceptance_ref'] == 'history:accept-1'
    assert 'accepted_by' not in failed
    remote['workspace_seed'] = second['workspace_state']
    checks['risks'] = {'status': 'passed', 'evidence': 'User permissions were verified against the same text.'}
    repaired = tools.build_product_handoff_state()['stage_manifest']
    assert repaired['status'] == 'reviewable'  # A passing recheck does not reapply old approval.
    assert repaired['assessment_record']['revision'] == 3
    assert repaired['acceptance_recheck_required'] is True


def test_failed_same_content_assessment_invalidates_consumers_without_new_content(tmp_path):
    tools = _load_contract_tools(tmp_path)
    context = _context(tools, tmp_path, 'direction', direction_document='# Stable direction',
                       direction_document_html=_html_view('# Stable direction'),
                       direction_assessment=_assessment('direction'))
    first = tools.build_product_handoff_state()
    parent = first['stage_manifest']
    design = _artifact('product-design-spec', '# Design', artifact_id='DES-1')
    design['dependencies'] = [{'artifact_id': parent['artifact_id'], 'version': '1.0',
                               'kind': 'required', 'status': 'available'}]
    seed = first['workspace_state']
    seed['artifacts'].append(design)
    remote = context.params['remote_inputs']
    remote['workspace_seed'] = seed
    remote['direction_assessment']['checks'] = {'scope': {'status': 'failed', 'evidence': 'Scope conflict'}}
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['version'] == '1.0'
    assert result['workspace_state']['artifacts'][1]['status'] == 'needs-update'
    assert result['workspace_state']['artifacts'][1]['implementation_readiness'] == 'blocked'
    assert result['workspace_state']['artifacts'][1]['dependencies'][0]['status'] == 'conflict'


def test_assessment_evidence_for_other_bytes_cannot_pass_current_version(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'direction', direction_document='# Current direction',
             direction_assessment=_assessment('direction', checks={
                 'scope': {'status': 'passed', 'evidence': 'Checked previous file.',
                           'artifact_sha256': hashlib.sha256(b'old content').hexdigest()},
             }))
    manifest = tools.build_product_handoff_state()['stage_manifest']
    assert manifest['status'] == 'draft'
    assert manifest['checks']['scope']['status'] == 'not-checked'
    assert manifest['checks']['scope']['binding_status'] == 'mismatch'


@pytest.mark.parametrize('stage', ['competitive', 'prototype'])
def test_html_stage_reentry_reads_its_existing_shared_view(tmp_path, stage):
    tools = _load_contract_tools(tmp_path)
    baseline = '<!doctype html><h1>Previous approved project view</h1>'
    _context(tools, tmp_path, stage, **{'upstream_' + stage: {'data': baseline}})
    loaded = tools.load_product_stage_inputs(stage)
    assert loaded['materials']['upstream_' + stage] == baseline


@pytest.mark.parametrize('stage', ['competitive', 'prototype', 'delivery'])
def test_non_writer_stage_loader_reads_all_shared_project_artifacts(tmp_path, stage):
    tools = _load_contract_tools(tmp_path)
    upstream = {
        slot: {'data': f'{slot} content'}
        for slot in (
            'upstream_direction', 'upstream_competitive', 'upstream_design',
            'upstream_prd', 'upstream_prototype', 'upstream_review', 'upstream_handoff',
        )
    }
    _context(tools, tmp_path, stage, **upstream)

    loaded = tools.load_product_stage_inputs(stage)

    assert {
        slot: loaded['materials'][slot] for slot in upstream
    } == {
        slot: value['data'] for slot, value in upstream.items()
    }


@pytest.mark.parametrize('stage,target', [
    ('direction', 1400), ('competitive', None), ('design', 3500), ('prd', 4500),
    ('prototype', None), ('review', 1800), ('handoff', 3500),
])
def test_stage_entry_uses_recorded_project_defaults_without_additional_setup(tmp_path, stage, target):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, stage)
    result = tools.validate_product_route({
        'selected_stage': stage, 'route_source': 'explicit', 'confidence': 'explicit',
        'route_reason': 'User selected this project view.',
    }, 'Shared project goal', requested_stage=stage)
    plan = result['execution_plan']
    assert plan['execution_depth'] == 'auto'
    assert plan['word_target'] == target
    assert plan['preference_sources']['execution_depth'] == 'project-default'
    assert plan['reference_sample_status'] == ('not-required' if target is None else 'none-confirmed')
    assert plan['preference_sources']['reference_sample'] == ('not-required' if target is None else 'project-default')
    assert plan['execution_scope'] == [stage]


def test_existing_reference_sample_is_automatically_reused_without_claiming_new_confirmation(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design', reference_sample={'data': '# Existing project sample'})
    route = {'selected_stage': 'design', 'route_source': 'explicit', 'confidence': 'explicit',
             'route_reason': 'Continue this view.'}
    plan = tools.validate_product_route(route, 'Project goal')['execution_plan']
    assert plan['reference_sample_status'] == 'provided'
    assert plan['preference_sources']['reference_sample'] == 'bound-reference-sample'
    plan = tools.validate_product_route(route, 'Project goal', 'full', '7200', 'none-confirmed')['execution_plan']
    assert plan['execution_depth'] == 'full'
    assert plan['word_target'] == 7200
    assert plan['reference_sample_status'] == 'none-confirmed'
    assert set(plan['preference_sources'].values()) == {'explicit-input'}


@pytest.mark.parametrize('preferences', [
    {'execution_depth': 'unknown'}, {'word_target': '20'}, {'word_target': 'invalid'},
    {'reference_sample_choice': 'unknown'},
])
def test_project_defaults_do_not_mask_invalid_explicit_preferences(tmp_path, preferences):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'prd')
    with pytest.raises(ValueError):
        tools.validate_product_route({
            'selected_stage': 'prd', 'route_source': 'explicit', 'confidence': 'explicit',
            'route_reason': 'User selection.',
        }, 'Project goal', **preferences)


def test_decision_updates_are_deduplicated_without_overwriting_accepted_baseline(tmp_path):
    tools = _load_contract_tools(tmp_path)
    accepted = {'decision_id': 'D-1', 'value': 'Manual write', 'status': 'accepted',
                'accepted_by': 'user-1', 'acceptance_ref': 'history:1'}
    seed = _seed()
    seed['decisions'] = [accepted, {'decision_id': 'D-2', 'value': 'Old scope', 'status': 'proposed'}]
    context = _context(tools, tmp_path, 'direction', workspace_seed=seed,
                       direction_document='# Direction', direction_assessment=_assessment('direction', decisions=[
                           {'decision_id': 'D-1', 'value': 'Automatic write', 'status': 'proposed'},
                           {'decision_id': 'D-2', 'value': 'New scope', 'status': 'proposed'},
                       ]))
    first = tools.build_product_handoff_state()
    decisions = first['workspace_state']['decisions']
    assert len(decisions) == 2
    assert decisions[0]['value'] == 'Manual write'
    assert decisions[0]['status'] == 'accepted'
    assert decisions[0]['pending_revisions'][0]['value'] == 'Automatic write'
    assert decisions[1]['value'] == 'New scope'
    assert first['workspace_state']['decision_history'][0]['value'] == 'Old scope'
    context.params['remote_inputs']['workspace_seed'] = first['workspace_state']
    retry = tools.build_product_handoff_state()
    assert retry['workspace_state']['decisions'] == decisions
    assert retry['workspace_state']['decision_history'] == first['workspace_state']['decision_history']


def test_accepted_decision_is_reused_and_only_sourced_replacement_changes_baseline(tmp_path):
    tools = _load_contract_tools(tmp_path)
    seed = _seed(_artifact('direction-brief', '# Direction'))
    seed['decisions'] = [{'decision_id': 'D-1', 'value': 'Manual write', 'status': 'accepted',
                          'accepted_by': 'user-1', 'acceptance_ref': 'history:1'}]
    context = _context(tools, tmp_path, 'direction', workspace_seed=seed, direction_document='# Direction',
                       direction_assessment=_assessment('direction', decisions=[
                           {'decision_id': 'D-1', 'value': 'Manual write', 'status': 'proposed'},
                       ]))
    reused = tools.build_product_handoff_state()
    assert reused['stage_manifest']['decisions'][0] == seed['decisions'][0]
    remote = context.params['remote_inputs']
    remote['direction_assessment']['decisions'] = [{
        'decision_id': 'D-1', 'value': 'Automatic reversible write', 'status': 'accepted',
        'accepted_by': 'user-1', 'acceptance_ref': 'history:2',
    }]
    remote['stage_approval'] = {'approval_id': 'AP-2', 'action': 'accept-decision', 'stage': 'direction',
                                'source': 'user-interface', 'reference': 'history:2',
                                'approved_by': 'user-1', 'decision_id': 'D-1'}
    snapshot = json.dumps(tools._decision_content(remote['direction_assessment']['decisions'][0]), separators=(',', ':'))
    remote['stage_approval'].update({
        'workspace_id': 'W-1', 'artifact_id': 'A-1', 'version': '1.0',
        'content_sha256': seed['artifacts'][0]['host_artifact']['content_sha256'],
        'decision_snapshot_json': snapshot, 'decision_hash': 'sha256:' + hashlib.sha256(snapshot.encode()).hexdigest(),
    })
    replaced = tools.build_product_handoff_state()['workspace_state']
    assert len(replaced['decisions']) == 1
    assert replaced['decisions'][0]['value'] == 'Automatic reversible write'
    assert replaced['decisions'][0]['status'] == 'accepted'
    assert replaced['decision_history'][0] == seed['decisions'][0]


def test_unconfirmed_high_risk_decision_never_produces_implementation_ready_handoff(tmp_path):
    tools = _load_contract_tools(tmp_path)
    design = '# Accepted design'
    checks = {key: {'status': 'passed', 'evidence': 'Checked document section ' + key}
              for key in ('rules', 'acceptance', 'traceability', 'risks', 'resources')}
    _context(tools, tmp_path, 'handoff', workspace_seed=_seed(_artifact('product-design-spec', design)),
             upstream_design=design, handoff_document='# Handoff',
             handoff_document_html=_html_view('# Handoff'),
             handoff_assessment=_assessment('handoff', implementation_readiness='ready', checks=checks, decisions=[{
                 'decision_id': 'RISK-1', 'value': 'Silent write into customer account',
                 'status': 'proposed', 'risk': 'high', 'hard_gates': ['silent_write'],
                 'deferred': True, 'deferral_ref': 'event:defer',
             }]))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['status'] == 'draft'
    assert result['stage_manifest']['implementation_readiness'] == 'blocked'
    assert result['stage_manifest']['host_artifact']['present'] is True
    question = next(item for item in result['stage_manifest']['open_questions'] if item.get('decision_id') == 'RISK-1')
    assert question['blocking'] is True
    assert question['confirmation'] == 'hard-stop'
    assert result['workspace_state']['current_run']['run_status'] == 'awaiting-stage-confirmation'


@pytest.mark.parametrize('decision_status', ['accepted', 'proposed'])
def test_reassessment_recomputes_copied_host_hitl_gate_from_current_decisions(tmp_path, decision_status):
    tools = _load_contract_tools(tmp_path)
    seed = _seed()
    decision = {'decision_id': 'D-1', 'value': 'Write only after confirmation',
                'risk': 'high', 'hard_gates': ['permission'], 'status': decision_status}
    if decision_status == 'accepted':
        decision.update(accepted_by='user-1', acceptance_ref='host-event:accepted')
    seed['decisions'] = [decision]
    _context(tools, tmp_path, 'direction', workspace_seed=seed, direction_document='# Direction',
             direction_document_html=_html_view('# Direction'),
             direction_assessment=_assessment('direction', open_questions=[{
                 'question_id': 'HITL-D-1', 'decision_id': 'D-1', 'confirmation': 'hard-stop',
                 'blocking': True, 'question': 'Copied stale host-generated confirmation gate.',
             }]))
    manifest = tools.build_product_handoff_state()['stage_manifest']
    gates = [item for item in manifest['open_questions'] if item.get('question_id') == 'HITL-D-1']
    if decision_status == 'accepted':
        assert gates == []
        assert manifest['status'] == 'reviewable'
    else:
        assert len(gates) == 1
        assert gates[0]['question'] != 'Copied stale host-generated confirmation gate.'
        assert gates[0]['blocking'] is True
        assert manifest['status'] == 'draft'


def test_reassessment_never_discards_independent_business_blockers(tmp_path):
    tools = _load_contract_tools(tmp_path)
    blockers = [
        {'question_id': 'BUSINESS-1', 'decision_id': 'D-1', 'confirmation': 'hard-stop',
         'question': 'Missing business owner approval.', 'blocking': True},
        {'question_id': 'HITL-D-1', 'decision_id': 'D-1', 'confirmation': 'confirmation-required',
         'question': 'Explicit business scope conflict.', 'blocking': True},
        {'question_id': 'HITL-D-2', 'decision_id': 'D-1', 'confirmation': 'hard-stop',
         'question': 'A separately identified unresolved issue.', 'blocking': True},
    ]
    _context(tools, tmp_path, 'direction', direction_document='# Direction',
             direction_document_html=_html_view('# Direction'),
             direction_assessment=_assessment('direction', open_questions=blockers))
    manifest = tools.build_product_handoff_state()['stage_manifest']
    assert manifest['open_questions'] == blockers
    assert manifest['status'] == 'draft'


@pytest.mark.parametrize('bad_field', [None, 'stage', 'workspace_id', 'artifact_id', 'version',
                                       'content_sha256', 'decision_hash', 'decision_snapshot_json'])
def test_fresh_decision_acceptance_requires_exact_hashed_artifact_and_decision_snapshot(tmp_path, bad_field):
    tools = _load_contract_tools(tmp_path)
    content = '# Direction'
    artifact = _artifact('direction-brief', content, status='reviewable')
    decision = {'decision_id': 'D-1', 'value': '仅在确认后写入 <用户账户>', 'status': 'accepted',
                'accepted_by': 'user-1', 'acceptance_ref': 'event:accept'}
    # Match Go's exact UTF-8 snapshot bytes, including its HTML escaping.
    snapshot = json.dumps(
        tools._decision_content(decision), ensure_ascii=False, separators=(',', ':'),
    ).replace('<', '\\u003c').replace('>', '\\u003e')
    event = {
        'approval_id': 'AP-1', 'action': 'accept-decision', 'source': 'user-interface',
        'reference': 'event:accept', 'approved_by': 'user-1', 'decision_id': 'D-1',
        'stage': 'direction', 'workspace_id': 'W-1', 'artifact_id': 'A-1', 'version': '1.0',
        'content_sha256': artifact['host_artifact']['content_sha256'],
        'decision_snapshot_json': snapshot, 'decision_hash': 'sha256:' + hashlib.sha256(snapshot.encode()).hexdigest(),
    }
    if bad_field:
        event[bad_field] = 'other-baseline'
    _context(tools, tmp_path, 'direction', workspace_seed=_seed(artifact), direction_document=content,
             stage_approval=event, direction_assessment=_assessment('direction', decisions=[decision]))
    result = tools.build_product_handoff_state()['stage_manifest']
    assert result['decisions'][0]['status'] == ('proposed' if bad_field else 'accepted')


def test_legacy_unhashed_event_cannot_newly_promote_decision(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'direction', direction_document='# Direction',
             stage_approval={'approval_id': 'AP-1', 'action': 'accept-decision', 'stage': 'direction',
                             'source': 'user-interface', 'reference': 'old-event', 'approved_by': 'user-1',
                             'decision_id': 'D-1'},
             direction_assessment=_assessment('direction', decisions=[{
                 'decision_id': 'D-1', 'value': 'New value', 'status': 'accepted',
                 'accepted_by': 'user-1', 'acceptance_ref': 'old-event',
             }]))
    assert tools.build_product_handoff_state()['stage_manifest']['decisions'][0]['status'] == 'proposed'


def test_design_child_cannot_omit_router_hard_stop_from_its_assessment(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design', direction_document='# Direction', design_document='# Design',
             design_routing_record={'decisions': [{'decision_id': 'RISK-1', 'decision_question': 'Who can write?',
                                                   'hard_gates': ['permission'], 'effort': 'heavy'}]},
             design_assessment=_assessment('design'))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['status'] == 'draft'
    assert result['stage_manifest']['decisions'][0]['decision_id'] == 'RISK-1'
    assert result['workspace_state']['decisions'][0]['status'] == 'proposed'
    assert any(item.get('confirmation') == 'hard-stop' for item in result['stage_manifest']['open_questions'])


def test_new_router_risk_does_not_inherit_acceptance_for_previously_low_risk_decision(tmp_path):
    tools = _load_contract_tools(tmp_path)
    seed = _seed()
    seed['decisions'] = [{'decision_id': 'D-1', 'value': 'Automatic write', 'status': 'accepted',
                          'accepted_by': 'user-1', 'acceptance_ref': 'history:old'}]
    _context(tools, tmp_path, 'design', workspace_seed=seed,
             direction_document='# Direction', design_document='# Design',
             design_routing_record={'decisions': [{'decision_id': 'D-1', 'hard_gates': ['silent_write']}]},
             design_assessment=_assessment('design', decisions=[{'decision_id': 'D-1', 'value': 'Automatic write'}]))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['status'] == 'draft'
    baseline = result['workspace_state']['decisions'][0]
    assert baseline['status'] == 'accepted'
    assert baseline['pending_revisions'][0]['hard_gates'] == ['silent_write']
    assert any(item.get('confirmation') == 'hard-stop' for item in result['stage_manifest']['open_questions'])


def test_repeated_stage_relay_uses_latest_host_revision_binding(tmp_path):
    tools = _load_contract_tools(tmp_path)
    old = _artifact('product-design-spec', '# Old design', artifact_id='DES-1')
    current = _artifact('product-design-spec', '# Current design', artifact_id='DES-2', version='1.1')
    old['host_artifact']['revision_id'] = 'old-revision'
    current['host_artifact']['revision_id'] = 'current-revision'
    seed = _seed(old, current)
    seed['host_artifact_bindings'] = [
        {'slot_id': 'design_document', 'revision_id': 'old-revision', 'revision': 1},
        {'slot_id': 'design_document', 'revision_id': 'current-revision', 'revision': 2},
    ]
    _context(tools, tmp_path, 'prd', workspace_seed=seed, upstream_design='# Current design',
             prd_document='# PRD', prd_assessment=_assessment('prd'))
    dependency = tools.build_product_handoff_state()['stage_manifest']['dependencies'][0]
    assert dependency['artifact_id'] == 'DES-2'
    assert dependency['host_revision']['revision_id'] == 'current-revision'


def test_continue_event_does_not_accept_a_proposed_decision(tmp_path):
    tools = _load_contract_tools(tmp_path)
    approval = {
        'approval_id': 'AP-1', 'action': 'continue', 'stage': 'direction',
        'source': 'user-message', 'reference': 'history:123', 'approved_by': 'user-1',
    }
    decision = {'decision_id': 'DEC-1', 'value': 'Enable automatic write', 'status': 'accepted',
                'accepted_by': 'user-1', 'acceptance_ref': 'history:123'}
    _context(tools, tmp_path, 'direction', stage_approval=approval,
             direction_document='# Direction\n',
             direction_assessment=_assessment('direction', decisions=[decision]))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['decisions'][0]['status'] == 'proposed'
    assert result['workspace_state']['approvals'][0]['reference'] == 'history:123'


def test_stage_assessment_schema_normalizes_common_model_shapes_in_one_call(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'prd')
    schema = tools.ProductNonHandoffAssessment.model_json_schema()
    assert schema['required'] == ['stage']
    assert schema['properties']['checks']['additionalProperties']['$ref'].endswith(
        '/ProductAssessmentCheck'
    )
    assert schema['properties']['implementation_readiness']['enum'] == [
        'not-assessed', 'blocked',
    ]
    model_value = tools.ProductNonHandoffAssessment.model_validate({
        'stage': 'prd',
        'status': 'completed',
        'execution_depth': 'light',
        'decisions': [{'value': '保留人工确认', 'status': 'pending'}],
        'checks': [
            {'name': 'outline', 'status': 'pass', 'evidence': 'PRD 标题结构核验记录。'},
            {'name': 'business_rules', 'status': 'pending'},
        ],
        'implementation_readiness': {'status': 'ready'},
    })

    result = tools.validate_product_stage_assessment(model_value)

    assert result['status'] == 'reviewable'
    assert result['decisions'][0]['decision_id'] == 'PRD-DEC-001'
    assert result['decisions'][0]['status'] == 'proposed'
    assert result['checks']['outline']['status'] == 'passed'
    assert result['checks']['business_rules']['status'] == 'not-checked'
    assert result['implementation_readiness'] == 'not-assessed'


def test_stage_assessment_tolerates_matching_legacy_sibling_stage_but_rejects_mismatch(
    tmp_path,
):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design')
    result = tools.validate_product_stage_assessment(
        {'stage': 'design', 'status': 'draft'}, stage='design',
    )
    assert result['stage'] == 'design'

    with pytest.raises(ValueError, match='must match value.stage'):
        tools.validate_product_stage_assessment(
            {'stage': 'design', 'status': 'draft'}, stage='prd',
        )


def test_stage_assessment_reports_all_remaining_errors_together(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'prd')

    with pytest.raises(ValueError) as failure:
        tools.validate_product_stage_assessment({
            'stage': 'prd',
            'execution_depth': 'auto',
            'decisions': ['not-an-object', {'decision_id': 'D-2', 'status': 'unknown'}],
            'dependencies': ['not-an-object'],
            'checks': {
                'shape': 'not-an-object',
                'content': {'status': {'unexpected': True}},
            },
            'implementation_readiness': {'status': ['not-hashable']},
        })

    message = str(failure.value)
    assert 'repair every listed field in one retry' in message
    assert 'execution_depth' in message
    assert 'decisions[0]' in message
    assert 'decisions[1].status' in message
    assert 'dependencies[0]' in message
    assert 'checks.shape' in message
    assert 'checks.content.status' in message
    assert 'implementation_readiness' in message


def test_high_risk_acceptance_cannot_use_delegated_ai(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'design')
    with pytest.raises(ValueError, match='high-risk'):
        tools.validate_product_stage_assessment(_assessment('design', decisions=[{
            'decision_id': 'DEC-1', 'status': 'accepted', 'accepted_by': 'delegated-ai',
            'acceptance_ref': 'history:123', 'hard_gates': ['permission'],
        }]))


def test_only_handoff_can_claim_readiness_and_requires_evidenced_gates(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'prd')
    with pytest.raises(ValueError, match='only the handoff'):
        tools.validate_product_stage_assessment(_assessment('prd', implementation_readiness='ready'))
    content = '# Accepted design\nRules and acceptance criteria\n'
    context = _context(tools, tmp_path, 'handoff', workspace_seed=_seed(_artifact('product-design-spec', content)),
                       upstream_design=content, handoff_document='# Handoff\n',
                       handoff_document_html=_html_view('# Handoff\n'),
                       handoff_assessment=_assessment('handoff', implementation_readiness='ready'))
    assert tools.build_product_handoff_state()['stage_manifest']['implementation_readiness'] == 'not-assessed'
    context.params['remote_inputs']['handoff_assessment']['checks'] = {
        key: {'status': 'passed', 'evidence': '交付文档验收矩阵第2行及来源规则。'}
        for key in ('rules', 'acceptance', 'traceability', 'risks', 'resources')
    }
    assert tools.build_product_handoff_state()['stage_manifest']['implementation_readiness'] == 'ready'
    context.params['remote_inputs']['workspace_seed']['artifacts'][0]['status'] = 'reviewable'
    result = tools.build_product_handoff_state()['stage_manifest']
    assert result['status'] == 'draft'
    assert result['implementation_readiness'] == 'blocked'


def test_static_html_success_is_not_real_interaction_validation(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(tools, tmp_path, 'prototype',
             design_document='# Design\n',
             prototype='<!doctype html><title>Demo</title><meta name="viewport" content="width=device-width">'
                       '<h1>Demo</h1><button>Continue</button>',
             prototype_assessment=_assessment('prototype', checks={
                 'static': {'status': 'passed', 'evidence': 'HTML validator passed'},
             }))
    result = tools.build_product_handoff_state()
    assert result['stage_manifest']['status'] == 'draft'
    assert any(item['question_id'] == 'interaction_desktop' for item in result['stage_manifest']['open_questions'])


def test_delivery_summary_never_stringifies_internal_question_records(tmp_path):
    tools = _load_contract_tools(tmp_path)
    _context(
        tools, tmp_path, 'direction', direction_document='# Direction\n',
        direction_assessment=_assessment('direction', open_questions=[{
            'question_id': 'Q-1', 'blocking': True, 'confirmation': 'hard-stop',
        }]),
    )

    summary = tools.build_product_handoff_state()['delivery_summary']

    assert '有一项待确认问题尚未补充说明' in summary
    assert 'question_id' not in summary
    assert 'hard-stop' not in summary


def test_design_escalation_keeps_approved_scope_and_upgrades_in_place(tmp_path):
    tools = _load_contract_tools(tmp_path)
    route = {
        'primary_domains': ['behavior_policy_trust'], 'linked_domains': ['content_communication'],
        'overall_effort': 'light', 'escalation_triggers': sorted(tools.DESIGN_ESCALATION_TRIGGERS),
        'decisions': [{'decision_id': 'D-1', 'decision_question': 'Who can write?',
                       'primary_domain': 'behavior_policy_trust', 'linked_domains': ['content_communication'],
                       'effort': 'light', 'effort_reasons': ['Reversible'], 'hard_gates': []}],
    }
    _context(tools, tmp_path, 'design', design_routing_record=route)
    escalation = {'trigger': 'trust_risk', 'reason': 'Discovered silent write', 'evidence': 'Source UI step 3',
                  'decisions': [{'decision_id': 'D-1', 'hard_gates': ['silent_write']}]}
    result = tools.validate_design_escalation(escalation)['design_escalation']
    assert result['effective_route']['overall_effort'] == 'heavy'
    assert result['effective_route']['primary_domains'] == route['primary_domains']
    assert result['risk_confirmation_required'] is True
    escalation['decisions'][0]['primary_domain'] = 'domain_state'
    with pytest.raises(ValueError, match='scope'):
        tools.validate_design_escalation(escalation)
