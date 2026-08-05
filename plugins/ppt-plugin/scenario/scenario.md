# AI PPT Planner Plugin

## Scenario

This plugin helps users create a multi-slide presentation using the
**plugin HTML runtime** under `plugins/ppt-plugin/runtime/` (wrapped as SubAgent tools).

- Generation: `ppt_init_deck` → stage tools (`preflight`…`batch-page-html`);
  LLM stages reuse the SubAgent chat model (`AutoModel(model='llm')`);
  page-html stages auto-publish `preview_html` from disk (no model HTML relay)
- Preview: full HTML pages in `preview_html` (iframe)
- Export: **not part of the skill**. User clicks the UI **Export** button
  (browser raster PPTX by default; Local/Desktop detects its installed editable
  dependency automatically, while containers use `LAZYMIND_OUTPUT_EDITABLE_PPT`
  with `ppt-export`)

Workflow:

1. `analyze_requirements` — goal, audience, length, visual style, constraints.
2. `collect_materials` — **optional** facts / KB / web research **and**
   registering real images (`ppt_search_web_images` +
   `ppt_register_material_images`) so later HTML embeds them.
3. `generate_ppt` — orchestrate HTML pipeline tools; save HTML + notes only.
   `ppt_init_deck` auto-attaches registered material images into Pool B;
   outline assigns `use_image`; page-html inserts foreground `<img>`.

After `analyze_requirements` succeeds, **prefer** advancing straight to
`generate_ppt` when the brief + user request / uploaded PDF already have enough
content. Queue `collect_materials` when KB/web facts or slide photos/diagrams
are still needed. Do not require `material_summary` before generation.

After the first deck is generated, the user may continue chatting to revise
individual pages. Do not require them to restart the plugin.

## Intent Recognition

### Cold Start

Invoke `trigger_ppt_plugin(user_input=<user's exact original request>)` when the
user explicitly asks for a PPT/presentation/deck plugin or asks to create,
draft, plan, or structure a multi-slide presentation.

Good trigger examples:

- "帮我做一个 AI 产品发布会 PPT"
- "用这个材料生成 10 页路演 deck"
- "Create a presentation about our Q3 performance."
- "启动 PPT 插件"

Do not trigger for:

- Simple one-answer explanations.
- Ordinary writing tasks where no slides/deck are requested.
- Image generation tasks where the user wants a picture, not a presentation.
- Uploaded PPT preview or parsing only.

### Active / completed session (follow-up chat)

Use `advance_step_and_hand_off` (or `advance_step` in continuous mode) to rewind
or rerun the relevant step. Completed PPT sessions remain editable.

| User intent | Recommended step | Tool guidance |
|---|---|---|
| Change audience / goal / tone / constraints | `analyze_requirements` | full rerun of analysis |
| After analysis, build the deck | `generate_ppt` | **preferred** next step; skip collect when facts suffice |
| Add or update references/materials | `collect_materials` | KB/web facts and/or register images for HTML |
| Regenerate the whole deck | `generate_ppt` | no page filter; full stage pipeline |
| Modify one or more specific pages | `generate_ppt` | **single-page edit** (see below) |
| Change one page's bullets / title / wording | `generate_ppt` | **single-page edit**, outline patched first |

After analysis, call:

```text
advance_step_and_hand_off(steps=[{
  "step_id": "generate_ppt",
  "user_input": "<user's original PPT request>",
  "runtime_instruction": "Full deck generation. material_summary may be absent; use requirement_analysis."
}])
```

Only use `collect_materials` when the Ready set shows it and the user still needs research beyond the analysis brief.

#### Modify a specific page

When the user asks to change page N / "第N页" / "这一页", including content edits
such as "删掉最后一个要点" or "第二条改成…":

1. Resolve the target page number:
   - Explicit page numbers in the user message win.
   - If they say "这一页/当前页/this page", use `focused_sort_order` from UI focus.
2. Call:

```text
advance_step_and_hand_off(steps=[{
  "step_id": "generate_ppt",
  "user_input": "<user's exact revision request>",
  "runtime_instruction": "Single-page edit only for sort_order=<N>. Use the existing deck_dir (ppt_find_deck if unknown). For content changes, first ppt_read_page_outline then ppt_patch_page_outline for that page (all edits in one ops_json call, including visual_hints when it states a count). To remove or retext something already on the slide, prefer ppt_edit_page_html addressing the element by its el id from ppt_read_page_html (deterministic, no redraw, republishes itself); use ppt_run_stage page-html only when the page really needs redrawing. Never ppt_init_deck and never stage=outline/style. Do NOT ppt_read_page_html + save_artifacts for HTML. If UI missing the page, call ppt_publish_pages(deck_dir, pages=<N>). Leave other pages untouched; keep notes unless asked. Do NOT export PPTX — user clicks UI Export."
}])
```

3. Briefly tell the user which page is being updated, e.g. "正在修改第 1 页…".

Do **not** restart the whole plugin for page-level edits. Do **not** ask the user
to paste HTML. Do **not** fall back to slide JSON templates.

## Output Contract

- `preview_html`: full HTML document per page (`content_type='text'`, `sort_order`)
- `preview_notes`: richer spoken introduction per page (~120–280 Chinese chars /
  4–7 sentences): page purpose, key points/data on the slide, brief interpretation,
  and a closing transition. Not a one-line stub.
- PPTX: user downloads via the panel Export button (not a skill artifact)
