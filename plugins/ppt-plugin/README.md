# ppt-plugin

LazyMind AI PPT plugin: generate HTML slides in chat, preview in PluginPanel,
export PPTX (raster in browser by default; optional editable via Playwright).

## Layout

```
plugins/ppt-plugin/
  plugin.yaml / scenario/     # LazyMind plugin contract (entry / steps / UI)
  scripts/tools.py            # SubAgent tools (ppt_init_deck, ppt_run_stage, …)
  runtime/                    # HTML pipeline used at runtime (ONLY what we need)
    lib/model_client.py
    prompts/                  # style / outline / page-html / refine
    references/               # html_constraints, style_catalog
    scripts/run_stage.py
    scripts/export_pptx/      # Playwright DOM → editable PPTX
  image_gen/                  # Optional T2I backend (image_source=ai-gen)
```

## Note on SenseNova skills (important)

This plugin does **not** vendor the full SenseNova / OpenClaw skills tree
(`sn-ppt-entry`, `sn-ppt-creative`, `sn-ppt-doctor`, `sn-search-image`, SKILL.md
orchestration, workbench, etc.).

What we keep under `runtime/` (+ optional `image_gen/`) is a **minimal runtime
subset** adapted for LazyMind:

| SenseNova skill piece | In this plugin? | Why |
|---|---|---|
| `sn-ppt-standard` run_stage + prompts | Yes → `runtime/` | HTML generation |
| `export_pptx` (Playwright) | Yes → `runtime/scripts/export_pptx/` | Used by **UI/API** editable export only — **not** a skill tool |
| `sn-image-base` T2I runner | Yes → `image_gen/` | Only if `image_source=ai-gen` |
| `sn-ppt-entry` | No | Replaced by `ppt_init_deck` + plugin scenario |
| `sn-ppt-creative` | No | Not used (standard HTML mode only) |
| `sn-ppt-doctor` | No | Env checks live in deploy / docs |
| `sn-search-image` | No | Replaced by `ppt_search_web_images` + `ppt_register_material_images` (Pool B → HTML `<img>`) |

Upstream SenseNova skills may evolve separately. Do not re-copy the whole
`skills/` tree into this repo; if a stage/prompt/export fix is needed, port the
specific file into `runtime/` and note it here.

## Material images → final HTML

Optional `collect_materials` can pull facts (`kb`, `web_search`) and real images:

1. `ppt_search_web_images` / KB image hits → `ppt_register_material_images`
2. `ppt_init_deck` auto-attaches them into `info_pack.user_assets.reference_images`
3. `outline` assigns `use_image.reference_image_index`
4. `page-html` copies to `images/page_XXX_inherited.*` and embeds a foreground `<img>`

Keep `image_source='none'` for this path (AI T2I is separate).

## Deck storage (conversation-scoped)

SubAgent workspaces are per task (`<root>/<user>/<task_id>/`), so decks and
material images are kept outside them, shared by every step task of one
conversation:

```
<workspace_root>/<user_id>/ppt_sessions/<conversation_id>/
  ppt_decks/<deck_id>/     # task_pack, outline, pages/, images/
  material_images/         # registered in collect_materials, attached at init
```

Without this, a follow-up edit task would see an empty workspace, `ppt_find_deck`
would find nothing, and the whole deck would be regenerated instead of edited.

## Single-page edit

Follow-up requests like "第3页删掉最后一个要点" patch one page instead of
rebuilding the deck:

1. `ppt_find_deck` (when `deck_dir` is not already known)
2. `ppt_read_page_outline(deck_dir, page=N)` — indexed bullets / data_points
3. `ppt_patch_page_outline(deck_dir, page=N, ops_json=[…])` — `delete_bullet`,
   `replace_bullet`, `insert_bullet`, `set_bullets`, `set_field`,
   `delete_data_point`, `set_data_points`; all ops for a page in one call
4. Make the slide match, either
   - `ppt_read_page_html(deck_dir, page=N)` for the element list, then
     `ppt_edit_page_html(deck_dir, page=N, ops_json=[…])` — deterministic
     `delete_node` / `replace_text` on the existing HTML, no LLM redraw, and it
     republishes the page itself, or
   - `ppt_run_stage(deck_dir, stage='page-html', page=N)` — LLM redraw of that page

### Stable element ids

`page-html` tags every content element with `data-el` (`title`, `subtitle`,
`bullet-i`, `kpi-i`, `table`, `image-i`, `footer`) and pairs a heading with its
body via `data-group`. Those ids are the addressing layer for editing:

- `ppt_read_page_html` returns them as a small JSON element list (id, tag, text
  preview) instead of the HTML body
- `ppt_edit_page_html` deletes or retexts by `el` / `group`, so "只删这一项"
  never depends on matching text that may appear twice
- the PPTX exporter carries each id into the shape name (`objectName`), so an
  exported deck stays id-addressable — `python-pptx` can drop one element by
  `shape.name` without regenerating anything

Decks generated before this existed have no `data-el`; `ppt_read_page_html` then
reports `repeated_classes` and edits fall back to `class` + `index`.

`ppt_init_deck` and the `outline` / `style` stages are for full generation only;
they discard the other pages' approved content.

### Why both step 3 and step 4

`outline.json` drives generation, the page HTML is what the user sees. Patching
only the outline leaves the current slide unchanged; editing only the HTML is
undone by the next redraw. `ppt_edit_page_html` warns when the outline still
carries text it just removed.

A stale count in `visual_hints` ("底部横向排列四个指标卡片") is the classic way a
deletion comes back: the rewriter keeps four columns and the generator invents a
filler card. `ppt_patch_page_outline` warns about this, and both page prompts
forbid padding a grid.

## Defaults

- Preview: iframe HTML (`preview_html`), auto-published after `page-html` stages
- Export: **click Export in PluginPanel** (not part of SubAgent tools). Default =
  browser raster PPTX; optional editable via `LAZYMIND_OUTPUT_EDITABLE_PPT=true`
