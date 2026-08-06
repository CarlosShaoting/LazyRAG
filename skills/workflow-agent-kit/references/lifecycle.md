# Workflow lifecycle v1

1. Inspect the conversation first. If any non-dismissed Session exists, reuse its
   exact id and projection; do not prepare another Session.
2. Only when no non-dismissed Session exists, discover an enabled, authorized
   Workflow and pin its revision.
3. Call `prepare_workflow`; bind every missing durable Input Resource. In the
   LazyMind Chat Host profile this wrapper also atomically starts the Session
   when preparation is ready and returns its initial projection.
4. Under the public Runtime/MCP contract, call `start_workflow` only with a
   ready, unexpired preparation. Do not call it after the LazyMind Chat Host
   wrapper has already returned a `session_id`.
5. Refresh the projection, select only `ready_steps`, and advance through the
   tool allowed by the active Host profile.
6. Review required Artifacts before reporting terminal success.
7. Stop only on explicit user intent through the Host/UI controller; do not
   expose stop as a model tool. Resume the same Session, refresh, and then advance
   the interrupted step; never stop-and-prepare as a recovery strategy.

Preparation is not a Session. Conversation memory is not projection state. A
state-version conflict always requires a fresh projection and a new decision.
Stopped, failed, and completed Sessions remain non-dismissed and therefore block
a new run until the user explicitly dismisses them.

The Chat Host's atomic prepare-and-start wrapper is an adapter convenience, not
a change to the Runtime lifecycle. Its returned `session_id` is authoritative:
do not prepare again, synthesize another id, or invoke `start_workflow` again.
