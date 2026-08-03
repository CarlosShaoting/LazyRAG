# LazyMind legacy source → shared policy ledger

This ledger is the audit boundary for PR3. It maps existing behavior; it does not
make the shared evaluator authoritative.

| Legacy source | Existing rule | Shared policy clause | Shadow input/evidence |
|---|---|---|---|
| `chat/workflow/workflow_manager.py::_COLD_START_PLUGIN_PROMPT` | Trigger only for direct intent; explicit named Workflow must trigger | Discover/prepare before start | Cold-start prompt tests remain authoritative; the constant name is a tracked legacy prompt alias |
| `build_cold_start_tools` preflight | `need_information` blocks start; `ready` produces one valid first step | Missing-input and preparation gates | Existing preflight tests |
| `_build_cold_execution_policy` | Auto hands off; dynamic waits only for explicit multi-step/no-approval cases | Rules 7–9 | Golden launch cases |
| `_build_step_status_section` | Go Ready projection is the execution frontier; conditions disambiguate choices | Rules 3 and 6 | `ready_steps`, active edges |
| `_build_mode_guidance` Rule 0 | Persist explicit user constraints before advancement | Host intent capture before shared decision | Intent-writer tests; policy receives normalized intent tokens only |
| `_build_mode_guidance` Rule 1 | Changed succeeded output targets earliest invalid step | Rule 4 | `changed_succeeded_step` |
| `_build_mode_guidance` Rule 2 | Atomic batch of independent Ready steps; retry is singular | Rules 5–6 | Ready/attempted sets |
| `_build_mode_guidance` Rules 3–4 | Approval and explicit uninterrupted boundary choose wait vs handoff | Rules 7–9 | approval map + normalized intent tokens |
| `build_advance_step_tool` | Wait for submitted task result and continue current turn | Waiting-tool semantics | Existing manager tests |
| `build_advance_step_and_hand_off_tool` | Submit atomically then stop after durable acceptance | Handoff semantics | Existing manager/stream-guard tests |
| `_trigger_workflow_step(s)` | Runtime resolves transition and accepts/rejects command | Runtime authority/idempotency | Transition submission tests |
| `engine/driver_agent.py` | Synthetic next turn after asynchronous completion | LazyMind Host profile (`driver`, `synthetic_turn`) | Driver tests; not a Runtime policy rule |
| `engine/subagent/runner.py::_build_subagent_plan` | Attempt objective, inputs, artifacts and output contract are isolated | Execute/review contract | SubAgent prompt-plan tests |
| `engine/subagent/runner.py` terminal handling | Artifacts and terminal outcome are reported after execution | Required-Artifact terminal rule | SubAgent artifact tests |

## Migration gate

The production flag is `LAZYMIND_WORKFLOW_POLICY_SHADOW` (default off). When on,
the active-session prompt path records `workflow.shadow-trace.v1` entries and
counters (`evaluated`, `equivalent`, `mismatch`) in request agentic configuration
and structured logs. Legacy remains authoritative. The PR3 golden suite requires
100% equivalence; default-on/canary and deletion of legacy prompt rules belong to
later migration PRs.
