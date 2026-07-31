import PptxGenJS from 'pptxgenjs';
import { notesToParagraph } from './exportHtmlToPptx';
import { parseSlideSpec, type SlideSpec } from './slideSchema';
import { PPT_FONT_FACE, resolveTheme, type ResolvedTheme } from './themes';

const SLIDE_W_IN = 13.333;
const SLIDE_H_IN = 7.5;

export interface JsonSlideInput {
  spec: SlideSpec;
  notes?: string;
  pageNo?: number;
}

type ShapeType = PptxGenJS['ShapeType'];

function hex(color: string): string {
  return color.replace('#', '').toUpperCase();
}

function addFooter(slide: PptxGenJS.Slide, theme: ResolvedTheme, footer?: string) {
  if (!footer) return;
  slide.addText(footer, {
    x: 0.6,
    y: 7.05,
    w: 12.1,
    h: 0.3,
    fontSize: 12,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.muted),
    margin: 0,
  });
}

function paintBackground(slide: PptxGenJS.Slide, shapes: ShapeType, theme: ResolvedTheme) {
  slide.addShape(shapes.rect, {
    x: 0,
    y: 0,
    w: SLIDE_W_IN,
    h: SLIDE_H_IN,
    fill: { color: hex(theme.bg) },
    line: { color: hex(theme.bg) },
  });
  slide.addShape(shapes.rect, {
    x: 0,
    y: 0,
    w: 0.12,
    h: SLIDE_H_IN,
    fill: { color: hex(theme.primary) },
    line: { color: hex(theme.primary) },
  });
}

function renderTitleLike(slide: PptxGenJS.Slide, spec: SlideSpec, theme: ResolvedTheme, chip?: string) {
  if (chip) {
    slide.addText(chip, {
      x: 1.2,
      y: 2.1,
      w: 10.8,
      h: 0.35,
      fontSize: 14,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.accent),
      align: 'center',
      bold: true,
      margin: 0,
    });
  }
  slide.addText(spec.title, {
    x: 1.0,
    y: chip ? 2.55 : 2.4,
    w: 11.3,
    h: 1.4,
    fontSize: 40,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.primary),
    align: 'center',
    bold: true,
    valign: 'middle',
    margin: 0,
  });
  if (spec.subtitle) {
    slide.addText(spec.subtitle, {
      x: 1.5,
      y: 4.1,
      w: 10.3,
      h: 0.8,
      fontSize: 18,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      align: 'center',
      margin: 0,
    });
  }
}

function renderBullets(slide: PptxGenJS.Slide, spec: SlideSpec, theme: ResolvedTheme) {
  slide.addText(spec.title, {
    x: 0.7,
    y: 0.45,
    w: 12.0,
    h: 0.7,
    fontSize: 28,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.primary),
    bold: true,
    margin: 0,
  });
  if (spec.subtitle) {
    slide.addText(spec.subtitle, {
      x: 0.7,
      y: 1.15,
      w: 12.0,
      h: 0.4,
      fontSize: 15,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      margin: 0,
    });
  }
  const items = (spec.bullets || []).slice(0, 8);
  const startY = spec.subtitle ? 1.75 : 1.4;
  slide.addText(
    items.map((t) => ({
      text: t,
      options: {
        bullet: true,
        breakLine: true,
        fontSize: 18,
        fontFace: PPT_FONT_FACE,
        color: hex(theme.text),
        paraSpaceAfter: 10,
      },
    })),
    {
      x: 0.9,
      y: startY,
      w: 11.5,
      h: 4.8,
      valign: 'top',
      margin: 0,
    },
  );
}

