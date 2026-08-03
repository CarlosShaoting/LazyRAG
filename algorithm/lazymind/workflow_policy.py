"""Deterministic shadow evaluator for the shared Workflow decision policy."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    action: str
    tool: str | None
    target: str | None


def decide(projection: dict, profile: dict, user_intent: str = '') -> Decision:
    if projection.get('missing_inputs'):
        return Decision('request_input', None, None)
    if projection.get('status') == 'stopped' and user_intent == 'resume':
        return Decision('resume', 'resume_workflow', None)
    ready = projection.get('ready_steps', [])
    if not ready:
        return Decision('observe', 'get_workflow_state', None)
    tools = profile.get('advance_tools', ['advance_step'])
    tool = 'advance_step_and_handoff' if profile.get('handoff') else tools[0]
    return Decision('advance', tool, ready[0])


def shadow_trace(legacy: Decision, shared: Decision) -> dict:
    return {
        'legacy': legacy.__dict__,
        'shared': shared.__dict__,
        'equivalent': legacy == shared,
    }
