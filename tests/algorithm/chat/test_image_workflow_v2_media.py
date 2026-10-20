from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from lazyllm.tools.agent import ToolExecutionError

MODULE_PATH = Path(__file__).resolve().parents[3] / 'workflows' / 'image-workflow-v2' / 'scripts' / 'media.py'
SPEC = importlib.util.spec_from_file_location('image_workflow_v2_media', MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_supported_aspect_ratios_use_provider_neutral_sizes():
    assert module._size_for_aspect_ratio('1:1') == '1024x1024'
    assert module._size_for_aspect_ratio('16:9') == '1344x768'
    assert module._size_for_aspect_ratio('9:16') == '768x1344'
    with pytest.raises(ToolExecutionError, match='Unsupported aspect_ratio'):
        module._size_for_aspect_ratio('5:4')


def test_editor_uses_global_role_and_preserves_source_ratio_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}

    def fake_editor(prompt, urls, *, image_size, batch_size):
        captured.update(
            prompt=prompt, urls=urls, image_size=image_size, batch_size=batch_size,
        )
        return {'local_path': 'edited.png'}

    monkeypatch.setattr(module, 'image_editor', fake_editor)

    result = module._edit_with_configured_model('Change only the hat.', ['source.png'])

    assert result['local_path'] == 'edited.png'
    assert result['model_role'] == 'image_editor'
    assert captured == {
        'prompt': 'Change only the hat.\nPreserve the source image aspect ratio.',
        'urls': ['source.png'],
        'image_size': '1024x1024',
        'batch_size': 1,
    }


def test_editor_requires_one_authoritative_source():
    with pytest.raises(ToolExecutionError, match='exactly one authoritative'):
        module._edit_with_configured_model('edit', [])
    with pytest.raises(ToolExecutionError, match='exactly one authoritative'):
        module._edit_with_configured_model('edit', ['a.png', 'b.png'])


def test_plain_generation_uses_global_generator_without_provider_env(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}

    def fake_generator(prompt, *, image_size, batch_size):
        captured.update(prompt=prompt, image_size=image_size, batch_size=batch_size)
        return {'local_path': 'generated.png'}

    monkeypatch.setattr(module, 'image_generator', fake_generator)

    result = module._generate_with_configured_model(
        'A fox', aspect_ratio='16:9', urls=None,
    )

    assert result['model_role'] == 'image_generator'
    assert captured == {
        'prompt': 'A fox\nRequested output aspect ratio: 16:9.',
        'image_size': '1344x768',
        'batch_size': 1,
    }


