"""Workflow loader — discovers and validates workflow packages under the workflows directory.

Each workflow lives at <workflows-dir>/<workflow-id>/ and must contain:
  - workflow.yaml          (required) — registration metadata
  - scenario/scenario.md (required) — ChatAgent intent-recognition guide
  - scenario/state.yml   (required) — state machine + step execution spec
  - scenario/driver.md   (optional, required for auto mode) — DriverAgent prompt
  - scripts/             (optional) — workflow-local tool implementations

The workflows directory is configured via lazymind.config['workflows_dir'] (env: LAZYMIND_WORKFLOWS_DIR),
falling back to workflow/workflows/ relative to this file for local development.

Loaded workflows are cached at import time (startup). Hot-reload is not supported.
"""
from __future__ import annotations

import importlib.util
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import threading
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from lazymind.config import config as _cfg
from lazymind.chat.workflow.compat import configured_workflows_dir, manifest_path

LOG = logging.getLogger(__name__)

# Base directory for all workflow packages, configured via lazymind config.
_WORKFLOWS_DIR = configured_workflows_dir(_cfg['workflows_dir'])

# Registry: {workflow_id: WorkflowSpec}
_registry: Dict[str, 'WorkflowSpec'] = {}
_runtime_registry: Dict[tuple[str, str, str], 'WorkflowSpec'] = {}
_load_lock = threading.Lock()
_loaded = False


def resolve_remote_workflow(entry: Dict[str, Any]) -> tuple[str, 'WorkflowSpec']:
    """Materialize and cache one immutable RemoteFS workflow revision."""
    workflow_ref = str(entry.get('workflow_ref') or '').strip()
    revision_id = str(entry.get('revision_id') or '').strip()
    tree_hash = str(entry.get('tree_hash') or '').removeprefix('sha256:').strip()
    remote_root = str(entry.get('remote_root') or '').strip()
    if not all((workflow_ref, revision_id, tree_hash, remote_root)):
        raise ValueError('workflow catalog entry is missing runtime identity fields')
    key = (workflow_ref, revision_id, tree_hash)
    if key in _runtime_registry:
        spec = _runtime_registry[key]
        return spec.workflow_id, spec
    runtime_id = f'user_{hashlib.sha256(workflow_ref.encode()).hexdigest()[:12]}_{entry.get("workflow_id", "workflow")}'
    cache_root = Path(os.getenv('LAZYMIND_WORKFLOW_RUNTIME_CACHE', tempfile.gettempdir())) / 'lazymind-workflow-runtime'
    cache_root.mkdir(parents=True, exist_ok=True)
    final_dir = cache_root / hashlib.sha256(workflow_ref.encode()).hexdigest()[:16] / revision_id
    if not final_dir.exists():
        tmp_dir = Path(tempfile.mkdtemp(prefix='workflow-', dir=str(cache_root)))
        try:
            from lazymind.common.integrations.remote_fs import RemoteFS
            RemoteFS().materialize_dir(remote_root, str(tmp_dir), revision_id=revision_id)
            rows = []
            for file_path in sorted(p for p in tmp_dir.rglob('*') if p.is_file()):
                rel = file_path.relative_to(tmp_dir).as_posix()
                rows.append(f'{rel}\0file\0{hashlib.sha256(file_path.read_bytes()).hexdigest()}')
            actual = hashlib.sha256('\n'.join(rows).encode()).hexdigest()
            if actual != tree_hash:
                raise ValueError(f'workflow tree hash mismatch: expected {tree_hash}, got {actual}')
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                tmp_dir.rename(final_dir)
            except FileExistsError:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
    spec = WorkflowSpec(workflow_id=runtime_id, workflow_dir=final_dir)
    _runtime_registry[key] = spec
    _registry[runtime_id] = spec
    return runtime_id, spec


