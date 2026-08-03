'''Language-neutral Workflow v1 fixture reader used by contract tests.'''

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_V1 = 'workflow.v1'


@dataclass(frozen=True)
class GoldenScenario:
    scenario: str
    projection: dict[str, Any]
    attempts: tuple[dict[str, Any], ...]
    artifacts: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]


def read_golden(path: str | Path) -> GoldenScenario:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('contract_version') != VERSION_V1:
        raise ValueError('unsupported Workflow contract version')
    projection = payload.get('projection', {})
    if not payload.get('scenario') or not projection.get('session_id'):
        raise ValueError('invalid Workflow fixture identity')
    cursors = [event.get('cursor') for event in payload.get('events', ())]
    if not cursors or cursors != sorted(set(cursors)):
        raise ValueError('Workflow event cursors must be strictly increasing')
    return GoldenScenario(
        scenario=payload['scenario'],
        projection=projection,
        attempts=tuple(payload.get('attempts', ())),
        artifacts=tuple(payload.get('artifacts', ())),
        events=tuple(payload['events']),
    )
