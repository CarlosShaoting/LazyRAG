import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _subprocess_env():
    env = os.environ.copy()
    env.update({
        'PYTHONPATH': os.pathsep.join((
            str(_REPO_ROOT / 'algorithm' / 'lazyllm'),
            str(_REPO_ROOT / 'algorithm'),
        )),
        'PYTHONDONTWRITEBYTECODE': '1',
        'LAZYLLM_INIT_DOC': 'False',
        'LAZYMIND_ENABLE_ROUTER': 'false',
        'LAZYMIND_BACKGROUND_JOBS_ENABLED': 'false',
        'LAZYMIND_WORKFLOWS_DIR': str(_REPO_ROOT / 'workflows'),
    })
    return env


def _run_probe(script: str, timeout: float = 35) -> dict:
    with tempfile.TemporaryDirectory(prefix='runtime-probe-traces-') as trace_dir:
        env = _subprocess_env()
        env['LAZYLLM_TRACE_LOCAL_STORAGE_DIR'] = trace_dir
        completed = subprocess.run(
            [sys.executable, '-c', script],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _fresh_loader():
    from lazymind.chat import runtime_loader
    return importlib.reload(runtime_loader)


def test_chat_runtime_loader_is_single_flight(monkeypatch):
    loader = _fresh_loader()
    sentinel = SimpleNamespace(name='chat-service')
    calls = []
    real_import = loader.importlib.import_module

    def fake_import(name):
        if name != 'lazymind.chat.service.chat_service':
            return real_import(name)
        calls.append(name)
        time.sleep(0.03)
        return sentinel

    monkeypatch.setattr(loader.importlib, 'import_module', fake_import)
    results = []
    threads = [threading.Thread(target=lambda: results.append(loader.ensure_chat_runtime())) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == ['lazymind.chat.service.chat_service']
    assert results == [sentinel] * 5
    assert loader.chat_runtime_status() == 'ready'


def test_rag_runtime_loader_is_single_flight(monkeypatch):
    loader = _fresh_loader()
    sentinel = SimpleNamespace(name='kb')
    calls = []

    def fake_import(name):
        calls.append(name)
        time.sleep(0.03)
        return sentinel

    monkeypatch.setattr(loader.importlib, 'import_module', fake_import)

    results = []
    threads = [threading.Thread(target=lambda: results.append(loader.ensure_rag_runtime())) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == ['lazymind.chat.engine.tools.kb']
    assert results == [sentinel] * 5
    assert loader.rag_runtime_status() == 'ready'


def test_background_warmup_waits_before_loading(monkeypatch):
    loader = _fresh_loader()
    calls = []
    monkeypatch.setattr(loader, '_wait_for_kb_runtime', lambda: calls.append('dependencies'))
    monkeypatch.setattr(loader, 'ensure_chat_runtime', lambda: calls.append('chat'))
    monkeypatch.setattr(loader, 'ensure_rag_runtime', lambda: calls.append('rag'))

    loader._wait_and_warm()

    assert calls == ['dependencies', 'chat', 'rag']


def test_chat_service_starts_under_three_seconds_without_rag():
    result = _run_probe('''
import json
import sys
import time
loader_started = time.perf_counter()
from lazymind.chat.runtime_loader import ensure_chat_runtime
loader_elapsed = time.perf_counter() - loader_started
cpu_started = time.process_time()
started = time.perf_counter()
ensure_chat_runtime()
elapsed = time.perf_counter() - started
cpu_elapsed = time.process_time() - cpu_started
result = {
    "elapsed": elapsed,
    "rag_loaded": "lazyllm.tools.rag" in sys.modules,
    "runtime_docs_loaded": any(name.startswith("lazyllm.docs.tools") for name in sys.modules),
    "phase_seconds": {
        "runtime_loader_import": loader_elapsed,
        "chat_runtime_import": elapsed,
        "chat_runtime_cpu": cpu_elapsed,
        "total_imports": loader_elapsed + elapsed,
    },
}
# Collect metadata after the measured imports; never dump the process environment.
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
versions = {}
for package in ("lazyllm", "fastapi", "starlette", "pydantic", "dashscope"):
    try:
        versions[package] = version(package)
    except PackageNotFoundError:
        versions[package] = "not installed"
result["environment"] = {
    "python_version": platform.python_version(),
    "python_implementation": platform.python_implementation(),
    "python_executable": sys.executable,
    "os": platform.system(),
    "os_release": platform.release(),
    "architecture": platform.machine(),
    "cpu_count": os.cpu_count(),
    "installed_dependency_versions": versions,
    "module_paths": {
        name: str(Path(sys.modules[name].__file__).resolve())
        for name in ("lazyllm", "fastapi", "lazymind.chat.runtime_loader", "lazymind.chat.service.chat_service")
    },
}
print(json.dumps(result))
''')

    # Pytest only renders this captured report if a startup requirement fails.
    diagnostics = 'Chat startup diagnostics:\n' + json.dumps(result, indent=2, sort_keys=True)
    assert result['elapsed'] < 3.0, diagnostics
    assert result['rag_loaded'] is False, diagnostics
    assert result['runtime_docs_loaded'] is False, diagnostics


def test_slow_chat_startup_reports_diagnostics_without_environment_secrets(monkeypatch, capsys):
    real_probe = _run_probe

    def slow_probe(script, timeout=35):
        result = real_probe(script, timeout)
        result['elapsed'] = 3.25
        return result

    monkeypatch.setenv('STARTUP_DIAGNOSTIC_SECRET', 'private-fixture-value')
    monkeypatch.setattr(sys.modules[__name__], '_run_probe', slow_probe)
    with pytest.raises(AssertionError) as raised:
        test_chat_service_starts_under_three_seconds_without_rag()

    message = str(raised.value)
    marker = 'Chat startup diagnostics:\n'
    assert marker in message
    diagnostics, _ = json.JSONDecoder().raw_decode(message.split(marker, 1)[1].lstrip())
    assert diagnostics['elapsed'] == 3.25
    assert diagnostics['phase_seconds']['runtime_loader_import'] >= 0
    assert diagnostics['phase_seconds']['chat_runtime_import'] >= 0
    assert diagnostics['phase_seconds']['chat_runtime_cpu'] >= 0
    assert diagnostics['environment']['python_version'] == sys.version.split()[0]
    assert diagnostics['environment']['installed_dependency_versions']['fastapi']
    source = Path(diagnostics['environment']['module_paths']['lazymind.chat.service.chat_service'])
    assert source == _REPO_ROOT / 'algorithm/lazymind/chat/service/chat_service.py'
    assert 'STARTUP_DIAGNOSTIC_SECRET' not in message
    assert 'private-fixture-value' not in message
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


def test_trace_maintenance_registers_its_config_without_runtime_docs():
    result = _run_probe('''
import json
import sys
from lazymind.chat.service.utils.trace_archive import start_local_trace_maintenance
start_local_trace_maintenance()
from lazyllm.configs import config
print(json.dumps({
    "trace_backend": config["trace_backend"],
    "runtime_docs_loaded": any(name.startswith("lazyllm.docs.tools") for name in sys.modules),
}))
''')

    assert result['trace_backend']
    assert result['runtime_docs_loaded'] is False


def test_background_warmup_loads_rag_within_thirty_seconds_without_request():
    result = _run_probe('''
import json
import time
import lazymind.chat.runtime_loader as loader
loader._wait_for_kb_runtime = lambda: None
started = time.perf_counter()
loader.start_background_chat_runtime_warmup()
deadline = started + 30
while loader.rag_runtime_status() not in {"ready", "failed"} and time.perf_counter() < deadline:
    time.sleep(0.01)
print(json.dumps({
    "elapsed": time.perf_counter() - started,
    "chat": loader.chat_runtime_status(),
    "rag": loader.rag_runtime_status(),
}))
''')

    assert result['elapsed'] < 30
    assert result['chat'] == 'ready'
    assert result['rag'] == 'ready'


def test_kb_request_triggers_rag_before_background_dependencies_are_ready():
    result = _run_probe('''
import json
import threading
import time
import lazymind.chat.runtime_loader as loader
from lazymind.chat.engine.tools.lazy_kb import KBToolkit
dependency_gate = threading.Event()
loader._wait_for_kb_runtime = lambda: dependency_gate.wait(30)
loader.start_background_chat_runtime_warmup()
real_ensure = loader.ensure_rag_runtime
def load_then_stop():
    real_ensure()
    raise RuntimeError("stop after loading")
loader.ensure_rag_runtime = load_then_stop
started = time.perf_counter()
try:
    KBToolkit().kb_search("trigger warmup")
except RuntimeError as exc:
    assert str(exc) == "stop after loading"
print(json.dumps({
    "elapsed": time.perf_counter() - started,
    "rag": loader.rag_runtime_status(),
    "dependencies_released": dependency_gate.is_set(),
}))
dependency_gate.set()
''')

    assert result['elapsed'] < 30
    assert result['rag'] == 'ready'
    assert result['dependencies_released'] is False


def test_temporary_mode_persists_without_importing_rag(tmp_path):
    script = r'''
import importlib.abc
import json
import sys
class NoRAG(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'lazyllm.tools.rag' or fullname.startswith('lazyllm.tools.rag.'):
            raise AssertionError('Session initialization imported RAG: ' + fullname)
sys.meta_path.insert(0, NoRAG())
from lazymind.chat.engine.tools import temporary_retrieval_session as session
session.workspace_for_request = lambda **kwargs: TEST_ROOT
session.is_model_role_available = lambda role: AVAILABLE
mode = session.initialize_temporary_retrieval({'user_id': 'alice', 'conversation_id': 'chat'})
assert 'lazyllm.tools.rag' not in sys.modules
print(json.dumps({'use_embed': mode}))
'''.replace('TEST_ROOT', repr(str(tmp_path)))
    assert _run_probe(script.replace('AVAILABLE', 'False')) == {'use_embed': False}
    # A fresh process and changed configuration still use the saved choice.
    assert _run_probe(script.replace('AVAILABLE', 'True')) == {'use_embed': False}


def test_temporary_attachment_retrieval_without_rag(tmp_path):
    result = _run_probe(r'''
import importlib.abc
import json
import os
import sys
from pathlib import Path

class NoOptionalRAG(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'spacy', 'pymilvus', 'milvus_lite', 'grpc', 'opensearchpy',
            'opensearch_protobufs', 'nltk', 'sentencepiece',
        }:
            raise AssertionError("Optional dependency loaded: " + fullname)
        if fullname in {
            'lazymind.chat.engine.tools.kb',
            'lazymind.chat.engine.tools.algo.search_kb',
        }:
            raise AssertionError("Knowledge-base service loaded: " + fullname)

sys.meta_path.insert(0, NoOptionalRAG())
os.environ['LAZYMIND_RAG_ENABLED'] = '0'
os.environ['LAZYLLM_HOME'] = TEST_ROOT
import lazyllm
from lazymind.chat.engine.tools.lazy_kb import kb_tmp_search
from lazymind.chat.engine.tools import temporary_files
from lazymind.chat.engine.tools import temporary_retrieval_session as session
from lazymind.chat.engine.tools.algo import search_temp
from lazymind.chat import runtime_loader
from lazymind.chat.engine.tools.file_resources import store

root = Path(TEST_ROOT)
fruit = root / 'fruit.txt'
fruit.write_text('苹果香蕉水果采购清单。', encoding='utf-8')
rail = root / 'rail.txt'
rail.write_text('火车铁路运行时刻表。', encoding='utf-8')
lazyllm.globals['agentic_config'] = {
    'files': [str(fruit), str(rail)],
    'history_files_per_turn': {},
    'user_id': 'test',
    'conversation_id': 'temporary-files-test',
}
def workspace(user_id=None, conversation_id=None):
    cfg = lazyllm.globals['agentic_config']
    return str(root / (user_id or cfg['user_id']) / (conversation_id or cfg['conversation_id']))
store.workspace_for_request = workspace
session.workspace_for_request = workspace
temporary_files.get_vocab_manager = lambda _: lambda query: query
available = False
session.is_model_role_available = lambda role: available
search_temp._build_reranker = lambda: None
calls = []
fail_embed = False
def embed(text):
    calls.append(text)
    if fail_embed:
        raise RuntimeError('embedding unavailable')
    return [1.0, 0.0] if '苹果' in text else [0.0, 1.0]
search_temp.AutoModel = lambda model: embed

bm25 = kb_tmp_search(semantic_query='苹果水果')
assert bm25['channels']['semantic'] == 'bm25_chinese', bm25
assert bm25['hits'][0]['target'] == 'fruit.txt', bm25
assert not bm25['skipped'], bm25
assert not calls
grep = kb_tmp_search(grep_patterns=['时刻表'])
assert grep['hits'][0]['target'] == 'rail.txt', grep
assert grep['hits'][0]['line'] == 1

available = True
# Same chat remains BM25 even after cache eviction or a newly configured model.
original = search_temp._ensure_retriever()
search_temp._session_retrievers.clear()
again = kb_tmp_search(semantic_query='苹果水果')
assert again['channels']['semantic'] == 'bm25_chinese', again
assert not calls
assert search_temp._ensure_retriever() is not original

# A separate chat chooses vector retrieval with its own nodes, even for the same files.
lazyllm.globals['agentic_config']['conversation_id'] = 'vector-chat'
vector = kb_tmp_search(semantic_query='苹果水果')
assert vector['channels']['semantic'] == 'vector', vector
assert vector['hits'][0]['target'] == 'fruit.txt', vector
assert not vector['skipped'], vector
assert calls
vector_retriever = search_temp._ensure_retriever()
assert vector_retriever is not original
calls.clear()
available = False
still_vector = kb_tmp_search(semantic_query='苹果水果')
assert still_vector['channels']['semantic'] == 'vector', still_vector
assert calls
fail_embed = True
failed = kb_tmp_search(semantic_query='苹果水果')
assert failed['channels']['semantic'] == 'degraded', failed
assert failed['hits'] == [], failed
assert any('embedding unavailable' in item['reason'] for item in failed['skipped']), failed
fail_embed = False
calls.clear()
lazyllm.globals['agentic_config']['conversation_id'] = 'temporary-files-test'
again = kb_tmp_search(semantic_query='苹果水果')
assert again['channels']['semantic'] == 'bm25_chinese', again
assert not calls

# Two BM25 chats sharing source paths must not share document/chunk instances.
first = search_temp._ensure_retriever()._get_retrievers((str(fruit), str(rail)))
lazyllm.globals['agentic_config']['conversation_id'] = 'another-bm25-chat'
other = kb_tmp_search(semantic_query='苹果水果')
assert other['hits'][0]['target'] == 'fruit.txt', other
second = search_temp._ensure_retriever()._get_retrievers((str(fruit), str(rail)))
assert first is not second
assert first[0]._docs[0] is not second[0]._docs[0]
first_ids = {node.uid for node in first[0]('苹果水果')}
second_ids = {node.uid for node in second[0]('苹果水果')}
assert first_ids and second_ids and first_ids.isdisjoint(second_ids)
assert runtime_loader.rag_runtime_status() == 'not_installed'
print(json.dumps({'bm25': bm25['total'], 'vector': vector['total']}))
'''.replace('TEST_ROOT', repr(str(tmp_path))))

    assert result['bm25'] > 0
    assert result['vector'] > 0
