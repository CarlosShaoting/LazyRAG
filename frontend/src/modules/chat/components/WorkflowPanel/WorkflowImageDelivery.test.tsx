import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import type { SlotRevision, WorkflowSession } from '@/modules/chat/store/workflowPanel';
import {
  ImageWorkflowDelivery,
  imageWorkflowDeliveryModel,
  shouldShowImageWorkflowDelivery,
} from './ImageWorkflowDelivery';

const fileActions = vi.hoisted(() => ({
  downloadArtifactFile: vi.fn(async () => undefined),
  resolveMarkdownImageUrlAsync: vi.fn(async (path: string) => `http://localhost/${path}`),
}));

vi.mock('@/modules/chat/utils/artifactFileActions', () => ({
  downloadArtifactFile: fileActions.downloadArtifactFile,
}));
vi.mock('@/modules/knowledge/utils/imageUrl', () => ({
  isExpiredSignedUrl: () => false,
  resolveCoreAssetUrl: (value: string) => value,
  resolveMarkdownImageUrlAsync: fileActions.resolveMarkdownImageUrlAsync,
}));

vi.mock('./SlotComponents', () => ({
  SlotDownloadContext: React.createContext(true),
  SlotRenderer: ({ slot }: { slot: SlotRevision }) => <div>preview:{slot.slot}</div>,
}));

function artifact(
  slot: string,
  value: Record<string, unknown>,
  index = -1,
  selected = true,
): SlotRevision {
  return {
    artifact_id: `${slot}-${index}`,
    slot_id: slot,
    slot,
    selected,
    revision: 1,
    list_index: index,
    sort_order: index < 0 ? undefined : index + 1,
    content_type: slot === 'gif_output' ? 'image' : 'json',
    artifact_value: value,
    created_at: '2026-10-21T00:00:00Z',
  };
}

function session(slots: SlotRevision[], status: WorkflowSession['status'] = 'completed'): WorkflowSession {
  return {
    session_id: 'delivery-session',
    conversation_id: 'delivery-conversation',
    workflow_id: 'image-workflow-v2',
    workflow_mode: 'dynamic',
    status,
    current_step_id: 'review_pack',
    created_at: '',
    updated_at: '',
    slots,
  };
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN');
  vi.clearAllMocks();
});
afterEach(cleanup);

describe('Image Workflow V2 final delivery', () => {
  it('keeps only the selected final artifacts for the active branch in display order', () => {
    const model = imageWorkflowDeliveryModel(session([
      artifact('route_plan', { data: { route: 'meme' } }),
      artifact('meme_brief_data', { data: { delivery_mode: 'dynamic' } }),
      artifact('static_final', { path: 'stale.png' }, 0),
      artifact('gif_output', { path: 'second.gif' }, 1),
      artifact('gif_output', { path: 'first.gif' }, 0),
      artifact('gif_output', { path: 'old.gif' }, 2, false),
      artifact('pack_review', { data: { overall_status: 'needs_rework', failed_units: ['sad'] } }),
    ]));

    expect(model.route).toBe('meme');
    expect(model.deliveryMode).toBe('dynamic');
    expect(model.artifacts.map((item) => item.filename)).toEqual(['first.gif', 'second.gif']);
  });

  it('keeps internal pack review details out of the user delivery surface', () => {
    render(<ImageWorkflowDelivery session={session([
      artifact('route_plan', { data: { route: 'meme' } }),
      artifact('meme_brief_data', { data: { delivery_mode: 'static' } }),
      artifact('static_final', { path: 'final.png' }, 0),
      artifact('pack_review', { data: {
        overall_status: 'needs_rework',
        failed_units: [{ id: 'sad', reason: 'internal review detail' }],
      } }),
    ])} />);

    expect(screen.queryByText(/failed_units|internal review detail|整包检查/)).not.toBeInTheDocument();
  });

  it('shows a deterministic summary, an ordered result area, and explicit download actions', async () => {
    render(<ImageWorkflowDelivery session={session([
      artifact('route_plan', { data: { route: 'ordinary' } }),
      artifact('ordinary_output', { path: 'final.png' }, 0),
    ])} />);

    expect(screen.getByRole('heading', { name: '最终产物' })).toBeVisible();
    expect(screen.getByText('普通生图已完成，共生成 1 个最终产物。以下均为当前有效版本。')).toBeVisible();
    expect(screen.getByRole('button', { name: '一键下载全部' })).toBeVisible();
    expect(screen.getByRole('button', { name: '下载 final.png' })).toBeVisible();
    expect(screen.getByText('preview:ordinary_output')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '一键下载全部' }));
    await waitFor(() => expect(fileActions.downloadArtifactFile).toHaveBeenCalledWith(
      'http://localhost/final.png',
      'final.png',
    ));
  });

  it('does not render before the workflow reaches completion', () => {
    const view = render(<ImageWorkflowDelivery session={session([], 'waiting')} />);
    expect(view.container).toBeEmptyDOMElement();
  });

  it('uses the same completion boundary for the delivery view and legacy-result suppression', () => {
    const waiting = session([], 'waiting');
    expect(shouldShowImageWorkflowDelivery(waiting)).toBe(false);
    expect(shouldShowImageWorkflowDelivery({
      ...waiting,
      projection: { completed: true },
    })).toBe(true);
    expect(shouldShowImageWorkflowDelivery({
      ...waiting,
      workflow_id: 'another-workflow',
      status: 'completed',
    })).toBe(false);
  });
});
