"""Tiny, deterministic local tools for the comprehensive Workflow smoke test."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus


def _root() -> Path:
    return Path(tempfile.mkdtemp(prefix='workflow-smoke-')).resolve()


def build_test_metadata(summary: str) -> Dict[str, Any]:
    return {'smoke_test': True, 'summary': str(summary), 'schema': 'test.v1'}


def create_typed_fixtures(summary: str) -> Dict[str, str]:
    root = _root()
    text_path = root / 'attachment.txt'
    text_path.write_text(f'Workflow smoke test\n{summary}\n', encoding='utf-8')
    label = quote_plus(f'Workflow Smoke Test | {str(summary)[:48]}')
    image_url = f'https://placehold.co/640x360/2563eb/ffffff.png?text={label}'
    return {'text_path': str(text_path), 'image_url': image_url}


def create_rewrite_fixture(summary: str) -> str:
    path = _root() / 'rewritten.txt'
    path.write_text(f'revision-1\n{summary}\n', encoding='utf-8')
    return str(path)


def rewrite_fixture(path: str, marker: str) -> str:
    target = Path(path).resolve()
    previous = target.read_text(encoding='utf-8')
    target.write_text(f'{previous}{marker}\n', encoding='utf-8')
    return str(target)


def create_list_fixtures() -> List[str]:
    root = _root()
    paths = []
    for index in (1, 2):
        path = root / f'list-{index}.txt'
        path.write_text(f'list-item-{index}\n', encoding='utf-8')
        paths.append(str(path))
    return paths


def verify_fixtures(text_path: str, image_url: str, rewritten_path: str,
                    list_paths: List[str]) -> Dict[str, str]:
    text = Path(text_path)
    rewritten = Path(rewritten_path)
    listed = [Path(path) for path in list_paths]
    checks = {
        'text': text.is_file() and 'Workflow smoke test' in text.read_text(encoding='utf-8'),
        'image': image_url.startswith('https://placehold.co/640x360/'),
        'rewrite': rewritten.is_file() and 'revision-2' in rewritten.read_text(encoding='utf-8'),
        'list': len(listed) == 2 and all(path.is_file() for path in listed),
    }
    if not all(checks.values()):
        raise ValueError(f'workflow smoke verification failed: {checks}')
    report = _root() / 'verification.json'
    report.write_text(json.dumps(checks, indent=2, sort_keys=True), encoding='utf-8')
    return {'status': 'Workflow smoke test passed', 'report_path': str(report)}


__all__ = [
    'build_test_metadata',
    'create_typed_fixtures',
    'create_rewrite_fixture',
    'rewrite_fixture',
    'create_list_fixtures',
    'verify_fixtures',
]
