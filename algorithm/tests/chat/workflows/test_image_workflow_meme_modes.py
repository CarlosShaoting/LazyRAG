from __future__ import annotations

from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_workflow() -> dict:
    path = _repo_root() / 'workflows' / 'image-workflow' / 'workflow.yaml'
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def _load_state() -> dict:
    path = _repo_root() / 'workflows' / 'image-workflow' / 'scenario' / 'state.yml'
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def test_image_workflow_declares_three_canonical_meme_routes():
    prompt = _load_state()['steps']['analyze_subject']['prompt']

    assert 'CREATE_STATIC_MEME' in prompt
    assert 'CREATE_ANIMATED_MEME' in prompt
    assert 'CREATE_MEME_PACK' in prompt
    assert 'Explicit multi-item meme/reaction/sticker pack → CREATE_MEME_PACK' in prompt
    assert 'One explicit animated meme/reaction/chat sticker → CREATE_ANIMATED_MEME' in prompt
    assert 'One explicit static meme/reaction/chat sticker → CREATE_STATIC_MEME' in prompt


def test_optimize_step_produces_optional_structured_meme_plan():
    workflow = _load_workflow()
    state = _load_state()
    slots = {slot['id']: slot for slot in workflow['slots']}
    optimize = state['steps']['optimize_prompt']

    assert slots['meme_generation_plan'] == {
        'id': 'meme_generation_plan',
        'label': 'Meme Generation Plan',
        'type': 'json',
        'cardinality': 'single',
    }
    assert {'material': 'meme_generation_plan', 'required': False} in optimize['outputs']

    prompt = optimize['prompt']
    for field in (
        'schema_version', 'mode', 'delivery', 'count', 'items', 'caption',
        'communication_task', 'image_prompt', 'motion_prompt',
    ):
        assert field in prompt
    assert 'Cap static packs at 12 items and animated packs at 5 items' in prompt


def test_generate_state_owns_three_distinct_meme_strategies():
    workflow = _load_workflow()
    state = _load_state()
    generate = state['steps']['generate_image']
    prompt = generate['prompt']

    assert 'Mode 1: one static meme (CREATE_STATIC_MEME)' in prompt
    assert 'Mode 2: one animated meme (CREATE_ANIMATED_MEME)' in prompt
    assert 'Mode 3: meme pack (CREATE_MEME_PACK)' in prompt
    assert 'stop before calling a paid media tool' in prompt

    assert {'material': 'meme_generation_plan', 'required': False} in generate['inputs']
    assert {'material': 'meme_static_output', 'required': False} in generate['outputs']
    assert set(generate['tools']) >= {
        'image_generator', 'image_editor', 'video_generator', 'video_to_gif',
    }

    slots = {slot['id']: slot for slot in workflow['slots']}
    assert slots['meme_static_output']['type'] == 'image'
    assert slots['meme_static_output']['cardinality'] == 'list'
    assert slots['meme_static_output']['ordered'] is True


def test_existing_non_meme_routes_remain_available():
    state = _load_state()
    analyze_prompt = state['steps']['analyze_subject']['prompt']
    generate_prompt = state['steps']['generate_image']['prompt']

    for route in (
        'CREATE_NEW', 'KB_STYLE', 'REFERENCE_GENERATE', 'FIND_AND_EDIT',
        'EDIT_UPLOAD', 'CREATE_ANIMATED', 'ANIMATE_UPLOAD',
    ):
        assert route in analyze_prompt
    assert 'ordinary still image (CREATE_NEW / KB_STYLE / REFERENCE_GENERATE)' in generate_prompt
    assert 'legacy' in generate_prompt
    assert 'CREATE_ANIMATED / ANIMATE_UPLOAD routes' in generate_prompt
