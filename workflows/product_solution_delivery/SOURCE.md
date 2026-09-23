# Source and adaptation record

This built-in Workflow is adapted from an internally assembled `product-solution-delivery` Skill
package. No private filesystem location is part of the Workflow package or runtime contract.

- Source release: `psd-2026-08-11-portable-lazymind-competitive-analysis-v1`
- Authority: the original portable Skill package supplied by the user; the separate
  visible-receipt testing variant is not the product contract.
- Parent contract: `SKILL.md`
- Atomic child contracts:
  - `shape-product-direction`
  - `analyze-competitors`
  - `product-design-full-cycle`
  - `write-prd`
  - `build-product-prototype`
  - `review-product-artifact`
  - `prepare-development-handoff`

The Workflow-local business contracts in `scripts/tools.py` were produced by the internal
LazyMind adaptation and are loaded deterministically at runtime. Runtime code does not read or
execute the original Skill package.

## Open-source design references

The internal Skill and this Workflow do **not** copy the following Skills verbatim. They were
consulted as design references for competitive research scope, evidence collection, competitor
discovery, positioning, profiling, and consulting-analysis structure:

| Referenced Skill | Upstream repository license |
|---|---|
| [Anthropic `competitive-brief`](https://github.com/anthropics/knowledge-work-plugins/blob/main/marketing/skills/competitive-brief/SKILL.md) | [Apache License 2.0](https://github.com/anthropics/knowledge-work-plugins/blob/main/LICENSE) |
| [Bright Data `competitive-intel`](https://github.com/brightdata/skills/blob/main/skills/competitive-intel/SKILL.md) | [MIT License](https://github.com/brightdata/skills/blob/main/LICENSE) |
| [Anysite `competitor-discovery`](https://github.com/anysiteio/agent-skills/blob/main/skills/competitor-discovery/SKILL.md) | [MIT License](https://github.com/anysiteio/agent-skills/blob/main/LICENSE) |
| [Anysite `positioning-map`](https://github.com/anysiteio/agent-skills/blob/main/skills/positioning-map/SKILL.md) | [MIT License](https://github.com/anysiteio/agent-skills/blob/main/LICENSE) |
| [Corey Haines `competitor-profiling`](https://github.com/coreyhaines31/marketingskills/blob/main/skills/competitor-profiling/SKILL.md) | [MIT License](https://github.com/coreyhaines31/marketingskills/blob/main/LICENSE) |
| [ByteDance DeerFlow `consulting-analysis`](https://github.com/bytedance/deer-flow/blob/main/skills/public/consulting-analysis/SKILL.md) | [MIT License](https://github.com/bytedance/deer-flow/blob/main/LICENSE) |

The license labels above describe the respective upstream repositories; they do not change the
license of this repository or imply endorsement by the upstream authors.

## Source-to-Workflow mapping

| Original concept | Built-in Workflow implementation |
|---|---|
| Parent Router and explicit-stage priority | `route_product_stage`, `validate_product_route`, and host `route_selector` binding |
| Clean-project default after Ask user | `validate_product_route` selects `direction`; after its HITL boundary, `competitive` is the first eligible/recommended next stage |
| Single stage or explicitly authorized finite chain | the chain is planning metadata; each Session authorizes only `selected_stage` |
| Product Workspace / Artifact Manifest | versioned internal `stage_manifest` / `workspace_state`, inherited through `workspace_seed` |
| Evidence only when it changes decisions | the parent Router collects evidence only for the selected stage |
| `shape-product-direction` | text path with artifact type `direction-brief` |
| `analyze-competitors` | `analyze_competitive_position` |
| `product-design-full-cycle` | `route_design_scope` activates the two-layer/six-domain scope and light/heavy branch before Writer |
| `write-prd` | text path with artifact type `prd` |
| `build-product-prototype` | `build_interactive_prototype` |
| `review-product-artifact` | text path with artifact type `review-report` |
| `prepare-development-handoff` | text path with artifact type `development-handoff` |
| Stage HITL and explicit continuation | one-stage boundary plus idempotent public `product-stage-relay` commands |

## LazyMind-native substitutions

- Five text-producing stages share LazyMind Writer for resource profiling, editable Markdown
  outlines, section planning, streaming/checkpointed drafting, revisions and selection rewrite.
- Selected knowledge bases use LazyMind `kb` with inherited runtime filters.
- Current public product evidence uses LazyMind `web_search` and `url_fetch`; provider selection and
  credentials remain generic runtime configuration.
- Every stage publishes synchronized HTML and Markdown under one logical artifact version. Text-stage HTML is deterministically rendered from the Writer Markdown; specialized HTML/Markdown pairs are published together. HTML files are written only inside the active Workflow workspace and receive deterministic
  prototype/competitive-report validation.
- LazyMind Artifact revisions remain the host record. `build_product_handoff_state` deterministically
  builds exact artifact fingerprints, version lineage, dependencies, quality checks and open
  questions; terminal `publish_product_handoff_state` writes the private Manifest/Workspace and the
  Chinese delivery summary as one Host-owned completion path. Stage-owned
  `*_assessment` slots retain professional judgments; unavailable evidence cannot pass a check.
- The source LazyMind Adapter's one-stage-per-Session rule is preserved. A multi-stage request can
  guide the next recommendation, but cannot cross the stage confirmation boundary automatically.
- The design child Router uses the six canonical domains, per-subdecision light/heavy effort, and
  non-compensatory privacy/identity/permission/silent-write/cross-tenant/irreversibility gates.
- Both Router nodes declare `route_selector`: their saved JSON decisions determine the reachable
  edge immediately. Missing or invalid decisions never default to a different business stage.
- Light design research can escalate individual decisions inside the current evidence step. The
  effective `design_escalation` record is passed to Writer and the final Workspace; it cannot change
  approved scope or downgrade heavy decisions. New high-risk boundaries still need confirmation.
- The public stage relay creates a new Session only for a user command, carries immutable input
  resources and exact source revisions, and records source-bound approval events. Continuing does
  not accept proposed decisions. Accepting a current artifact is a separate explicit operation.
- Runtime trace remains internal. No visible Skill receipt is part of the product interface.

## Shared-project adaptation (2026-09-07)

The user's clarified target is one project and one conversation window, with design, PRD,
prototype and other stage artifacts presented as shared views, not one overwritten document.

- The host projects the selected version of each stage from the same workspace lineage. A new
  internal stage Session does not create another conversation or require another user window.
- Returning to a stage binds its own prior version alongside the selected upstream versions.
  Writer and HTML stages revise that baseline; historical versions remain available to the host.
- The latest explicit change request is bound in `stage_approval.request_context`, separately
  from the stable product goal. Shared materials and decisions are not re-entered by the user.
- Product-stage defaults replace repeated startup fields: automatic execution depth, target-stage
  text length, and supplied or default structure. This is an intentional user-authorized override
  of the portable Skill's separate sample-confirmation question, not a claim that a sample exists.
- Content identity/version, assessment revision/history, and sourced acceptance are separate.
  Reassessment can change readiness without creating a fake new content version. Child-reported
  evidence is labelled as such; no browser execution is claimed merely from a text assertion.
- Current stage editing and historical shared-view inspection stay in the same panel. Inspection
  is read-only and never authorizes a stage run. Stage transitions require the user's action at
  a safe completed-stage boundary; active work is not silently interrupted.
- Necessary HITL remains at stage/scope review, editable outlines and outputs, decision acceptance,
  and stage continuation. Decision accept/defer commands bind the exact server-snapshotted proposal
  and the expected project state version; accepting one decision never accepts every artifact.
  Unconfirmed high-risk decisions and new hard-gate revisions permit drafts, but block an
  implementation-ready conclusion and, in newly finalized stages, pause stage relay until the
  user explicitly accepts or defers each decision. Deferral carries only a draft, never a risk
  approval. A child assessment cannot erase Router 2's known hard gates or claim a human deferral.

## Rich-document presentation adaptation (2026-09-13)

- Direction, design, PRD, review and handoff keep their approved Markdown outline and enrich only
  the relevant existing sections with tables, Mermaid diagrams and actual project images.
- Prototype remains a self-contained interactive HTML default view with a synchronized Markdown companion; it may add a compact page-flow
  overview and key-state gallery without replacing the interactive screens.
- Timelines require real dates or explicit relative markers. Two-axis distributions require named
  axes and must say when positions are qualitative. Missing evidence never becomes a visual fact.
- The design Writer renders only the light or heavy branch selected by Router 2; the unselected
  branch does not appear as an empty panel or placeholder.
- Competitive analysis retains its existing generation and rich-report contract unchanged.

## Deliberate boundaries

The Workflow does not claim logged-in product operation, paid-source access, browser visual QA,
production frontend implementation, technical architecture, engineering estimates, release dates,
or organizational approval. Missing sources, rules and decisions remain explicit gaps. Only the
parent Router's selected stage may run in a Session. Continuing, switching, adding or reversing
stages requires explicit user action and a new Workflow run.
