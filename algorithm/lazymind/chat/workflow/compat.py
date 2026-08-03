"""Explicit, observable adapters for the pre-Workflow package contract."""
from __future__ import annotations

import logging
import os
from pathlib import Path

LOG = logging.getLogger(__name__)
LEGACY_COMPAT_ENV = 'LAZYMIND_ENABLE_LEGACY_PLUGIN_COMPAT'
workflow_legacy_adapter_hits = 0


def _enabled() -> bool:
    return os.getenv(LEGACY_COMPAT_ENV, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _hit(surface: str) -> None:
    global workflow_legacy_adapter_hits
    workflow_legacy_adapter_hits += 1
    LOG.warning('workflow_legacy_adapter_hit surface=%s count=%d', surface, workflow_legacy_adapter_hits)


def configured_workflows_dir(default: str) -> Path:
    primary = os.getenv('LAZYMIND_WORKFLOWS_DIR', '').strip()
    if primary:
        return Path(primary)
    legacy = os.getenv('LAZYMIND_PLUGINS_DIR', '').strip()
    if legacy and _enabled():
        _hit('environment')
        return Path(legacy)
    return Path(default)


def manifest_path(workflow_dir: Path) -> Path | None:
    current = workflow_dir / 'workflow.yaml'
    if current.exists():
        return current
    legacy = workflow_dir / 'plugin.yaml'
    if legacy.exists() and _enabled():
        _hit('manifest')
        return legacy
    return None
