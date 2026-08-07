import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { execFileSync } from 'node:child_process';

import { buildPptx, resolveAuthoritativeBg } from '../lib/pptx_builder.mjs';
import { cssColorToHex } from '../lib/style_parser.mjs';

function festivalIr() {
  return {
    canvasWidth: 1600,
    canvasHeight: 900,
    bodyBgColor: 'rgb(26, 26, 26)',
    bodyBgImage: 'none',
    wrapperBgColor: 'rgba(0, 0, 0, 0)',
    wrapperBgImage: 'none',
    bg: {
      tag: 'DIV',
      id: 'bg',
      bounds: { x: 0, y: 0, w: 1600, h: 900 },
      styles: {
        backgroundColor: 'rgba(0, 0, 0, 0)',
        backgroundImage: 'linear-gradient(135deg, #E53935 0%, #FF6B6B 50%, #FFD700 100%)',
        opacity: '1',
      },
      children: [{
        tag: 'DIV',
        className: '_pseudo_before',
        bounds: { x: 0, y: 0, w: 1600, h: 900 },
        styles: {
          backgroundColor: 'rgba(0, 0, 0, 0)',
          backgroundImage: 'radial-gradient(ellipse at 30% 20%, rgba(255, 215, 0, 0.3) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(255, 107, 107, 0.2) 0%, transparent 40%)',
          opacity: '1',
        },
        children: [],
      }],
    },
    ct: null,
    header: null,
    footer: null,
    overlays: [],
    rest: [],
  };
}

test('resolveAuthoritativeBg prefers #bg gradient over body chrome', () => {
  assert.equal(resolveAuthoritativeBg(festivalIr()), 'E53935');
});

test('resolveAuthoritativeBg keeps body when #bg has no usable fill', () => {
  const ir = festivalIr();
  ir.bg.styles.backgroundImage = 'none';
  ir.bg.styles.backgroundColor = 'rgba(0, 0, 0, 0)';
  assert.equal(resolveAuthoritativeBg(ir), '1A1A1A');
});

test('cssColorToHex accepts modern space-separated rgb()', () => {
  assert.equal(cssColorToHex('rgb(229 57 53)'), 'E53935');
  assert.equal(cssColorToHex('rgb(26 26 26 / 1)'), '1A1A1A');
});

test('exported slide underlay is red, not body black; no yellow wash solid', async () => {
  const deckDir = await mkdtemp(path.join(os.tmpdir(), 'lazymind-auth-bg-'));
  try {
    const outputPath = path.join(deckDir, 'festival.pptx');
    const inspectPy = path.join(deckDir, 'inspect.py');
    await writeFile(inspectPy, `
import zipfile, re, sys
z = zipfile.ZipFile(sys.argv[1])
xml = z.read('ppt/slides/slide1.xml').decode()
bg = re.search(r'<p:bg>[\\s\\S]*?</p:bg>', xml)
bg_xml = bg.group(0) if bg else ''
m = re.search(r'val="([A-F0-9]{6})"', bg_xml)
print('BG_HEX', m.group(1) if m else '')
print('GRAD', xml.count('<a:gradFill'))
print('YELLOW_WASH', int('val="FFD700"><a:alpha' in xml))
`);
    await buildPptx(
      [{ path: path.join(deckDir, 'page_001.html'), ir: festivalIr() }],
      deckDir,
      outputPath,
    );
    const out = execFileSync('python3', [inspectPy, outputPath], { encoding: 'utf8' });
    assert.match(out, /BG_HEX E53935/);
    assert.doesNotMatch(out, /BG_HEX 1A1A1A/);
    assert.match(out, /GRAD 1/);
    assert.match(out, /YELLOW_WASH 0/);
  } finally {
    await rm(deckDir, { recursive: true, force: true });
  }
});
