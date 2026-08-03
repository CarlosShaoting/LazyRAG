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


def test_python_reads_all_workflow_golden_fixtures():
    root = Path(__file__).parents[2]
    fixtures = sorted(
        (root / 'docs/plan/plugin/contracts/v1/golden').glob('*.json')
    )
    assert len(fixtures) == 8
    for path in fixtures:
        fixture = read_golden(path)
        assert fixture.events
        assert 'status' in fixture.projection


def test_advance_tools_share_transition_but_not_wait_semantics():
    root = Path(__file__).parents[2]
    serial = read_golden(
        root / 'docs/plan/plugin/contracts/v1/golden/serial.json'
    )
    handoff = read_golden(
        root / 'docs/plan/plugin/contracts/v1/golden/handoff.json'
    )
    assert serial.attempts[0]['operation'] == handoff.attempts[0]['operation']
    assert serial.attempts[0]['status'] == 'succeeded'
    assert handoff.attempts[0]['status'] == 'queued'