function renderCards(slide: PptxGenJS.Slide, shapes: ShapeType, spec: SlideSpec, theme: ResolvedTheme) {
  slide.addText(spec.title, {
    x: 0.7,
    y: 0.4,
    w: 12.0,
    h: 0.6,
    fontSize: 26,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.primary),
    bold: true,
    margin: 0,
  });
  if (spec.subtitle) {
    slide.addText(spec.subtitle, {
      x: 0.7,
      y: 1.0,
      w: 12.0,
      h: 0.35,
      fontSize: 14,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      margin: 0,
    });
  }

  const cards = (spec.cards || []).slice(0, 4);
  const n = Math.max(cards.length, 1);
  const cols = n <= 2 ? n : 2;
  const rows = Math.ceil(n / cols);
  const gap = 0.22;
  const left = 0.55;
  const usable = 12.2;
  const cardW = (usable - gap * (cols - 1)) / cols;
  const top = spec.subtitle ? 1.45 : 1.2;
  const bottom = 0.55;
  const usableH = 7.5 - top - bottom;
  const cardH = (usableH - gap * (rows - 1)) / rows;

  cards.forEach((card, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = left + col * (cardW + gap);
    const y = top + row * (cardH + gap);
    slide.addShape(shapes.roundRect, {
      x,
      y,
      w: cardW,
      h: cardH,
      fill: { color: hex(theme.bgAlt) },
      line: { color: hex(theme.primary), width: 1.25 },
      rectRadius: 0.12,
    });
    slide.addText(card.heading, {
      x: x + 0.18,
      y: y + 0.2,
      w: cardW - 0.36,
      h: 0.5,
      fontSize: 16,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.accent),
      bold: true,
      margin: 0,
    });
    const bodyParts: Array<{ text: string; options: Record<string, unknown> }> = [];
    if (card.body) {
      bodyParts.push({
        text: card.body,
        options: {
          fontSize: 13,
          fontFace: PPT_FONT_FACE,
          color: hex(theme.text),
          breakLine: true,
          paraSpaceAfter: 8,
        },
      });
    }
    (card.bullets || []).slice(0, 5).forEach((b) => {
      bodyParts.push({
        text: b,
        options: {
          bullet: true,
          breakLine: true,
          fontSize: 13,
          fontFace: PPT_FONT_FACE,
          color: hex(theme.text),
          paraSpaceAfter: 6,
        },
      });
    });
    if (bodyParts.length) {
      slide.addText(bodyParts as PptxGenJS.TextProps[], {
        x: x + 0.18,
        y: y + 0.8,
        w: cardW - 0.36,
        h: Math.max(0.8, cardH - 1.05),
        valign: 'top',
        margin: 0,
      });
    }
  });
}

function renderTwoColumn(slide: PptxGenJS.Slide, shapes: ShapeType, spec: SlideSpec, theme: ResolvedTheme) {
  slide.addText(spec.title, {
    x: 0.7,
    y: 0.4,
    w: 12.0,
    h: 0.6,
    fontSize: 26,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.primary),
    bold: true,
    margin: 0,
  });
  if (spec.subtitle) {
    slide.addText(spec.subtitle, {
      x: 0.7,
      y: 1.0,
      w: 12.0,
      h: 0.35,
      fontSize: 14,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      margin: 0,
    });
  }

  const cols = [spec.left, spec.right];
  const top = spec.subtitle ? 1.5 : 1.25;
  const widths = [5.85, 5.85];
  const xs = [0.6, 6.85];

  cols.forEach((col, i) => {
    slide.addShape(shapes.roundRect, {
      x: xs[i],
      y: top,
      w: widths[i],
      h: 5.0,
      fill: { color: hex(theme.bgAlt) },
      line: { color: hex(theme.primary), width: 1 },
      rectRadius: 0.1,
    });
    if (col?.heading) {
      slide.addText(col.heading, {
        x: xs[i] + 0.25,
        y: top + 0.25,
        w: widths[i] - 0.5,
        h: 0.45,
        fontSize: 16,
        fontFace: PPT_FONT_FACE,
        color: hex(theme.accent),
        bold: true,
        margin: 0,
      });
    }
    const items = (col?.bullets || []).slice(0, 8);
    slide.addText(
      items.map((t) => ({
        text: t,
        options: {
          bullet: true,
          breakLine: true,
          fontSize: 14,
          fontFace: PPT_FONT_FACE,
          color: hex(theme.text),
          paraSpaceAfter: 8,
        },
      })),
      {
        x: xs[i] + 0.25,
        y: top + (col?.heading ? 0.85 : 0.35),
        w: widths[i] - 0.5,
        h: 3.8,
        valign: 'top',
        margin: 0,
      },
    );
  });
}

