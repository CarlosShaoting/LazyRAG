"""Tests for workflow_loader — workflow discovery, state machine, and slot/artifact helpers."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build a temporary workflow directory
# ---------------------------------------------------------------------------

_WORKFLOW_YAML = textwrap.dedent("""\
    id: test-workflow
    name: Test Workflow
    description: A workflow for unit testing.
    steps:
      - id: step_a
        label: Step A
      - id: step_b
        label: Step B
      - id: step_c
        label: Step C
      - id: step_d
        label: Step D
    ui:
      tabs:
        - id: output
          label: Output
          slots:
            - id: text_result
              type: text
              cardinality: single
            - id: image_gallery
              type: image
              cardinality: list
""")

_STATE_YML = textwrap.dedent("""\
    initial: __start__
    transitions:
      __start__:
        - to: step_a
      step_a:
        - to: step_b
        - to: step_a    # full retry
      step_b:
        - to: step_c
        - to: step_b    # full retry
      step_c:
        - to: step_d
        - to: step_b    # re-run from step_b
      step_d:
        - to: step_d    # full retry or partial retry (list slot)
        - to: __end__
    steps:
      step_a:
        prompt: |
          Analyze the input: {{user_input}}.
          {{runtime_instruction}}
          Save result: save_artifacts(artifacts=[
            {'key': 'analysis', 'content_type': 'text', 'value': <text>}
          ]).
        outputs:
          - artifact_id: analysis
            content_type: text
            slot_id: text_result
      step_b:
        prompt: |
          Optimize based on analysis: {{analysis}}.
          {{runtime_instruction}}
        inputs:
          - artifact_id: analysis
            required: true
        outputs:
          - artifact_id: optimized
            content_type: text
            slot_id: text_result
      step_c:
        prompt: |
          Generate image from: {{optimized}}.
          {{runtime_instruction}}
        tools: [gen_tool]
        inputs:
          - artifact_id: optimized
            required: true
        outputs:
          - artifact_id: image_url
            content_type: image
            slot_id: image_gallery
      step_d:
        prompt: |
          Enhance image: {{image_url}}.
          {{runtime_instruction}}
        tools: [enhance_tool]
        inputs:
          - artifact_id: image_url
            required: true
        outputs:
          - artifact_id: enhanced_url
            content_type: image
            slot_id: image_gallery