def test_reference_generation_uses_global_editor_role(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_editor(prompt, urls, *, image_size, batch_size):
        captured.update(
            prompt=prompt, urls=urls, image_size=image_size, batch_size=batch_size,
        )
        return {'local_path': 'generated.png'}

    monkeypatch.setattr(module, 'image_editor', fake_editor)

    result = module._generate_with_configured_model(
        'Restyle this image', aspect_ratio='1:1', urls=['reference.png'],
    )

    assert result['model_role'] == 'image_editor'
    assert captured['urls'] == ['reference.png']


def test_missing_global_media_role_is_a_clear_workflow_error(monkeypatch: pytest.MonkeyPatch):
    marker = 'MEDIA_CAPABILITY_DEPENDENCY_MISSING {"required":["image_generator"]}'
    monkeypatch.setattr(module, 'image_generator', lambda *args, **kwargs: {
        'status': 'blocked',
        'message': 'No configured image generator.',
        '_agent_control': {'final_text': marker},
    })

    with pytest.raises(ToolExecutionError, match='MEDIA_CAPABILITY_DEPENDENCY_MISSING'):
        module._generate_with_configured_model('A fox', aspect_ratio='1:1')


@pytest.mark.parametrize(
    ('launch_request', 'expected'),
    [
        ('生成 16:9 横版插画', '16:9'),
        ('make a portrait poster', '9:16'),
        ('生成横向风景', '16:9'),
        ('正方形头像', '1:1'),
        ('no ratio given', '1:1'),
    ],
)
def test_requested_aspect_ratio_is_deterministic(launch_request: str, expected: str):
    assert module._requested_aspect_ratio(launch_request) == expected


def test_generate_ordinary_image_only_publishes_real_provider_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    generated = tmp_path / 'generated.png'
    generated.write_bytes(b'png')
    saved = []
    monkeypatch.setattr(module, '_artifact_text', lambda key: 'A spring valley')
    monkeypatch.setattr(module, '_artifact_image_refs', lambda *keys: [])
    monkeypatch.setattr(module, '_immutable_request', lambda: '16:9 横版')
    monkeypatch.setattr(
        module,
        '_generate_with_configured_model',
        lambda prompt, aspect_ratio, urls: {
            'images': [{'local_path': str(generated), 'image_url': '/static-files/x'}],
            'model_role': 'image_generator',
            'image_size': '1344x768',
        },
    )
    fake_tools = SimpleNamespace(
        _save_artifact=lambda *args, **kwargs: saved.append((args, kwargs)) or {'status': 'ok'}
    )
    monkeypatch.setitem(__import__('sys').modules, 'lazymind.chat.engine.subagent.tools', fake_tools)

    result = module.generate_ordinary_image()

    assert result['saved_count'] == 1
    assert saved[0][0] == ('ordinary_output', {'path': str(generated)})
    assert saved[0][1]['internal_publish'] is True
    assert saved[0][1]['publisher_list_index'] == 0


def test_generate_ordinary_image_cannot_publish_after_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(module, '_artifact_text', lambda key: 'prompt')
    monkeypatch.setattr(module, '_artifact_image_refs', lambda *keys: [])
    monkeypatch.setattr(module, '_immutable_request', lambda: '1:1')
    monkeypatch.setattr(
        module,
        '_generate_with_configured_model',
        lambda *args, **kwargs: (_ for _ in ()).throw(ToolExecutionError('provider failed')),
    )

    with pytest.raises(ToolExecutionError, match='provider failed'):
        module.generate_ordinary_image()


def test_generate_edit_candidate_uses_contract_and_real_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    generated = tmp_path / 'edited.png'
    generated.write_bytes(b'png')
    captured = {}
    saved = []
    monkeypatch.setattr(module, '_artifact_json', lambda key: {
        'requested_edit': 'Make the hat blue',
        'edit_scope': 'Hat only',
        'preserve': 'Identity and background',
        'do_not': 'Change the face',
    })
    monkeypatch.setattr(
        module,
        '_artifact_image_refs',
        lambda *keys: ['C:/source.png'],
    )
    monkeypatch.setattr(module, '_immutable_request', lambda: '把帽子改成蓝色')

    def fake_editor(prompt, urls, aspect_ratio):
        captured.update(prompt=prompt, urls=urls, aspect_ratio=aspect_ratio)
        return {
            'images': [{'local_path': str(generated)}],
            'model_role': 'image_editor',
            'image_size': '1024x1024',
        }

    monkeypatch.setattr(module, '_edit_with_configured_model', fake_editor)
    fake_tools = SimpleNamespace(
        _save_artifact=lambda *args, **kwargs: saved.append((args, kwargs)) or {'status': 'ok'}
    )
    monkeypatch.setitem(__import__('sys').modules, 'lazymind.chat.engine.subagent.tools', fake_tools)

    result = module.generate_edit_candidate()

    assert result['saved_count'] == 1
    assert captured['urls'] == ['C:/source.png']
    assert captured['aspect_ratio'] is None
    assert captured['prompt'].splitlines() == [
        'Requested edit: Make the hat blue',
        'Edit scope: Hat only',
        'Preserve: Identity and background',
        'Do not: Change the face',
    ]
    assert saved[0][0] == ('edit_candidate', {'path': str(generated)})
    assert saved[0][1]['internal_publish'] is True
    assert 'publisher_list_index' not in saved[0][1]
