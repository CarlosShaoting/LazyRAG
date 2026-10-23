import { DownloadOutlined } from '@ant-design/icons';
import { message } from 'antd';
import JSZip from '@progress/jszip-esm';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SlotRevision, WorkflowSession } from '@/modules/chat/store/workflowPanel';
import { downloadStream } from '@/modules/chat/utils/download';
import { downloadArtifactFile } from '@/modules/chat/utils/artifactFileActions';
import {
  isExpiredSignedUrl,
  resolveCoreAssetUrl,
  resolveMarkdownImageUrlAsync,
} from '@/modules/knowledge/utils/imageUrl';
import { SlotDownloadContext, SlotRenderer } from './SlotComponents';

const FINAL_SLOTS = new Set([
  'ordinary_output',
  'edit_candidate',
  'static_final',
  'gif_output',
]);

type DeliveryRoute = 'ordinary' | 'edit' | 'meme' | 'unknown';
type DeliveryMode = 'static' | 'dynamic' | 'unknown';

export interface ImageWorkflowDeliveryArtifact {
  id: string;
  slot: SlotRevision;
  filename: string;
}

export interface ImageWorkflowDeliveryModel {
  route: DeliveryRoute;
  deliveryMode: DeliveryMode;
  artifacts: ImageWorkflowDeliveryArtifact[];
}

export function shouldShowImageWorkflowDelivery(session: WorkflowSession): boolean {
  return session.workflow_id === 'image-workflow-v2'
    && (session.status === 'completed' || session.projection?.completed === true);
}

function artifactRecord(slot: SlotRevision | undefined): Record<string, unknown> {
  const raw = slot?.artifact_value;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const record = raw as Record<string, unknown>;
  const data = record.data;
  return data && typeof data === 'object' && !Array.isArray(data)
    ? data as Record<string, unknown>
    : record;
}

function selectedSlots(session: WorkflowSession, slotId: string): SlotRevision[] {
  return (session.slots ?? [])
    .filter((slot) => slot.slot === slotId && slot.selected !== false)
    .sort((left, right) => (
      (left.sort_order ?? left.list_index ?? 0) - (right.sort_order ?? right.list_index ?? 0)
      || left.revision - right.revision
    ));
}

