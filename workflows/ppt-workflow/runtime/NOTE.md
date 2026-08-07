# Runtime notes

This directory is a **vendored, trimmed** copy of SenseNova `sn-ppt-standard`
pieces needed by LazyMind — not a full OpenClaw skill.

Kept:
- `scripts/run_stage.py` — preflight / style / outline / asset-plan / page-html / refine
- `lib/model_client.py` — LLM/VLM hooks (LazyMind injects AutoModel via tools.py)
- `prompts/` + `references/` — only prompts actually loaded by run_stage
- `scripts/export_pptx/` — Playwright helpers for **UI/API** editable export
  (not invoked by SubAgent tools; user clicks Export in WorkflowPanel)

Removed vs upstream skill:
- OpenClaw `SKILL.md` orchestration, workbench, progress WebUI wrappers
- Unused prompts (deck_review, page_review, …)
- Sibling skills (entry / creative / doctor / search-image)

Do not re-expand into a full `ppt_skills/` tree. Port individual fixes only.
