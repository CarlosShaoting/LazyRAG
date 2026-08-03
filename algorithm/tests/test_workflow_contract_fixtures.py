import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / 'lazymind/workflow_contracts.py'
_SPEC = importlib.util.spec_from_file_location('workflow_contracts', _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
read_golden = _MODULE.read_golden
read_baseline_manifest = _MODULE.read_baseline_manifest
replay_projection = _MODULE.replay_projection


def test_python_reads_all_workflow_golden_fixtures():
    root = Path(__file__).parents[2]
    fixtures = sorted(
        (root / 'docs/plan/workflow/contracts/v1/golden').glob('*.json')
    )
    manifest = read_baseline_manifest(
        root / 'docs/plan/workflow/contracts/v1/baseline-manifest.json'
    )
    assert len(fixtures) == len(manifest.required_scenarios) + 1
    seen = set()
    for path in fixtures:
        fixture = read_golden(path)
        seen.add(fixture.scenario)
        assert fixture.events
        assert 'status' in fixture.projection
        assert replay_projection(fixture.events) == fixture.projection
    assert set(manifest.required_scenarios) <= seen


def test_advance_tools_share_transition_but_not_wait_semantics():
    root = Path(__file__).parents[2]
    manifest = read_baseline_manifest(
        root / 'docs/plan/workflow/contracts/v1/baseline-manifest.json'
    )
    sync = manifest.tool_semantics['advance_step']
    handoff = manifest.tool_semantics['advance_step_and_hand_off']
    assert sync['transition'] == handoff['transition']
    assert sync['wait'] == 'attempt_terminal'
    assert handoff['wait'] == 'durable_submission'
