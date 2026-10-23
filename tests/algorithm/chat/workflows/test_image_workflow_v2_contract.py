import base64
from pathlib import Path

import yaml

from lazymind.workflow_toolkit import load_workflow_package_tools


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_ROOT = ROOT / 'workflows' / 'image-workflow-v2'


def _load(relative_path: str):
    return yaml.safe_load((WORKFLOW_ROOT / relative_path).read_text(encoding='utf-8'))


def test_package_declares_three_final_deliverable_routes():
    workflow = _load('workflow.yaml')
    state = _load('scenario/state.yml')
    targets = {edge['to'] for edge in state['transitions']['classify_request']}
    assert targets == {'ordinary_prepare', 'edit_prepare', 'meme_brief'}
    assert workflow['runtime']['publisher_owned_slots'] == [
        'route_plan', 'material_summary', 'ordinary_prompt',
        'ordinary_output', 'authoritative_image', 'edit_contract', 'edit_candidate',
    ]
    assert state['steps']['classify_request']['tools'] == ['classify_image_request']
    assert state['steps']['classify_request']['terminal_tools'] == ['classify_image_request']
    assert state['steps']['classify_request']['inputs'] == [
        {'material': 'source_image', 'required': False},
    ]
    assert state['steps']['ordinary_prepare']['tools'] == ['prepare_ordinary_request']
    assert state['steps']['ordinary_prepare']['terminal_tools'] == ['prepare_ordinary_request']
    assert state['steps']['edit_prepare']['terminal_tools'] == ['publish_edit_contract']
    assert 'publish_edit_contract' in state['steps']['edit_prepare']['tools']


def test_completed_corrections_route_to_the_existing_branch_owner():
    runtime = _load('workflow.yaml')['runtime']
    routing = runtime['completed_edit_routing']
    assert 'Never call a Workflow trigger' in routing
    assert 'ordinary_generate is an effective completed step' in routing
    assert 'rewinds to ordinary_generate' in routing
    assert 'edit_candidate is an effective completed step' in routing
    assert 'rewinds to edit_candidate' in routing
    assert 'wording, state, action, count, delivery-mode' in routing
    assert 'rewind to meme_brief' in routing
    assert 'rewind to build_identity_anchors' in routing
    assert 'current rewindable_steps list' in routing


def test_ordinary_and_edit_routes_use_configured_global_media_models():
    workflow = _load('workflow.yaml')
    state = _load('scenario/state.yml')
    declarations = {
        entry['path']: set(entry['functions'])
        for entry in workflow['tool_scripts']
    }
    assert declarations['scripts/media.py'] == {
        'generate_ordinary_image',
        'generate_edit_candidate',
    }
    assert 'publish_edit_contract' in declarations['scripts/tools.py']
    assert state['steps']['ordinary_generate']['tools'] == ['generate_ordinary_image']
    assert state['steps']['ordinary_generate']['terminal_tools'] == ['generate_ordinary_image']
    assert state['steps']['edit_candidate']['tools'] == ['generate_edit_candidate']
    assert state['steps']['edit_candidate']['terminal_tools'] == ['generate_edit_candidate']
    ordinary_prompt = ' '.join(state['steps']['ordinary_generate']['prompt'].split())
    assert 'globally configured LazyMind' in ordinary_prompt
    assert 'Seedream' not in ordinary_prompt
    edit_prompt = ' '.join(state['steps']['edit_candidate']['prompt'].split())
    assert 'authoritative image and complete edit contract' in edit_prompt
    assert 'globally configured LazyMind image-editor role' in edit_prompt


def test_meme_route_keeps_native_media_toolchain_and_validated_brief():
    workflow = _load('workflow.yaml')
    state = _load('scenario/state.yml')
    support_tools = next(
        set(entry['functions'])
        for entry in workflow['tool_scripts']
        if entry['path'] == 'scripts/tools.py'
    )
    assert {
        'save_validated_meme_brief',
        'run_and_save_meme_preflight',
        'compose_character_anchor_sheet',
        'meme_add_caption',
        'meme_video_to_captioned_gif',
    } <= support_tools
    assert state['steps']['meme_brief']['tools'] == ['save_validated_meme_brief']
    assert state['steps']['meme_preflight']['tools'] == ['run_and_save_meme_preflight']
    assert state['steps']['meme_preflight']['terminal_tools'] == ['run_and_save_meme_preflight']
    assert state['steps']['render_static']['tools'] == ['image_editor']
    assert state['steps']['render_keyframes']['tools'] == ['image_editor']
    assert state['steps']['video_canary']['tools'] == ['video_generator']
    assert state['steps']['caption_dynamic']['tools'] == ['meme_video_to_captioned_gif']
    review_inputs = state['steps']['review_pack']['inputs']
    assert {'material': 'canonical_character_image', 'required': True} in review_inputs
    assert (
        'Never fan out concurrent multimodal calls'
        in state['steps']['review_pack']['prompt']
    )


