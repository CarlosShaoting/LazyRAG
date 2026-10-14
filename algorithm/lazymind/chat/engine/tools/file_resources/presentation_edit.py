from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


_FONT_TAGS = {'latin', 'ea', 'cs'}
_COLOR_TAGS = {'srgbClr', 'sysClr'}
_HEX_COLOR = re.compile(r'^[0-9A-F]{6}$')


def _local_name(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def _normalize_color(value: Any) -> str:
    color = str(value or '').strip().lstrip('#').upper()
    if not _HEX_COLOR.fullmatch(color):
        raise ValueError(f'invalid RGB color {value!r}; expected #RRGGBB')
    return color


def normalize_color_map(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError('color_map must be an object or a JSON object string') from exc
    if not isinstance(value, dict) or not value:
        raise ValueError('color_map must contain at least one old-to-new RGB mapping')
    return {_normalize_color(old): _normalize_color(new) for old, new in value.items()}


def available_font_families() -> set[str]:
    """Return installed font family names without guessing a fallback font."""
    fc_list = shutil.which('fc-list')
    if fc_list:
        try:
            result = subprocess.run(
                [fc_list, '--format=%{family}\n'], check=True,
                capture_output=True, text=True, timeout=15,
            )
            return {
                family.strip()
                for line in result.stdout.splitlines()
                for family in line.split(',')
                if family.strip()
            }
        except (OSError, subprocess.SubprocessError):
            pass

    roots = [
        Path('/System/Library/Fonts'), Path('/Library/Fonts'),
        Path.home() / 'Library' / 'Fonts', Path('/usr/share/fonts'),
        Path('/usr/local/share/fonts'), Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts',
    ]
    families: set[str] = set()
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        TTFont = None  # type: ignore[assignment,misc]
    if TTFont is not None:
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob('*'):
                if path.suffix.lower() not in {'.ttf', '.otf', '.ttc'}:
                    continue
                try:
                    font = TTFont(str(path), lazy=True, fontNumber=0)
                    for record in font['name'].names:
                        if record.nameID in {1, 16}:
                            families.add(record.toUnicode().strip())
                    font.close()
                except Exception:
                    continue
    return {family for family in families if family}


def inspect_pptx(path: str | Path, installed_fonts: set[str] | None = None) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() != '.pptx':
        raise ValueError('presentation editing supports .pptx files only')
    fonts: Counter[str] = Counter()
    colors: Counter[str] = Counter()
    slide_count = 0
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            if '[Content_Types].xml' not in names or 'ppt/presentation.xml' not in names:
                raise ValueError('file is not a valid PowerPoint OOXML package')
            for name in names:
                if not name.startswith('ppt/') or not name.endswith('.xml'):
                    continue
                if re.fullmatch(r'ppt/slides/slide\d+\.xml', name):
                    slide_count += 1
                try:
                    root = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    continue
                for node in root.iter():
                    local = _local_name(node.tag)
                    if local in _FONT_TAGS:
                        family = node.attrib.get('typeface', '').strip()
                        if family and not family.startswith('+'):
                            fonts[family] += 1
                    elif local in _COLOR_TAGS:
                        value = (node.attrib.get('val') or node.attrib.get('lastClr') or '').upper()
                        if _HEX_COLOR.fullmatch(value):
                            colors[value] += 1
    except zipfile.BadZipFile as exc:
        raise ValueError('file is not a valid PPTX ZIP package') from exc

    installed = installed_fonts if installed_fonts is not None else available_font_families()
    installed_folded = {family.casefold() for family in installed}
    return {
        'filename': source.name,
        'slide_count': slide_count,
        'fonts': [
            {
                'family': family,
                'references': count,
                'available': family.casefold() in installed_folded,
            }
            for family, count in fonts.most_common()
        ],
        'missing_fonts': [
            family for family in fonts
            if family.casefold() not in installed_folded
        ],
        'colors': [
            {'rgb': f'#{color}', 'references': count}
            for color, count in colors.most_common()
        ],
        'installed_font_count': len(installed),
    }


def rewrite_pptx(
    source_path: str | Path,
    output_path: str | Path,
    *,
    source_font: str | None = None,
    target_font: str | None = None,
    color_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rewrite font/color OOXML attributes while preserving all other parts."""
    source = Path(source_path)
    output = Path(output_path)
    if source.suffix.lower() != '.pptx' or output.suffix.lower() != '.pptx':
        raise ValueError('presentation editing supports .pptx files only')
    normalized_source_font = str(source_font or '').strip()
    normalized_target_font = str(target_font or '').strip()
    if normalized_source_font and not normalized_target_font:
        raise ValueError('target_font is required when source_font is provided')
    if not normalized_target_font and not color_map:
        raise ValueError('provide target_font and/or color_map')
    normalized_colors = {
        _normalize_color(old): _normalize_color(new)
        for old, new in (color_map or {}).items()
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    font_replacements = 0
    color_replacements = 0
    changed_parts: list[str] = []
    try:
        with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(
            output, 'w', compression=zipfile.ZIP_DEFLATED,
        ) as outgoing:
            names = incoming.namelist()
            if '[Content_Types].xml' not in names or 'ppt/presentation.xml' not in names:
                raise ValueError('file is not a valid PowerPoint OOXML package')
            for info in incoming.infolist():
                raw = incoming.read(info.filename)
                changed = False
                if info.filename.startswith('ppt/') and info.filename.endswith('.xml'):
                    try:
                        root = ET.fromstring(raw)
                    except ET.ParseError:
                        root = None
                    if root is not None:
                        for node in root.iter():
                            local = _local_name(node.tag)
                            if local in _FONT_TAGS and normalized_target_font:
                                current = node.attrib.get('typeface', '')
                                if (
                                    (not normalized_source_font or current.casefold() == normalized_source_font.casefold())
                                    and current != normalized_target_font
                                ):
                                    node.set('typeface', normalized_target_font)
                                    font_replacements += 1
                                    changed = True
                            if local in _COLOR_TAGS and normalized_colors:
                                for attribute in ('val', 'lastClr'):
                                    current = node.attrib.get(attribute, '').upper()
                                    replacement = normalized_colors.get(current)
                                    if replacement and replacement != current:
                                        node.set(attribute, replacement)
                                        color_replacements += 1
                                        changed = True
                        if changed:
                            raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                            changed_parts.append(info.filename)
                outgoing.writestr(info, raw)
    except zipfile.BadZipFile as exc:
        raise ValueError('file is not a valid PPTX ZIP package') from exc

    if font_replacements == 0 and color_replacements == 0:
        output.unlink(missing_ok=True)
        raise ValueError('the requested font/color values were not present; no new version was created')
    return {
        'font_replacements': font_replacements,
        'color_replacements': color_replacements,
        'changed_parts': changed_parts,
    }