function renderKpi(slide: PptxGenJS.Slide, shapes: ShapeType, spec: SlideSpec, theme: ResolvedTheme) {
  slide.addText(spec.title, {
    x: 0.7,
    y: 0.4,
    w: 12.0,
    h: 0.55,
    fontSize: 26,
    fontFace: PPT_FONT_FACE,
    color: hex(theme.primary),
    bold: true,
    margin: 0,
  });
  if (spec.subtitle) {
    slide.addText(spec.subtitle, {
      x: 0.7,
      y: 0.95,
      w: 12.0,
      h: 0.35,
      fontSize: 14,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      margin: 0,
    });
  }

  const kpis = (spec.kpis || []).slice(0, 4);
  const n = Math.max(kpis.length, 1);
  const gap = 0.25;
  const left = 0.6;
  const usable = 12.1;
  const cardW = (usable - gap * (n - 1)) / n;
  const top = spec.subtitle ? 1.5 : 1.25;

  kpis.forEach((k, i) => {
    const x = left + i * (cardW + gap);
    slide.addShape(shapes.roundRect, {
      x,
      y: top,
      w: cardW,
      h: 1.7,
      fill: { color: hex(theme.bgAlt) },
      line: { color: hex(theme.primary), width: 1 },
      rectRadius: 0.1,
    });
    slide.addText(k.value, {
      x: x + 0.15,
      y: top + 0.3,
      w: cardW - 0.3,
      h: 0.7,
      fontSize: 28,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.accent),
      align: 'center',
      bold: true,
      margin: 0,
    });
    slide.addText(k.label, {
      x: x + 0.15,
      y: top + 1.05,
      w: cardW - 0.3,
      h: 0.4,
      fontSize: 13,
      fontFace: PPT_FONT_FACE,
      color: hex(theme.muted),
      align: 'center',
      margin: 0,
    });
  });

  const bullets = (spec.bullets || []).slice(0, 6);
  if (bullets.length) {
    const cols = bullets.length >= 3 ? 2 : 1;
    const colW = cols === 1 ? 11.5 : 5.5;
    const gapX = 0.5;
    bullets.forEach((t, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      slide.addText(t, {
        x: 0.9 + col * (colW + gapX),
        y: top + 2.05 + row * 0.55,
        w: colW,
        h: 0.5,
        fontSize: 15,
        fontFace: PPT_FONT_FACE,
        color: hex(theme.text),
        bullet: true,
        margin: 0,
        valign: 'top',
      });
    });
  }
}

function buildSlideFromSpec(pptx: PptxGenJS, input: JsonSlideInput) {
  const slide = pptx.addSlide();
  const shapes = pptx.ShapeType;
  const theme = resolveTheme(input.spec.theme);
  paintBackground(slide, shapes, theme);

  switch (input.spec.layout) {
    case 'title':
      renderTitleLike(slide, input.spec, theme, 'PRESENTATION');
      break;
    case 'section':
      renderTitleLike(slide, input.spec, theme, 'SECTION');
      break;
    case 'cards':
      renderCards(slide, shapes, input.spec, theme);
      break;
    case 'two_column':
      renderTwoColumn(slide, shapes, input.spec, theme);
      break;
    case 'kpi':
      renderKpi(slide, shapes, input.spec, theme);
      break;
    case 'bullets':
    default:
      renderBullets(slide, input.spec, theme);
      break;
  }

  addFooter(slide, theme, input.spec.footer);
  const notes = notesToParagraph(input.notes || input.spec.notes || '');
  if (notes) {
    slide.addNotes(notes);
  }
}

export async function exportJsonSlidesToPptx(
  slides: JsonSlideInput[],
  fileName = 'deck.pptx',
): Promise<void> {
  if (!slides.length) throw new Error('No slides to export');
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: 'LAYOUT_16x9', width: SLIDE_W_IN, height: SLIDE_H_IN });
  pptx.layout = 'LAYOUT_16x9';
  for (const item of slides) {
    buildSlideFromSpec(pptx, item);
  }
  await pptx.writeFile({ fileName });
}

export function parseJsonSlideInput(raw: string): SlideSpec | null {
  return parseSlideSpec(raw);
}
