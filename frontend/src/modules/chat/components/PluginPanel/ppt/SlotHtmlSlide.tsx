import { useEffect, useMemo, useRef, useState } from 'react';
import type { SlotRevision } from '@/modules/chat/store/pluginPanel';
import { resolveCoreAssetUrl, resolveMarkdownImageUrlAsync, isExpiredSignedUrl } from '@/modules/knowledge/utils/imageUrl';
import { extractHtmlFromArtifact, htmlForStaticPreview } from './exportHtmlToPptx';
import { htmlWithInlinedEcharts } from './echartsInline';

function isSpaFallbackHtml(text: string): boolean {
  const lower = text.slice(0, 400).toLowerCase();
  return lower.includes('<div id="root"') || lower.includes('id="app"');
}

async function loadArtifactText(raw: unknown): Promise<string> {
  if (raw == null) return '';
  if (typeof raw === 'string') return raw;
  if (typeof raw !== 'object') return String(raw);
  const obj = raw as Record<string, unknown>;
  if (typeof obj.text === 'string') return obj.text;

  // Offloaded large text: { type:'text', path, size }
  if (obj.path && (obj.type === 'text' || obj.type === 'json')) {
    const pathForSign = String(obj.path ?? obj.url ?? '').trim();
    const apiUrlRaw = obj.url ? String(obj.url).trim() : '';
    const apiUrl = apiUrlRaw ? resolveCoreAssetUrl(apiUrlRaw) : '';
    const fetchUrl = apiUrl && !isExpiredSignedUrl(apiUrl)
      ? apiUrl
      : await resolveMarkdownImageUrlAsync(pathForSign);
    const response = await fetch(fetchUrl);
    if (!response.ok) throw new Error('failed to load html artifact');
    const text = await response.text();
    if (isSpaFallbackHtml(text)) throw new Error('invalid artifact content');
    return text;
  }
  return '';
}

/** Width-only scale: always 16:9, no height feedback loop / page-switch jump. */
function scaleFromWidth(containerW: number): number {
  if (!containerW || containerW < 1) return 0.5;
  return Math.max(0.15, Math.min(containerW / 1600, 1));
}

export function SlotHtmlSlide({
  slot,
  compact = false,
}: {
  slot: SlotRevision;
  compact?: boolean;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // null until first measure — avoids mounting at 0.4 then jumping to 0.5+.
  const [scale, setScale] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      const text = await loadArtifactText(slot.artifact_value);
      if (cancelled) return;
      const extracted = extractHtmlFromArtifact(text) || extractHtmlFromArtifact(slot.artifact_value);
      if (!extracted) {
        setError('Not a valid HTML slide');
        setHtml(null);
        return;
      }
      // Inline echarts so ../assets/echarts.min.js works inside srcDoc.
      const withCharts = await htmlWithInlinedEcharts(extracted);
      if (cancelled) return;
      setHtml(withCharts);
    })().catch(() => {
      if (!cancelled) {
        setError('Failed to load HTML slide');
        setHtml(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [slot.artifact_value, slot.slot_id, slot.revision]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const update = () => {
      const w = host.getBoundingClientRect().width;
      setScale(scaleFromWidth(Math.max(0, w)));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(host);
    return () => ro.disconnect();
  }, [compact]);

  const srcDoc = useMemo(() => (html ? htmlForStaticPreview(html) : ''), [html]);

  if (error) {
    return <div className='slot-html-slide slot-html-slide--error'>{error}</div>;
  }
  if (!html || scale == null) {
    return (
      <div ref={hostRef} className={`slot-html-slide${compact ? ' slot-html-slide--compact' : ''}`}>
        <div className='slot-html-slide__viewport slot-html-slide__viewport--placeholder'>
          <div className='slot-html-slide slot-html-slide--loading'>Loading slide…</div>
        </div>
      </div>
    );
  }

  return (
    <div ref={hostRef} className={`slot-html-slide${compact ? ' slot-html-slide--compact' : ''}`}>
      <div className='slot-html-slide__viewport'>
        <iframe
          className='slot-html-slide__frame'
          title={`slide-${slot.sort_order ?? slot.list_index ?? 0}`}
          sandbox='allow-scripts allow-same-origin'
          srcDoc={srcDoc}
          style={{
            width: 1600,
            height: 900,
            transform: `scale(${scale})`,
            transformOrigin: 'top left',
          }}
        />
      </div>
    </div>
  );
}
