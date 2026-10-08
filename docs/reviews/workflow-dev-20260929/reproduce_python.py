"""Review regression probes. Run with pytest; failures describe expected behavior.

REVIEW_ROOT may point at another checkout. No model/network calls are made.
"""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(os.environ.get('REVIEW_ROOT', Path(__file__).resolve().parents[3]))


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def writer():
    return load('workflows/product_solution_delivery/scripts/writer_bridge.py', 'review_writer')


def test_product_presentation_preserves_code_urls_and_evidence():
    source = ('# API contract\n\n```json\n{"status":"accepted","value":null}\n```\n\n'
              '[接口文档](https://example.com/api/accepted)\n\n'
              '当前运行已核验 WEB-001，结论有公开资料支持。')
    rendered = writer()._present_reader_facing_markdown('handoff', source)
    assert '"value":null' in rendered, rendered
    assert 'https://example.com/api/accepted' in rendered, rendered
    assert '本轮未使用外部资料' not in rendered, rendered


def test_product_flowchart_keeps_branch_labels():
    source = 'flowchart TD\nA{已付款?} -->|是| B[发货]\nA -->|否| C[取消]'
    rendered = writer()._render_flow(source)
    assert '>是<' in rendered and '>否<' in rendered, rendered


def test_uploaded_edit_validation_publishes_authoritative_source(monkeypatch, tmp_path):
    from PIL import Image
    from lazymind.chat.engine.subagent import tools as runtime_tools
    module = load('workflows/image-workflow-v2/scripts/tools.py', 'review_image_tools')
    path = tmp_path / 'source.png'
    Image.new('RGB', (800, 600), 'white').save(path)
    saved = []
    monkeypatch.setattr(runtime_tools, '_save_artifact', lambda *a, **kw: saved.append((a, kw)))
    legacy = module._legacy_image_tools()
    # Isolate the claimed publication side effect from URL/path resolution.
    monkeypatch.setattr(legacy, '_resolve_local_file', lambda value: str(path))
    module.validate_image_ref('source_image')
    state = yaml.safe_load((ROOT / 'workflows/image-workflow-v2/scenario/state.yml').read_text())
    required = {item['material'] for item in state['steps']['edit_prepare']['outputs'] if item.get('required')}
    # The uploaded-image prompt permits save_artifacts(edit_contract) only.
    published = {'edit_contract'} | {args[0] if args else kw.get('key') for args, kw in saved}
    assert required <= published, f'missing required output(s): {required - published}'


def test_ordinary_search_request_collects_reference_material(monkeypatch):
    from lazymind.chat.engine.subagent import context, tools as runtime_tools
    module = load('workflows/image-workflow-v2/scripts/tools.py', 'review_image_search')
    ctx = SimpleNamespace(params={'user_input': '搜索上海外滩真实照片作为参考，制作16:9旅游海报'})
    monkeypatch.setattr(context, 'require_context', lambda: ctx)
    saved = []
    monkeypatch.setattr(runtime_tools, '_save_artifact', lambda key, value, **kw: saved.append((key, value)) or {'status': 'ok'})
    route = module.classify_image_request()['route_plan']
    assert route['route'] == 'ordinary' and route['needs_external_material']
    module.prepare_ordinary_request()
    assert 'material_images' in {key for key, value in saved}, saved


def test_image_generation_keeps_ratio_after_approval_continue(monkeypatch):
    from lazymind.chat.engine.subagent import context
    module = load('workflows/image-workflow-v2/scripts/baoyu.py', 'review_image_ratio')
    # workflow_manager forwards the current approval text for non-PPT workflows;
    # Core only falls back to launch intent when the step input is empty.
    ctx = SimpleNamespace(params={'user_input': '继续'})
    monkeypatch.setattr(context, 'require_context', lambda: ctx)
    monkeypatch.setattr(module, '_artifact_text', lambda key: '生成16:9横版海报，主题为城市旅行')
    monkeypatch.setattr(module, '_artifact_image_refs', lambda *keys: [])
    captured = {}
    monkeypatch.setattr(module, 'baoyu_image_generator', lambda prompt, **kw: captured.update(kw) or {})
    monkeypatch.setattr(module, '_publish_generated_images', lambda *args: {})
    module.generate_ordinary_image()
    assert captured['aspect_ratio'] == '16:9', captured


def test_uploaded_wide_image_keeps_source_aspect_ratio(tmp_path):
    from PIL import Image
    module = load('workflows/image-workflow-v2/scripts/baoyu.py', 'review_image_size')
    path = tmp_path / 'banner.png'
    Image.new('RGB', (4000, 500), 'white').save(path)
    width, height = map(int, module._size_for_source_image(str(path)).split('x'))
    assert abs(width / height - 8) < 0.05, f'8:1 source silently becomes {width}x{height} ({width / height:.2f}:1)'
