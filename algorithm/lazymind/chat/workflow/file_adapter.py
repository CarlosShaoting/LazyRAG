"""LazyMind Host Attachment to stable Workflow Input Resource adapter."""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .client import CONTRACT_VERSION, WorkflowClientError


@dataclass(frozen=True)
class InputResource:
    resource_id: str
    name: str
    mime_type: str
    size: int
    content_hash: str
    revision: int


class LazyMindHostFileAdapter:
    def __init__(self, base_url: str, user_id: str, *, transport: Any):
        self.base_url = base_url.rstrip('/')
        self.user_id = user_id
        self.transport = transport

    def import_attachment(self, path: str) -> InputResource:
        source = Path(path)
        content = source.read_bytes()
        digest = 'sha256:' + hashlib.sha256(content).hexdigest()
        payload = {
            'contract_version': CONTRACT_VERSION,
            'name': source.name,
            'mime_type': mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
            'size': len(content),
            'content_hash': digest,
            'content_base64': base64.b64encode(content).decode('ascii'),
        }
        response = self.transport.post(
            self.base_url + '/workflow-input-resources', json=payload,
            headers={'X-User-Id': self.user_id, 'Workflow-Contract-Version': CONTRACT_VERSION},
            timeout=30.0,
        )
        body: Dict[str, Any] = response.json()
        if response.status_code >= 400 or body.get('ok') is False:
            error = body.get('error') or {}
            raise WorkflowClientError(str(error.get('code') or 'INPUT_IMPORT_FAILED'),
                                      str(error.get('message') or 'input import failed'))
        result = body.get('result') or body.get('data') or body
        # The Host-private path and transport capability are deliberately discarded here.
        return InputResource(
            resource_id=str(result['resource_id']), name=str(result['name']),
            mime_type=str(result['mime_type']), size=int(result['size']),
            content_hash=str(result['content_hash']), revision=int(result['revision']),
        )
