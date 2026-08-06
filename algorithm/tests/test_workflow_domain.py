import importlib.util
import sys
from pathlib import Path


_PATH = Path(__file__).parents[1] / 'lazymind/workflow_domain.py'
_SPEC = importlib.util.spec_from_file_location('workflow_domain', _PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_workflow_names_and_legacy_route_rollback():
    ref = _MODULE.WorkflowSessionRef('s', 'w')
    assert ref.workflow_id == 'w'
    assert _MODULE.public_route() == '/api/workflows'
