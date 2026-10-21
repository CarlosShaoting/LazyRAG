"""Sparse font-only OOXML edits sharing inspect_content's stable text slot IDs."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree

from .font_library import ensure_font
from .pptx_template_fill import _load, _slots, NS
from .presentation_edit import normalize_page_numbers


def edit_fonts(source, output, source_sha256, target_font, pages=None,
               slot_ids=None, text_scope='all', allow_download=False):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('Output must not overwrite source')
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha256:
        raise ValueError('Deck changed; inspect the current revision again')
    if text_scope not in {'all', 'titles', 'body'}:
        raise ValueError('text_scope must be all, titles or body')
    infos, data, slides = _load(source)
    if isinstance(pages, (list, tuple)) and any(type(p) is not int for p in pages):
        raise ValueError('pages must contain integers')
    if isinstance(pages, bool):
        raise ValueError('pages must contain integers')
    selected = normalize_page_numbers(pages)
    selected = set(selected if selected is not None else range(1, len(slides) + 1))
    if any(p > len(slides) for p in selected):
        raise ValueError('Font edit page exceeds slide count')
    if slot_ids is not None and (not isinstance(slot_ids, (list, tuple)) or not slot_ids
                               or any(not isinstance(s, str) for s in slot_ids)):
        raise ValueError('slot_ids must be a non-empty list of exact inspected IDs')
    requested = set(slot_ids or [])
    targets = []
    found = set()
    for page, (name, root) in enumerate(slides, 1):
        if page not in selected:
            continue
        for node, slot in _slots(root, page):
            if requested and slot['id'] not in requested:
                continue
            shape = next((a for a in node.iterancestors() if a.tag == '{%s}sp' % NS['p']), None)
            ph = shape.find('.//p:ph', NS) if shape is not None else None
            title = ph is not None and ph.get('type') in {'title', 'ctrTitle'}
            if (text_scope == 'titles' and not title) or (text_scope == 'body' and title):
                continue
            targets.append((page, node, slot))
            found.add(slot['id'])
    if requested - found or not targets:
        raise ValueError('Requested font targets were not found in the selected scope; inspect exact slots')
    family = ensure_font(target_font, allow_download)
    changed = set()
    for page, node, slot in targets:
        parent = node if slot['empty_paragraph'] else node.getparent()
        tag = 'endParaRPr' if slot['empty_paragraph'] else 'rPr'
        properties = parent.find('a:' + tag, NS)
        if properties is None:
            properties = etree.Element('{%s}%s' % (NS['a'], tag))
            if slot['empty_paragraph']:
                parent.append(properties)
            else:
                parent.insert(0, properties)
        for script in ('latin', 'ea', 'cs'):
            child = properties.find('a:' + script, NS)
            if child is None:
                child = etree.Element('{%s}%s' % (NS['a'], script))
                later = {'latin': {'ea', 'cs', 'sym', 'hlinkClick', 'hlinkMouseOver', 'rtl', 'extLst'},
                         'ea': {'cs', 'sym', 'hlinkClick', 'hlinkMouseOver', 'rtl', 'extLst'},
                         'cs': {'sym', 'hlinkClick', 'hlinkMouseOver', 'rtl', 'extLst'}}[script]
                index = next((i for i, c in enumerate(properties) if etree.QName(c).localname in later), len(properties))
                properties.insert(index, child)
            child.set('typeface', family)
        changed.add(page)
    for page in changed:
        name, root = slides[page - 1]
        data[name] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, data[info.filename])
    complex_parts = [name for name in data if name.startswith(('ppt/charts/', 'ppt/diagrams/')) and name.endswith('.xml')]
    return {'target_font': family, 'slide_count': len(slides), 'updated_font_pages': sorted(changed),
            'updated_font_slots': len(targets), 'original_unchanged': True,
            'unmodified_complex_text_parts': complex_parts,
            'font_notice': 'Receiving PowerPoint also needs this font installed; native font embedding is not added.'}