def _normalise_steps(raw_steps: Any) -> Dict[str, Dict[str, Any]]:
    """Return state.yml steps keyed by id for both supported YAML shapes.

    Older/built-in workflows use a mapping (``steps: {step_id: {...}}``), while
    the visual editor serialises a list (``steps: [{id: step_id, ...}]``).
    Runtime code consumes one canonical mapping so metadata such as ``mode`` is
    never lost merely because the workflow was saved by the editor.
    """
    def _normalise_config(step_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        normalised = {'id': step_id, **config}
        for field in ('inputs', 'outputs'):
            refs = normalised.get(field)
            if not isinstance(refs, list):
                continue
            normalised_refs: List[Dict[str, Any]] = []
            for ref in refs:
                if isinstance(ref, str) and ref.strip():
                    normalised_refs.append({'slot': ref.strip()})
                elif isinstance(ref, dict):
                    slot = str(ref.get('slot') or ref.get('artifact_id') or '').strip()
                    if slot:
                        normalised_refs.append({'slot': slot, **ref})
            normalised[field] = normalised_refs
        return normalised

    if isinstance(raw_steps, dict):
        result: Dict[str, Dict[str, Any]] = {}
        for step_id, config in raw_steps.items():
            if not isinstance(step_id, str) or not isinstance(config, dict):
                continue
            result[step_id] = _normalise_config(step_id, config)
        return result
    if isinstance(raw_steps, list):
        result = {}
        for config in raw_steps:
            if not isinstance(config, dict):
                continue
            step_id = str(config.get('id') or '').strip()
            if step_id:
                result[step_id] = _normalise_config(step_id, config)
        return result
    return {}


class WorkflowSpec:
    """Holds all parsed artifacts for one workflow."""

    def __init__(self, workflow_id: str, workflow_dir: Path) -> None:
        self.workflow_id = workflow_id
        self.workflow_dir = workflow_dir

        # Load workflow.yaml
        workflow_yaml_path = manifest_path(workflow_dir)
        if workflow_yaml_path is None:
            raise FileNotFoundError(f'workflow.yaml missing in {workflow_dir}')
        with workflow_yaml_path.open('r', encoding='utf-8') as f:
            self.workflow_yaml_raw: str = f.read()
        self.yaml: Dict[str, Any] = yaml.safe_load(self.workflow_yaml_raw) or {}

        # Load scenario files
        scenario_dir = workflow_dir / 'scenario'
        self.scenario_md: str = self._read_text(scenario_dir / 'scenario.md')
        state_path = scenario_dir / 'state.yml'
        with state_path.open('r', encoding='utf-8') as f:
            state_text = f.read()
        self.state_yaml_raw: str = state_text
        self.state: Dict[str, Any] = yaml.safe_load(state_text) or {}
        self.driver_md: Optional[str] = self._read_text(scenario_dir / 'driver.md', optional=True)

        # Normalise editor (list) and legacy (mapping) step shapes before any
        # runtime consumer reads step metadata.
        self._steps: Dict[str, Dict[str, Any]] = _normalise_steps(self.state.get('steps', {}))

        # Load workflow-local script tools declared in workflow.yaml tool_scripts.
        self._script_tools: Dict[str, Callable] = self._load_script_tools()

        # Validate: auto-capable steps need driver.md
        self._validate()

    def _load_script_tools(self) -> Dict[str, Callable]:
        """Dynamically import functions declared in workflow.yaml tool_scripts.

        Each entry under tool_scripts must have:
          - path: relative path from the workflow directory to the Python file
          - functions: list of function names to import from that file

        Returns a dict mapping function_name -> callable.
        """
        result: Dict[str, Callable] = {}
        entries: List[Dict[str, Any]] = self.yaml.get('tool_scripts', []) or []
        for entry in entries:
            rel_path = entry.get('path', '')
            func_names: List[str] = entry.get('functions', []) or []
            if not rel_path or not func_names:
                continue
            script_path = self.workflow_dir / rel_path
            if not script_path.exists():
                LOG.warning(
                    '[WorkflowLoader] workflow=%s tool_script not found: %s',
                    self.workflow_id, script_path,
                )
                continue
            # Use a unique module name to avoid collisions across workflows.
            module_name = f'_workflow_script_{self.workflow_id}_{script_path.stem}'
            if module_name in sys.modules:
                module: types.ModuleType = sys.modules[module_name]
            else:
                spec = importlib.util.spec_from_file_location(module_name, script_path)
                if spec is None or spec.loader is None:
                    LOG.warning(
                        '[WorkflowLoader] workflow=%s cannot load script: %s',
                        self.workflow_id, script_path,
                    )
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                except Exception as exc:
                    LOG.error(
                        '[WorkflowLoader] workflow=%s script exec failed (%s): %s',
                        self.workflow_id, script_path, exc,
                    )
                    del sys.modules[module_name]
                    continue
            for fn_name in func_names:
                fn = getattr(module, fn_name, None)
                if fn is None or not callable(fn):
                    LOG.warning(
                        '[WorkflowLoader] workflow=%s script %s has no callable %r',
                        self.workflow_id, rel_path, fn_name,
                    )
                    continue
                result[fn_name] = fn
                LOG.info(
                    '[WorkflowLoader] workflow=%s registered script tool: %s',
                    self.workflow_id, fn_name,
                )
        return result

    def get_script_tool(self, name: str) -> Optional[Callable]:
        """Return a script tool callable by name, or None if not found."""
        return self._script_tools.get(name)

    def list_script_tool_names(self) -> List[str]:
        """Return the names of all registered script tools for this workflow."""
        return list(self._script_tools.keys())

    @staticmethod
    def _read_text(path: Path, optional: bool = False) -> Optional[str]:
        if not path.exists():
            if optional:
                return None
            raise FileNotFoundError(f'Required file missing: {path}')
        return path.read_text(encoding='utf-8')

    def _validate(self) -> None:
        # workflow.yaml must declare 'id' and 'steps'
        if not self.yaml.get('id'):
            raise ValueError(f'workflow.yaml missing id in {self.workflow_dir}')
        if not self.yaml.get('steps'):
            raise ValueError(f'workflow.yaml missing steps in {self.workflow_dir}')

        required_framework_tools = self.yaml.get('required_framework_tools') or []
        if required_framework_tools:
            from lazymind.chat.service.component.tool_registry import DEFAULT_TOOLS, tool_is_active
            by_name = {cfg.name: cfg for cfg in DEFAULT_TOOLS}
            unavailable = [
                name for name in required_framework_tools
                if name not in by_name or not tool_is_active(by_name[name])
            ]
            if unavailable:
                raise ValueError(f'workflow requires unavailable framework tools: {unavailable}')

        # If driver.md is missing, we emit a warning but don't hard-fail load.
        # auto mode will be silently degraded to manual at runtime if driver.md absent.
        if not self.driver_md:
            LOG.warning(
                '[WorkflowLoader] workflow=%s has no driver.md; auto mode will be disabled',
                self.workflow_id,
            )

    def get_step_config(self, step_id: str) -> Dict[str, Any]:
        return dict(self._steps.get(step_id, {}))

    def get_step_mode(self, step_id: str) -> str:
        """Return the step's default approval mode; legacy omissions are human."""
        return 'auto' if self._steps.get(step_id, {}).get('mode') == 'auto' else 'human'

    def get_slot_def(self, slot_id: str) -> Optional[Dict[str, Any]]:
        """Find a slot in either the canonical list or UI tab declarations."""
        slots = list(self.yaml.get('slots', []) or [])
        for tab in (self.yaml.get('ui', {}) or {}).get('tabs', []) or []:
            slots.extend(tab.get('slots', []) or [])
        for slot in slots:
            if slot.get('id') == slot_id:
                return dict(slot)
        return None

    def get_slot(self, slot: str) -> Optional[Dict[str, Any]]:
        """Return the slot definition (id, type, cardinality, ordered …) for a slot id."""
        for s in self.yaml.get('slots', []):
            if s.get('id') == slot:
                return dict(s)
        return None

    def get_slot_for_artifact(self, artifact_id: str) -> Optional[str]:
        """Return the UI slot receiving an artifact produced by any step."""
        for step in self._steps.values():
            for output in step.get('outputs', []) or []:
                if output.get('artifact_id') == artifact_id:
                    return output.get('slot_id') or output.get('slot')
        return None

    def get_i18n_label(self, lang: str, key_path: str, fallback: str = '') -> str:
        """Return a translated label from workflow.yaml i18n section.

        key_path uses dot-notation: e.g. 'tabs.materials', 'slots.material_images',
        'steps.generate_image'.

        Args:
            lang: BCP-47 language tag, e.g. 'zh-CN'.
            key_path: Dot-separated path into the i18n subtree.
            fallback: Value to return when the key is missing.
        """
        i18n = self.yaml.get('i18n') or {}
        node: Any = i18n.get(lang) or i18n.get(lang.split('-')[0]) or {}
        for part in key_path.split('.'):
            if not isinstance(node, dict):
                return fallback
            node = node.get(part)
            if node is None:
                return fallback
        if isinstance(node, dict):
            return str(node.get('label', fallback))
        return str(node) if node else fallback


def load_all() -> None:
    """Discover and load all workflows from the workflows directory on demand."""
    global _registry, _loaded
    with _load_lock:
        _registry = {}
        if not _WORKFLOWS_DIR.is_dir():
            LOG.warning('[WorkflowLoader] workflows directory not found: %s', _WORKFLOWS_DIR)
            _loaded = True
            return

        for entry in sorted(_WORKFLOWS_DIR.iterdir()):
            if not entry.is_dir():
                continue
            workflow_yaml = manifest_path(entry)
            if workflow_yaml is None:
                continue
            workflow_id = entry.name
            try:
                spec = WorkflowSpec(workflow_id=workflow_id, workflow_dir=entry)
                _registry[workflow_id] = spec
                LOG.info('[WorkflowLoader] loaded workflow: %s', workflow_id)
            except Exception as exc:
                LOG.error('[WorkflowLoader] failed to load workflow %s: %s', workflow_id, exc)
        _loaded = True


def ensure_loaded() -> None:
    if not _loaded:
        load_all()


def get_workflow(workflow_id: str) -> Optional[WorkflowSpec]:
    ensure_loaded()
    return _registry.get(workflow_id)


def list_workflows() -> List[Dict[str, Any]]:
    """Return summary info for all loaded workflows."""
    ensure_loaded()
    out = []
    for spec in _registry.values():
        steps = [
            {'id': s.get('id', ''), 'label': s.get('label', '')}
            for s in spec.yaml.get('steps', [])
        ]
        out.append({
            'id': spec.workflow_id,
            'name': spec.yaml.get('name', spec.workflow_id),
            'description': spec.yaml.get('description', ''),
            'steps': steps,
            'ui': spec.yaml.get('ui', {}),
            'i18n': spec.yaml.get('i18n', {}),
        })
    return out


def get_workflow_with_i18n(workflow_id: str, lang: str = '') -> Optional[Dict[str, Any]]:
    """Return full workflow spec with labels resolved for lang.

    When lang is supplied (e.g. 'zh-CN'), labels for tabs and slots are
    overwritten with the i18n values if available.  Falls back to the
    static labels in workflow.yaml when a translation is absent.
    """
    spec = get_workflow(workflow_id)
    if not spec:
        return None

    import copy

    # Build a slot lookup from the top-level slots[] definition.
    top_slots: Dict[str, Dict[str, Any]] = {
        s['id']: s for s in spec.yaml.get('slots', []) if s.get('id')
    }

    # Expand ui.tabs[].slots[] from id-only references to full slot defs.
    # Each tab slot entry is merged: top-level slot attrs first, then any
    # tab-local overrides (currently only 'id' is present, but kept for
    # forward-compatibility).
    raw_ui = copy.deepcopy(spec.yaml.get('ui', {}))
    for tab in raw_ui.get('tabs', []):
        expanded = []
        for slot_ref in tab.get('slots', []):
            slot_id = slot_ref.get('id', '')
            base = dict(top_slots.get(slot_id, {}))
            base.update(slot_ref)  # tab-local keys win if ever added
            expanded.append(base)
        tab['slots'] = expanded

    raw: Dict[str, Any] = {
        'id': spec.workflow_id,
        'name': spec.yaml.get('name', spec.workflow_id),
        'description': spec.yaml.get('description', ''),
        'when_to_use': spec.yaml.get('when_to_use', ''),
        'steps': list(spec.yaml.get('steps', [])),
        'ui': raw_ui,
        'i18n': spec.yaml.get('i18n', {}),
    }

    if not lang:
        return raw

    # Apply i18n overrides to a deep copy so the registry cache is untouched.
    raw = copy.deepcopy(raw)

    name_i18n = spec.get_i18n_label(lang, 'name', '')
    if name_i18n:
        raw['name'] = name_i18n

    for step in raw.get('steps', []):
        step_id = step.get('id', '')
        label_i18n = spec.get_i18n_label(lang, f'steps.{step_id}', '')
        if label_i18n:
            step['label'] = label_i18n

    ui = raw.get('ui') or {}
    for tab in ui.get('tabs', []):
        tab_id = tab.get('id', '')
        label_i18n = spec.get_i18n_label(lang, f'tabs.{tab_id}', '')
        if label_i18n:
            tab['label'] = label_i18n
        for slot in tab.get('slots', []):
            slot_id = slot.get('id', '')
            label_i18n = spec.get_i18n_label(lang, f'slots.{slot_id}', '')
            if label_i18n:
                slot['label'] = label_i18n

    return raw


def get_step_config(workflow_id: str, step_id: str) -> Dict[str, Any]:
    spec = get_workflow(workflow_id)
    return spec.get_step_config(step_id) if spec else {}


def get_step_mode(workflow_id: str, step_id: str) -> str:
    """Return ``auto`` or ``human`` for the step's default approval policy."""
    spec = get_workflow(workflow_id)
    return spec.get_step_mode(step_id) if spec else 'human'


def get_scenario(workflow_id: str) -> str:
    spec = get_workflow(workflow_id)
    return spec.scenario_md if spec else ''


def get_workflow_intro(workflow_id: str) -> str:
    """Return a short intro (id + description + when_to_use) for cold-start injection.

    Only the trigger-relevant fields are included so the full scenario.md is not
    leaked into the system prompt before the workflow is activated.
    """
    spec = get_workflow(workflow_id)
    if not spec:
        return ''
    workflow_id_val = spec.workflow_id
    workflow_name = str(spec.yaml.get('name') or workflow_id_val).strip()
    description = (spec.yaml.get('description') or '').strip()
    when_to_use = (spec.yaml.get('when_to_use') or '').strip()
    lines = [f'## Workflow: {workflow_name} (id: {workflow_id_val})']
    if description:
        lines.append(description)
    if when_to_use:
        lines.append(f'When to use: {when_to_use}')
    return '\n'.join(lines)


def get_driver(workflow_id: str) -> Optional[str]:
    spec = get_workflow(workflow_id)
    return spec.driver_md if spec else None


def get_workflow_yaml(workflow_id: str) -> Dict[str, Any]:
    spec = get_workflow(workflow_id)
    return spec.yaml if spec else {}


def get_script_tool(workflow_id: str, tool_name: str) -> Optional[Callable]:
    """Return a workflow script tool callable by name, or None."""
    spec = get_workflow(workflow_id)
    return spec.get_script_tool(tool_name) if spec else None


def list_script_tool_names(workflow_id: str) -> List[str]:
    """Return names of all script tools registered for a workflow."""
    spec = get_workflow(workflow_id)
    return spec.list_script_tool_names() if spec else []
