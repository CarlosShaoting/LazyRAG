"""Real macOS computation and fail-closed isolation through the shared executor."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lazymind.document_tools.paper.execution import container, macos


NATIVE_MACOS = pytest.mark.skipif(sys.platform != 'darwin', reason='Requires macOS Seatbelt')


@pytest.mark.parametrize('available', [True, False])
def test_macos_environment_validation(monkeypatch, available):
    validate = Mock(side_effect=None if available else OSError('Seatbelt unavailable'))
    monkeypatch.setattr(container, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(macos, 'validate_environment', validate)
    if available:
        container.validate_environment()
    else:
        with pytest.raises(container.ContainerEnvironmentError, match='Seatbelt unavailable'):
            container.validate_environment()
    validate.assert_called_once()


def test_macos_launch_failure_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(container, 'sys', SimpleNamespace(platform='darwin', executable=sys.executable))
    monkeypatch.setattr(macos, 'start', Mock(side_effect=OSError('Seatbelt launch failed')))
    host = Mock(side_effect=AssertionError('Must not launch an unrestricted worker'))
    monkeypatch.setattr(container.subprocess, 'Popen', host)
    with pytest.raises(container.ContainerEnvironmentError, match='Seatbelt launch failed'):
        container.execute({}, tmp_path / 'worker.py', 1, label='test')
    host.assert_not_called()


@NATIVE_MACOS
@pytest.mark.parametrize('failure', ['timeout', 'storage', 'memory', 'profile'])
def test_macos_failure_terminates_and_cleans(monkeypatch, tmp_path, failure):
    start = macos.start
    children = []

    def capture(worker, scratch, timeout, streams, env):
        process = start(worker, scratch, timeout, streams, env)
        children.append((process, scratch.parent))
        if failure == 'storage':
            process.wait(timeout=5)  # Enforce storage even after a fast worker exits.
        return process

    monkeypatch.setattr(macos, 'start', capture)
    code = 'import time; time.sleep(30)'
    error = '超时'
    if failure == 'storage':
        monkeypatch.setattr(macos, 'STORAGE_LIMIT', 1024)
        code = 'from pathlib import Path\nPath("one").write_bytes(b"x" * 768)\n' \
               'Path("two").write_bytes(b"x" * 768)\nprint("{}")\n'
        error = '临时存储合计'
    elif failure == 'memory':
        monkeypatch.setattr(macos, 'MEMORY_LIMIT', 32 * 1024 ** 2)
        code = 'import time\ndata = bytearray(64 * 1024 ** 2)\ntime.sleep(30)\n'
        error = '内存超过'
    elif failure == 'profile':
        monkeypatch.setattr(macos, '_profile', lambda _: '(version 1)\n(invalid-operation)')
        marker = tmp_path / 'must-not-execute'
        code = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nprint("{{}}")\n'
        error = '沙箱启动失败'
    worker = tmp_path / 'worker.py'
    worker.write_text(code, encoding='utf-8')
    with pytest.raises(RuntimeError, match=error):
        container.execute({}, worker, 1 if failure == 'timeout' else 10, label='macOS test')
    assert children and all(process.poll() is not None and not root.exists() for process, root in children)
    if failure == 'profile':
        assert not marker.exists()


@NATIVE_MACOS
def test_macos_experiment_worker():
    worker = Path(container.__file__).parent.parent / 'experiment' / 'worker.py'
    result = container.execute({
        'config': {'scale': 2}, 'data': [1, 2, 3],
        'code': 'import numpy as np\n'
                'def run_experiment(config, data):\n'
                '    print("experiment completed")\n'
                '    return [{"mean": float(np.mean(data)) * config["scale"]}]\n',
    }, worker, 30, label='macOS experiment')
    assert result == {'records': [{'mean': 4.0}], 'logs': 'experiment completed\n'}


@NATIVE_MACOS
def test_macos_relative_paths_and_unicode_workspace(tmp_path, monkeypatch):
    directory = tmp_path / '论文 执行目录'
    directory.mkdir()
    monkeypatch.setattr(container.tempfile, 'tempdir', str(directory))
    worker = directory / 'worker.py'
    worker.write_text('import json\nfrom pathlib import Path\np=Path("结果.txt")\n'
                      'p.write_text("真实结果", encoding="utf-8")\n'
                      'print(json.dumps({"text":p.read_text(encoding="utf-8")}))\n', encoding='utf-8')
    assert container.execute({}, worker, 10, label='macOS text') == {'text': '真实结果'}
