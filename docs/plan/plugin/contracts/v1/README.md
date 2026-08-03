# Workflow contract fixtures v1

This directory is the language-neutral executable baseline for the Workflow
Agent Kit. `schemas/contract-bundle.schema.json` validates both tool envelopes
and golden scenarios. `golden/` freezes the observable projection, attempts,
artifact revisions, and durable event order for the legacy Runtime.

The fixtures intentionally use Workflow domain names. Physical `plugin_*`
database names are outside this public contract and remain confined to the
persistence compatibility boundary.

`baseline-manifest.json` records which production tests are the authority for
the frozen observations. A golden file is not evidence by itself: both readers
validate scenario coverage, entity references, Attempt numbering, immutable
Artifact revision ordering, and the replay cursor rules from that manifest.

The public schemas are split by boundary:

- `schemas/tool-contract.schema.json`: idempotent transition command input.
- `schemas/event-contract.schema.json`: durable ordered stream envelope.
- `schemas/attempt-context.schema.json`: executor-visible, Host-neutral context.
- `schemas/contract-bundle.schema.json`: response envelopes and golden baseline.

The production Python symbol retains the historical spelling
`advance_step_and_hand_off`; the v1 public tool name is
`advance_step_and_hand_off` as recorded in the manifest. Both tools submit the
same Runtime transition. The synchronous tool waits for terminal execution;
the handoff tool returns after the submission has durable ownership.