def test_ui_uses_picture_production_and_hides_empty_branch_outputs():
    workflow = _load('workflow.yaml')
    tabs = {tab['id']: tab for tab in workflow['ui']['tabs']}
    assert workflow['i18n']['zh-CN']['tabs']['production']['label'] == '图片制作'
    assert tabs['character']['composite_behavior']['hide_empty_columns'] is True
    assert tabs['production']['composite_behavior']['hide_empty_columns'] is True

    character_slots = {slot['id'] for slot in tabs['character']['slots']}
    production_slots = {slot['id'] for slot in tabs['production']['slots']}
    # The four individual anchor images remain authoritative workflow material,
    # but the Character tab shows only their composed 2x2 review sheet.
    assert 'face_anchor_grid' in character_slots
    assert 'face_anchor_images' not in character_slots
    assert {'canary_video', 'remaining_videos'} <= production_slots

    widgets = workflow['ui']['slots']
    assert widgets['hero_no_text']['itemLayout'] == 'grid'
    assert widgets['hero_no_text']['gridMaxCols'] == 6
    assert widgets['master_keyframes']['itemLayout'] == 'grid'
    assert widgets['remaining_videos']['itemLayout'] == 'grid'
    assert 'pack_review' not in {slot['id'] for slot in tabs['result']['slots']}
    assert 'pack_review' not in tabs['result']['composite_layout']
    assert all(widgets[slot]['readOnly'] is True for slot in (
        'canonical_character_image',
        'character_identity_prompt',
        'face_anchor_grid',
        'hero_no_text',
        'master_keyframes',
        'canary_video',
        'remaining_videos',
    ))


def test_static_and_dynamic_meme_routes_are_mutually_exclusive():
    state = _load('scenario/state.yml')
    assert state['transitions']['design_best_performances'] == [
        {'to': 'plan_static', 'when': 'meme_brief_data.delivery_mode is static'},
        {'to': 'plan_dynamic', 'when': 'meme_brief_data.delivery_mode is dynamic'},
    ]
    assert state['transitions']['caption_static'] == [{'to': 'review_pack'}]
    assert state['transitions']['caption_dynamic'] == [{'to': 'review_pack'}]


def test_three_routes_declare_the_original_human_interaction_contract():
    state = _load('scenario/state.yml')
    steps = state['steps']

    # Ordinary generation is intentionally automatic from preparation to output.
    assert steps['ordinary_prepare'].get('mode', 'auto') != 'human'
    assert steps['ordinary_generate'].get('mode', 'auto') != 'human'

    # Local editing stops on the generated candidate and owns its correction rerun.
    assert steps['edit_candidate']['mode'] == 'human'
    assert 'rejects the candidate' in steps['edit_candidate']['rerun_when']

    # Static memes stop for the complete brief and the 2x2 identity anchors only.
    assert steps['meme_brief']['mode'] == 'human'
    assert steps['build_identity_anchors']['mode'] == 'human'
    assert steps['render_static'].get('mode', 'auto') == 'auto'
    assert steps['caption_static'].get('mode', 'auto') == 'auto'
    assert steps['review_pack'].get('mode', 'auto') == 'auto'

    # Dynamic memes add key-image and complete-video-set approval checkpoints.
    assert steps['render_keyframes']['mode'] == 'human'
    assert steps['render_dynamic']['mode'] == 'human'
    assert 'skip_if' not in steps['render_dynamic']
    assert 'placeholder remaining_videos artifact' in steps['render_dynamic']['prompt']
    assert 'one-state video set' in steps['render_dynamic']['prompt']

    for step_id in (
        'edit_candidate', 'meme_brief', 'build_identity_anchors',
        'render_keyframes', 'render_dynamic',
    ):
        assert steps[step_id]['rerun_when'].strip()


def test_workflow_contains_no_workplace_meme_template_or_replay_feature():
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in WORKFLOW_ROOT.rglob('*')
        if path.is_file() and path.suffix in {'.yaml', '.yml', '.md', '.py'}
    ).lower()
    forbidden = (
        '_workplace_meme_performances', '职场文字抽象梗',
        '收到', '辛苦了', '加油', '下班', 'replay', '回放',
    )
    assert all(term not in source for term in forbidden)


def test_declared_tool_scripts_load_from_an_immutable_package():
    workflow = _load('workflow.yaml')
    names = [
        name
        for declaration in workflow['tool_scripts']
        for name in declaration['functions']
    ]
    files = {
        path.relative_to(WORKFLOW_ROOT).as_posix(): base64.b64encode(path.read_bytes()).decode()
        for path in WORKFLOW_ROOT.rglob('*')
        if path.is_file() and '__pycache__' not in path.parts
    }
    tools = load_workflow_package_tools(
        {'files': files}, names, 'image-workflow-v2', 'test-revision',
    )
    assert set(tools) == set(names)
    base_tools = tools['meme_add_caption'].__globals__['_legacy_image_tools']()
    assert callable(base_tools.meme_add_caption)