""")

_SCENARIO_MD = 'Call trigger_test_workflow when user wants to test.\n'
_DRIVER_MD = 'Evaluate step results and describe whether the step is complete.\n'


def make_workflow_dir(tmp_path: Path) -> Path:
    """Create a complete valid workflow directory under tmp_path."""
    workflow_dir = tmp_path / 'workflows' / 'test-workflow'
    scenario_dir = workflow_dir / 'scenario'
    scenario_dir.mkdir(parents=True)
    (workflow_dir / 'workflow.yaml').write_text(_WORKFLOW_YAML)
    (scenario_dir / 'state.yml').write_text(_STATE_YML)
    (scenario_dir / 'scenario.md').write_text(_SCENARIO_MD)
    (scenario_dir / 'driver.md').write_text(_DRIVER_MD)
    return tmp_path / 'workflows'


# ---------------------------------------------------------------------------
# WorkflowSpec loading
# ---------------------------------------------------------------------------

def test_workflowspec_loads_valid_workflow(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')
    assert spec.workflow_id == 'test-workflow'
    assert spec.yaml['name'] == 'Test Workflow'
    assert spec.scenario_md.strip() == _SCENARIO_MD.strip()
    assert spec.driver_md is not None
    assert spec.get_step_mode('step_a') == 'human'


def test_workflowspec_normalises_editor_step_list_and_preserves_mode(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec

    workflows_dir = make_workflow_dir(tmp_path)
    state_path = workflows_dir / 'test-workflow' / 'scenario' / 'state.yml'
    state_path.write_text(textwrap.dedent("""\
        initial: __start__
        transitions:
          __start__:
            - to: step_a
          step_a:
            - to: step_b
          step_b:
            - to: __end__
        steps:
          - id: step_a
            label: Step A
            mode: auto
            prompt: Run A
            outputs: [draft]
          - id: step_b
            label: Step B
            mode: human
            prompt: Run B
    """))

    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')

    assert spec.get_step_config('step_a')['prompt'] == 'Run A'
    assert spec.get_step_config('step_a')['outputs'] == [{'slot': 'draft'}]
    assert spec.get_step_mode('step_a') == 'auto'
    assert spec.get_step_mode('step_b') == 'human'


def test_workflowspec_missing_workflow_yaml_raises(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflow_dir = tmp_path / 'bad-workflow'
    workflow_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        WorkflowSpec('bad-workflow', workflow_dir)


def test_workflowspec_missing_scenario_md_raises(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    (workflows_dir / 'test-workflow' / 'scenario' / 'scenario.md').unlink()
    with pytest.raises(FileNotFoundError):
        WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')


def test_workflowspec_no_driver_md_warns(tmp_path, caplog):
    import logging
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    (workflows_dir / 'test-workflow' / 'scenario' / 'driver.md').unlink()
    with caplog.at_level(logging.WARNING, logger='lazymind.chat.workflow.workflow_loader'):
        spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')
    assert spec.driver_md is None
    assert 'auto mode' in caplog.text.lower() or 'driver.md' in caplog.text


# ---------------------------------------------------------------------------
# get_step_config
# ---------------------------------------------------------------------------

def test_get_step_config_returns_full_dict(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')

    cfg = spec.get_step_config('step_b')
    assert len(cfg['inputs']) == 1
    assert cfg['inputs'][0]['artifact_id'] == 'analysis'
    assert 'outputs' in cfg
    # Retry is expressed via state machine transitions, not a step-level flag.
    assert 're_runnable' not in cfg


def test_get_step_config_unknown_step_returns_empty(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')
    assert spec.get_step_config('nonexistent') == {}


# ---------------------------------------------------------------------------
# get_slot_def
# ---------------------------------------------------------------------------

def test_get_slot_def_found(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')

    slot = spec.get_slot_def('text_result')
    assert slot is not None
    assert slot['cardinality'] == 'single'
    assert slot['type'] == 'text'

    slot_list = spec.get_slot_def('image_gallery')
    assert slot_list is not None
    assert slot_list['cardinality'] == 'list'


def test_get_slot_def_not_found_returns_none(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')
    assert spec.get_slot_def('no_such_slot') is None


# ---------------------------------------------------------------------------
# get_slot_for_artifact
# ---------------------------------------------------------------------------

def test_get_slot_for_artifact_returns_slot_id(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')

    assert spec.get_slot_for_artifact('image_url') == 'image_gallery'
    assert spec.get_slot_for_artifact('optimized') == 'text_result'


def test_get_slot_for_artifact_no_slot(tmp_path):
    from lazymind.chat.workflow.workflow_loader import WorkflowSpec
    workflows_dir = make_workflow_dir(tmp_path)
    spec = WorkflowSpec('test-workflow', workflows_dir / 'test-workflow')
    assert spec.get_slot_for_artifact('unknown_artifact') is None


# load_all registry
# ---------------------------------------------------------------------------

def test_load_all_populates_registry(tmp_path):
    from lazymind.chat.workflow import workflow_loader
    workflows_dir = make_workflow_dir(tmp_path)
    with patch.object(workflow_loader, '_WORKFLOWS_DIR', workflows_dir):
        workflow_loader.load_all()
    try:
        spec = workflow_loader.get_workflow('test-workflow')
        assert spec is not None
        assert spec.workflow_id == 'test-workflow'
    finally:
        workflow_loader.load_all()   # restore original registry


def test_load_all_skips_non_workflow_dirs(tmp_path):
    from lazymind.chat.workflow import workflow_loader
    workflows_dir = make_workflow_dir(tmp_path)
    # Add a directory without workflow.yaml.
    (workflows_dir / 'not-a-workflow').mkdir()
    with patch.object(workflow_loader, '_WORKFLOWS_DIR', workflows_dir):
        workflow_loader.load_all()
    try:
        assert workflow_loader.get_workflow('not-a-workflow') is None
    finally:
        workflow_loader.load_all()


def test_list_workflows_returns_summary(tmp_path):
    from lazymind.chat.workflow import workflow_loader
    workflows_dir = make_workflow_dir(tmp_path)
    with patch.object(workflow_loader, '_WORKFLOWS_DIR', workflows_dir):
        workflow_loader.load_all()
    try:
        workflows = workflow_loader.list_workflows()
        names = [p['id'] for p in workflows]
        assert 'test-workflow' in names
        p = next(x for x in workflows if x['id'] == 'test-workflow')
        assert len(p['steps']) == 4
        assert p['steps'][0]['id'] == 'step_a'
    finally:
        workflow_loader.load_all()
