"""Workflow public domain types; legacy persistence names never cross this module."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowSessionRef:
    session_id: str
    workflow_id: str
    origin_host: str = 'lazymind'
    origin_ref: str = ''


def public_route(workflow_names_enabled: bool = True) -> str:
    return '/api/workflows' if workflow_names_enabled else '/api/workflows'