function deliveryFilename(slot: SlotRevision, index: number): string {
  const raw = artifactRecord(slot);
  const declared = String(raw.filename ?? raw.name ?? '').trim();
  if (declared) return declared.replace(/[\\/]/g, '_');

  const source = String(raw.path ?? raw.url ?? '').trim().split(/[?#]/, 1)[0];
  const basename = source.split(/[\\/]/).filter(Boolean).pop();
  if (basename && /\.[a-z0-9]{2,8}$/i.test(basename)) {
    try {
      return decodeURIComponent(basename).replace(/[\\/]/g, '_');
    } catch {
      return basename.replace(/[\\/]/g, '_');
    }
  }

  const stem = slot.slot === 'ordinary_output'
    ? 'ordinary-image'
    : slot.slot === 'edit_candidate'
      ? 'edited-image'
      : slot.slot === 'gif_output'
        ? 'animated-meme'
        : 'static-meme';
  const extension = slot.slot === 'gif_output' ? 'gif' : 'png';
  return `${stem}-${index + 1}.${extension}`;
}

/** Build the immutable completion view from selected, effective final slots only. */
export function imageWorkflowDeliveryModel(session: WorkflowSession): ImageWorkflowDeliveryModel {
  const routePlan = artifactRecord(selectedSlots(session, 'route_plan').at(-1));
  const memeBrief = artifactRecord(selectedSlots(session, 'meme_brief_data').at(-1));
  const routeValue = String(routePlan.route ?? '').trim();
  const route: DeliveryRoute = routeValue === 'ordinary' || routeValue === 'edit' || routeValue === 'meme'
    ? routeValue
    : 'unknown';
  const modeValue = String(memeBrief.delivery_mode ?? '').trim();
  const deliveryMode: DeliveryMode = modeValue === 'static' || modeValue === 'dynamic'
    ? modeValue
    : 'unknown';
  const targetSlots = route === 'ordinary'
    ? ['ordinary_output']
    : route === 'edit'
      ? ['edit_candidate']
      : route === 'meme' && deliveryMode === 'dynamic'
        ? ['gif_output']
        : route === 'meme'
          ? ['static_final']
          : [...FINAL_SLOTS];
  const slots = targetSlots.flatMap((slotId) => selectedSlots(session, slotId));
  return {
    route,
    deliveryMode,
    artifacts: slots.map((slot, index) => ({
      id: slot.artifact_id ?? `${slot.slot}:${slot.list_index ?? -1}:${slot.revision}`,
      slot,
      filename: deliveryFilename(slot, index),
    })),
  };
}

async function resolveArtifactSource(slot: SlotRevision): Promise<string> {
  const raw = artifactRecord(slot);
  const path = String(raw.path ?? raw.url ?? '').trim();
  const direct = raw.url ? resolveCoreAssetUrl(String(raw.url).trim()) : '';
  if (direct && !isExpiredSignedUrl(direct)) return direct;
  if (!path) throw new Error('Artifact file is not ready');
  const resolved = await resolveMarkdownImageUrlAsync(path);
  if (!resolved) throw new Error('Artifact file is not ready');
  return resolved;
}

function uniqueFilename(filename: string, used: Set<string>): string {
  const safe = (filename || 'artifact').replace(/[\\/]/g, '_');
  const dot = safe.lastIndexOf('.');
  const stem = dot > 0 ? safe.slice(0, dot) : safe;
  const extension = dot > 0 ? safe.slice(dot) : '';
  let candidate = safe;
  let suffix = 2;
  while (used.has(candidate)) {
    candidate = `${stem}-${suffix}${extension}`;
    suffix += 1;
  }
  used.add(candidate);
  return candidate;
}

function routeTranslationKey(model: ImageWorkflowDeliveryModel): string {
  if (model.route === 'ordinary') return 'chat.imageWorkflowDeliveryRouteOrdinary';
  if (model.route === 'edit') return 'chat.imageWorkflowDeliveryRouteEdit';
  if (model.deliveryMode === 'dynamic') return 'chat.imageWorkflowDeliveryRouteDynamicMeme';
  if (model.route === 'meme') return 'chat.imageWorkflowDeliveryRouteStaticMeme';
  return 'chat.imageWorkflowDeliveryRouteUnknown';
}

export function ImageWorkflowDelivery({ session }: { session: WorkflowSession }) {
  const { t } = useTranslation();
  const model = useMemo(() => imageWorkflowDeliveryModel(session), [session]);
  const [downloading, setDownloading] = useState<string | null>(null);

  const downloadOne = useCallback(async (artifact: ImageWorkflowDeliveryArtifact) => {
    setDownloading(artifact.id);
    try {
      await downloadArtifactFile(await resolveArtifactSource(artifact.slot), artifact.filename);
    } catch {
      message.error(t('chat.imageWorkflowDeliveryDownloadFailed'));
    } finally {
      setDownloading(null);
    }
  }, [t]);

  const downloadAll = useCallback(async () => {
    if (!model.artifacts.length) return;
    if (model.artifacts.length === 1) {
      await downloadOne(model.artifacts[0]);
      return;
    }
    setDownloading('all');
    try {
      const zip = new JSZip();
      const usedNames = new Set<string>();
      for (const artifact of model.artifacts) {
        const response = await fetch(await resolveArtifactSource(artifact.slot));
        if (!response.ok) throw new Error(`Download failed: ${response.status}`);
        zip.file(uniqueFilename(artifact.filename, usedNames), await response.arrayBuffer());
      }
      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
      downloadStream(blob, `lazymind-final-artifacts-${session.session_id.slice(0, 8)}.zip`);
    } catch {
      message.error(t('chat.imageWorkflowDeliveryDownloadFailed'));
    } finally {
      setDownloading(null);
    }
  }, [downloadOne, model.artifacts, session.session_id, t]);

  if (!shouldShowImageWorkflowDelivery(session)) return null;

  return (
    <section className='image-workflow-delivery' aria-labelledby={`image-workflow-delivery-${session.session_id}`}>
      <div className='image-workflow-delivery__header'>
        <div>
          <h3 id={`image-workflow-delivery-${session.session_id}`}>{t('chat.imageWorkflowDeliveryTitle')}</h3>
          <p>
            {t('chat.imageWorkflowDeliverySummary', {
              route: t(routeTranslationKey(model)),
              count: model.artifacts.length,
            })}
          </p>
        </div>
        <button
          type='button'
          className='image-workflow-delivery__download-all'
          disabled={!model.artifacts.length || downloading !== null}
          onClick={() => { void downloadAll(); }}
        >
          <DownloadOutlined aria-hidden />
          {downloading === 'all'
            ? t('chat.imageWorkflowDeliveryDownloading')
            : t('chat.imageWorkflowDeliveryDownloadAll')}
        </button>
      </div>

      {model.artifacts.length ? (
        <div className='image-workflow-delivery__grid'>
          {model.artifacts.map((artifact, index) => (
            <article className='image-workflow-delivery__card' key={artifact.id}>
              <div className='image-workflow-delivery__preview'>
                <SlotDownloadContext.Provider value={false}>
                  <SlotRenderer
                    slot={artifact.slot}
                    cardMode
                    readOnly
                    hideImageMutationActions
                  />
                </SlotDownloadContext.Provider>
              </div>
              <div className='image-workflow-delivery__card-footer'>
                <span title={artifact.filename}>
                  {artifact.slot.caption || t('chat.imageWorkflowDeliveryItem', { index: index + 1 })}
                </span>
                <button
                  type='button'
                  disabled={downloading !== null}
                  onClick={() => { void downloadOne(artifact); }}
                  aria-label={t('chat.imageWorkflowDeliveryDownloadNamed', { name: artifact.filename })}
                >
                  <DownloadOutlined aria-hidden />
                  {downloading === artifact.id
                    ? t('chat.imageWorkflowDeliveryDownloading')
                    : t('chat.slots.download')}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className='image-workflow-delivery__empty' role='status'>
          {t('chat.imageWorkflowDeliveryEmpty')}
        </p>
      )}
    </section>
  );
}
