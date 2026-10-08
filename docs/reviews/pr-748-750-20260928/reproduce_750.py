"""Reviewer-added tests: assertions describe required behavior, not current defects."""
import asyncio
import json
import time
from unittest.mock import MagicMock

import requests
from lazyllm import OnlineChatModule
import test_subagent_runner as harness


def setup_runner(monkeypatch, tmp_path, artifacts=(), output_slots=(), params=None):
    harness._install_fake_lazyllm(monkeypatch)
    model = MagicMock()
    model.share.return_value.return_value = 'NO\nNo readable deliverable exists.'
    monkeypatch.setattr(harness.runner_mod, 'AutoModel', lambda **kw: model)
    harness._install_fake_translator(monkeypatch)
    monkeypatch.setattr(harness.runner_mod, '_generate_display_plan', lambda *a, **k: ['Read', 'Analyze', 'Deliver'])
    harness._install_fake_drive(monkeypatch, [], final_value='Here is the completed analysis.')
    return {
        **harness._DEFAULT_TASK, 'workspace_path': str(tmp_path),
        'agent_type': 'research', 'objective': 'Explain the answer in plain text.',
        'output_artifact_keys': list(output_slots), 'output_slots': list(output_slots),
        'params': params or {}, 'artifacts': list(artifacts),
    }


def test_review_completion_does_not_block_event_loop(monkeypatch, tmp_path):
    task = setup_runner(monkeypatch, tmp_path)
    model = MagicMock()
    delays = []
    def evaluate(_prompt):
        time.sleep(0.20)  # Controlled stand-in for a blocking provider HTTP call.
        return json.dumps({'completed': True, 'requires_artifact': False,
                           'artifact_keys': [], 'reason': 'Analysis delivered.'})
    model.share.return_value.side_effect = evaluate
    monkeypatch.setattr(harness.runner_mod, 'AutoModel', lambda **kw: model)
    async def run():
        loop = asyncio.get_running_loop()
        async def ticker():
            before = loop.time()
            await asyncio.sleep(0.025)
            delays.append(loop.time() - before)
        tick = asyncio.create_task(ticker())
        await asyncio.sleep(0)
        await harness._collect(harness.runner_mod.run_subagent_stream(task['id'], task_spec=task))
        await tick
    asyncio.run(run())
    assert delays[0] < 0.10, f'25ms timer blocked for {delays[0]:.3f}s by completion review'


def test_review_completion_supports_stream_only_models(monkeypatch, tmp_path):
    task = setup_runner(monkeypatch, tmp_path)
    model = OnlineChatModule(source='qwen', model='qwq-plus', api_key='test-key', stream=True)
    monkeypatch.setattr(harness.runner_mod, 'AutoModel', lambda **kw: model)
    sent = []
    def post(url, **kwargs):
        sent.append(kwargs['json']['stream'])
        if sent[-1]:
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = 200
            verdict = json.dumps({'completed': True, 'requires_artifact': False,
                                  'artifact_keys': [], 'reason': 'Analysis delivered.'})
            response.iter_lines.return_value = iter([
                ('data: ' + json.dumps({'choices': [{'index': 0, 'delta': {'content': verdict}}]})).encode(),
                b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                b'data: [DONE]',
            ])
            return response
        response = requests.Response()
        response.status_code = 400
        response._content = json.dumps({'error': {'message': 'This model only supports stream mode',
                                                  'type': 'invalid_request_error',
                                                  'code': 'InvalidParameter'}}).encode()
        response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr('requests.post', post)
    raw = asyncio.run(harness._collect(harness.runner_mod.run_subagent_stream(task['id'], task_spec=task)))
    terminal = [e for e in harness._sse_to_events(raw) if e['type'] in {'done', 'error'}][-1]
    assert terminal['status'] == 'succeeded', f'payload stream={sent}, terminal={terminal}'


def test_review_resume_missing_file_is_not_delivery_evidence(monkeypatch, tmp_path):
    missing = tmp_path / 'deleted.pdf'
    assert not missing.exists()
    task = setup_runner(monkeypatch, tmp_path,
        artifacts=[{'slot': 'document', 'content_type': 'file', 'seq': 1,
                    'value': {'path': str(missing), 'filename': missing.name, 'size': 100}}],
        output_slots=['document'], params={'output_slot_types': {'document': 'file'}})
    task['objective'] = 'Generate and deliver the PDF document.'
    raw = asyncio.run(harness._collect(harness.runner_mod.run_subagent_stream(task['id'], task_spec=task, resume=True)))
    terminal = [e for e in harness._sse_to_events(raw) if e['type'] in {'done', 'error'}][-1]
    assert terminal['status'] == 'failed', f'Nonexistent file accepted: {terminal}'
