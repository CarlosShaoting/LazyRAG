---
name: workflow-agent-kit
description: Discover, prepare, execute, review, recover, and author versioned Workflows through the neutral Workflow v1 tools.
version: workflow.v1
---

# Workflow Agent Kit

Read the active Host profile before choosing tools. Treat the Runtime projection
as authoritative. Discover a Workflow, run `prepare_workflow`, resolve missing
inputs, and only then call `start_workflow`. Select from `ready_steps`; parallel
steps may execute concurrently when the profile permits it.

Use `advance_step` for terminal-wait execution. Use
`advance_step_and_handoff` only when the active profile permits handoff and a
durable Supervisor owns the Attempt. Never choose retry versus rewind: name the
target step and let Runtime return `resolved_operation`.

Review required outputs against acceptance criteria. Preserve immutable
Artifact revisions. On failure, target the failed/interrupted step; on a change
to a previously succeeded step, target that step and allow Runtime to stale its
downstream lineage. Stop and resume through Workflow tools, never by editing
projection state.

For authoring, generate a draft and use deterministic diagnostics until it can
be published. Authoring tools never invoke a model.

See `references/decision-policy.md` and the selected file under `profiles/`.

