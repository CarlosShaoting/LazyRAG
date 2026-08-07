# Optional image generation

Trimmed SenseNova `sn-image-base` runner used only when
`ppt_init_deck(..., image_source='ai-gen')` for decorative T2I slots.

For real KB/web photos in slide HTML, use collect_materials →
`ppt_register_material_images` (Pool B / inherited `<img>`), not this T2I path.
Default LazyMind PPT flow uses `image_source='none'` (CSS/SVG/ECharts + optional
registered material images),
so this directory is unused on the happy path.

`SN_IMAGE_BASE` defaults to this folder when unset (see `scripts/tools.py`).
