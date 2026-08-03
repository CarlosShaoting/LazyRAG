# Phase One Gate Audit

This file is the merge authority for the LazyMind Workflow refactor. A plan
checkbox may be checked only when every exit gate in the corresponding section
is checked and linked to executable evidence.

## PR 1 — contract and behavior baseline

- [ ] Schemas cover every Tool, Event, Attempt Context and Input Resource v1 field.
- [ ] Both advance tools execute the same production transition command.
- [ ] Golden scenarios are captured from the production Runtime, not hand-authored examples.
- [ ] Go and Python readers validate and replay projection, Attempt, Artifact lineage and events.
- [ ] Serial, parallel, choice, retry, rewind, partial retry, stop and resume pass.

## PR 2 — Workflow naming and persistence mapping

- [ ] Go public types, handlers, configuration and payloads use Workflow naming.
- [ ] Python business modules, configuration, tools and payloads use Workflow naming.
- [ ] Frontend public types, stores, hooks, components and routes use Workflow naming.
- [ ] Legacy physical names are restricted to the persistence/compatibility allowlist.
- [ ] Old-schema round-trip, old binary rolling-deploy and unbackfilled-row tests pass.
- [ ] Schema capability gate, route flag, adapter metrics and deletion gate exist.
- [ ] Repository scan rejects non-allowlisted legacy domain names.

## PR 3 — shared Skill and Host Profiles

- [ ] Existing prompt rules have a source-to-policy mapping ledger.
- [ ] Skill covers discovery, preflight, readiness, parallelism, review, retry/rewind targeting, resume, Artifact and authoring.
- [ ] Default, LazyMind and Codex profiles cover every Host capability in the contract.
- [ ] LazyMind production prompt assembly loads the Skill in shadow mode.
- [ ] Shadow trace is structured, metered and keeps the legacy decision authoritative.
- [ ] Recorded golden decisions meet the declared equivalence threshold.

## PR 4 — Core Workflow Tool facade

- [ ] Public HTTP handlers implement every v1 Agent-facing and Executor-only schema.
- [ ] Preparations and events are persisted in expand-only database tables.
- [ ] Stream emits snapshot then replayable incremental events with monotonic cursor.
- [ ] Authentication, authorization, contract version and structured errors are enforced.
- [ ] Commands and preparation consumption are transactionally idempotent.
- [ ] New handlers delegate to the existing Runtime authority.
- [ ] Old/new entry points produce equal golden projections and Artifact lineage.

## PR 5 — Workflow Client and Input Resources

- [ ] Typed client, error mapping, timeout/retry and rollback flag are production wired.
- [ ] Direct Runtime table queries and handwritten transition payloads are removed outside the adapter.
- [ ] Host attachments bind to stable Input Resource revisions.
- [ ] Attempt Context contains no temporary URL, absolute path, token or model configuration.

## PR 6 — queued Attempt protocol

- [ ] Lease, heartbeat and fencing persistence are expand-only and capability gated.
- [ ] Queued claim/progress/terminal protocol enforces ownership and terminal races.
- [ ] Generic Workflow Outbox is isolated from the legacy worker domain.
- [ ] FakeExecutor passes serial, parallel, crash reclaim and terminal race tests.

## PR 7 — LazyMindExecutor

- [ ] Deterministic Supervisor owns running, heartbeat, progress and exactly one terminal report.
- [ ] Attempt Context adapter invokes the existing AgentRunPlan without leaking Host state.
- [ ] Sync and handoff modes share execution; handoff requires durable ownership.
- [ ] Canary comparison proves projection, Artifact lineage and visible event equivalence.

## PR 8 — remove fixed SubAgent endpoint dependency

- [ ] Capability-gated queued dispatch is default-on.
- [ ] Core production Runtime does not call the fixed SubAgent endpoint.
- [ ] Algorithm outage leaves Attempts queued/recoverable and restart continues them.
- [ ] Rollback is a dispatch flag only.

## PR 9 — converge algorithm/chat

- [ ] Shared decisions have one authoritative Skill source.
- [ ] Python retains only Host model/Agent/interaction/event responsibilities.
- [ ] Driver and handoff flags cannot alter Runtime projection or lineage.
- [ ] Policy rollback and decision comparison remain available.

## PR 10 — deterministic Workflow authoring

- [ ] Fixed Skill snapshot and draft file APIs are public and versioned.
- [ ] Diagnostics and publication gates are deterministic and model-free.
- [ ] LazyMind generation and static fixtures use the same validation/publish path.

## PR 11 — phase-one acceptance

- [ ] Full golden, contract and UI regression suites pass.
- [ ] One reducer consumes snapshot plus patches for every Workflow panel surface.
- [ ] Normal refresh uses the Workflow Event Stream without polling/refetch-per-event.
- [ ] Compatibility usage report and deletion ledger are generated.
- [ ] All twelve phase-one acceptance clauses have executable evidence.
