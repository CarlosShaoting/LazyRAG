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

## Defaults

- Preview: iframe HTML (`preview_html`), auto-published after `page-html` stages
- Export: **click Export in PluginPanel** (not part of SubAgent tools). Default =
  browser raster PPTX; optional editable via `LAZYMIND_OUTPUT_EDITABLE_PPT=true`
