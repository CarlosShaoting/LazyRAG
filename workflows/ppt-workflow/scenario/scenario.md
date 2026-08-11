# AI PPT Planner Workflow

## Scenario

This workflow helps users create a multi-slide presentation using the
**workflow HTML runtime** under `workflows/ppt-workflow/runtime/` (wrapped as SubAgent tools).

- Outline: **`ppt_build_outline`** (init → preflight → style → outline →
  `ppt_publish_outline`; one editable `slide_outline` list item per page)
- Generation: **`ppt_generate_pages`** (asset-plan → batch-page-html using each
  page's `slide_outline` brief, including human UI edits; auto-publishes
  `preview_html`)
- Preview: full HTML pages in `preview_html` (iframe)
- Export: **not part of the skill**. User clicks the UI **Export** button

Workflow:

1. `analyze_requirements` — goal, audience, length, visual style, constraints.
2. `collect_materials` — **optional** facts / KB / web research **and**
   registering images (`ppt_search_web_images` +
   `ppt_register_material_images`, or `ppt_generate_material_images` only when
   the user explicitly asks for AI material images) so later HTML embeds them.
3. `build_outline` — one call: `ppt_build_outline` → `slide_outline[page1..]`.
4. `generate_ppt` — one call: `ppt_generate_pages`; no outline rewrite.

After `analyze_requirements` succeeds, **prefer** advancing to `build_outline`
when the brief + user request / uploaded PDF/PPTX already have enough content.
Queue `collect_materials` when KB/web facts or slide photos/diagrams are still
needed.

After the first deck is generated, the user may continue chatting to revise
individual pages. Do not require them to restart the workflow.

## Intent Recognition

### Cold Start

Invoke `trigger_ppt_workflow(user_input=<user's exact original request>)` when the
user explicitly asks for a PPT/presentation/deck workflow or asks to create,
draft, plan, or structure a multi-slide presentation.

### Active / completed session (follow-up chat)

| User intent | Recommended step | Tool guidance |
|---|---|---|
| Change audience / goal / tone / constraints | `analyze_requirements` | full rerun of analysis |
| After analysis, plan pages | `build_outline` | **preferred** next step; skip collect when facts suffice |
| Add or update references/materials | `collect_materials` | KB/web facts and/or register images for HTML |
| Edit page briefs before HTML | (user edits Outline tab) | then `generate_ppt` |
| Generate / regenerate HTML slides | `generate_ppt` | uses `slide_outline` briefs; no re-outline |
| Modify one or more specific pages | `generate_ppt` | **single-page edit** |

After analysis, call:

```text
advance_step_and_hand_off(step_id="build_outline")
```

After outline is ready (and user optionally edits briefs), call:

```text
advance_step_and_hand_off(step_id="generate_ppt")
```

#### Modify a specific page

```text
advance_step_and_hand_off(step_id="generate_ppt")
```

#### Delete an entire page

```text
advance_step_and_hand_off(step_id="generate_ppt")
```
