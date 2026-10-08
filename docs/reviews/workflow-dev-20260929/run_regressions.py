"""Run the review probes without copying tests into production packages.

Usage from any directory: python /path/to/this/run_regressions.py
The Python environment must include pytest and normal algorithm dependencies.
Expected on reviewed commit: 6 Python failures and 1 Go failure; fixed code should pass.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('REVIEW_ROOT', HERE.parents[2])).resolve()
env = dict(os.environ)
env['REVIEW_ROOT'] = str(ROOT)
env['PYTHONPATH'] = os.pathsep.join(filter(None, [
    str(ROOT / 'algorithm'), str(ROOT / 'algorithm/lazyllm'), env.get('PYTHONPATH'),
]))
py = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(HERE / 'reproduce_python.py')], cwd=ROOT, env=env)
with tempfile.TemporaryDirectory(prefix='workflow-review-overlay-') as directory:
    overlay = Path(directory) / 'overlay.json'
    overlay.write_text(json.dumps({'Replace': {
        str(ROOT / 'backend/core/workflow/store/review_regression_test.go'): str(HERE / 'reproduce_product_test.go'),
    }}))
    go = subprocess.run(['go', 'test', '-overlay', str(overlay), './workflow/store',
                         '-run', '^TestReviewStageActionMustNotAcceptUnseenHighRiskDecision$', '-count=1'],
                        cwd=ROOT / 'backend/core')
sys.exit(1 if py.returncode or go.returncode else 0)
