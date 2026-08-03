"""Compatibility exports for the legacy direct persistence reader.

Workflow-aware callers should use ``WorkflowClient``.  The implementation is
isolated under ``workflow.persistence_compat`` so Runtime table access cannot
spread back into algorithm/chat business modules.
"""
from lazymind.chat.workflow.persistence_compat import (
    SubAgentDB as _SubAgentDB,
    TaskQueryDB as _TaskQueryDB,
    record_workflow_persistence_compat_call,
)


class SubAgentDB(_SubAgentDB):
    def __init__(self, *args, **kwargs):
        record_workflow_persistence_compat_call('SubAgentDB')
        super().__init__(*args, **kwargs)


class TaskQueryDB(_TaskQueryDB):
    def __init__(self, *args, **kwargs):
        record_workflow_persistence_compat_call('TaskQueryDB')
        super().__init__(*args, **kwargs)


__all__ = ['SubAgentDB', 'TaskQueryDB']
