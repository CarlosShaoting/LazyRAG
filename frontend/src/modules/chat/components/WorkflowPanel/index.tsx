import { WorkflowApprovalActions } from './WorkflowApprovalActions';
import { ExternalWorkflowPresentationContext, type ExternalWorkflowPresentation } from './external/presentation';
import { activeExecutionTasks } from './external/useExecutionActivity';
import { executionPreview, executionPreviewTab } from './external/executionPreview';
import { workflowEmptyStateKey } from './external/workflowEmptyState';
import { useSlotCollapse } from './external/useSlotCollapse';
import { buildDocumentFooterItems } from './documentFooter';
import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { message as antdMessage, Popconfirm, Tooltip, Dropdown } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import {
  CopyOutlined,
  DownOutlined,
  CloudUploadOutlined,
  DownloadOutlined,
  ExportOutlined,
  MoreOutlined,
  InfoCircleOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons';
import { useWorkflowSession } from '@/modules/chat/hooks/useWorkflow';
import {
  buildChineseDesignRoutingSummary,
  filterWorkflowTabs,
  filterFallbackWorkflowSlots,
  filterWorkflowSlotIdsByConditions,
  workflowTabAllowsDownload,
  useWorkflowStore,
} from '@/modules/chat/store/workflowPanel';
import { isWorkflowReadyToStart, reconcileWorkflowSessionStatus } from '@/modules/chat/store/workflowStatus';
import { useTaskCenterStore, type SubAgentTask, type TaskArtifactStream } from '@/modules/chat/store/taskCenter';
import { uploadFileInChunks } from '@/modules/chat/utils/chunkUpload';
import { getLocalizedErrorMessage } from '@/components/request';
import {
  WORKFLOW_CONTRACT_VERSION,
  WorkflowSessionApi,
  type ProductStageId,
  type WorkflowRestartOnLatestRequest,
  type WorkflowTransitionRequest,
} from '@/modules/chat/utils/request';
import StateGraphModal from '@/components/StateGraphModal';
import {
  WORKFLOW_PANEL_EXPANDED_EVENT,
  WORKFLOW_PANEL_EXPANDED_STORAGE_PREFIX,
} from '@/modules/chat/constants/chat';
import type {
  WorkflowSession,
  SlotRevision,
  TabDef,
  WorkflowUI,
  SlotDef,
  CompositePanelNode,
  CompositeLayoutNode,
  CompositeColumnNode,
  InnerTabsNode,
} from '@/modules/chat/store/workflowPanel';
import {
  resolveWorkflowTabStepId,
} from './workflowTabScope';
import {
  isWriterIrSource,
  SlotRenderer,
  SlotDownloadContext,
  SlotMarkdownStream,
} from './SlotComponents';
import { SlideThumb } from './ppt/SlideThumb';
import { WorkflowTabActions } from './actions/WorkflowTabActions';
import { WorkflowPanelTabActiveContext, SlotEditingContext, type SlotFooterAction } from './slotEditingContext';
import { findWriterArtifactStream } from './writerArtifactStream';
import { resolveCompletedContinueStep, resolveWorkflowContinueAction } from './workflowContinue';
import { resolvePendingApprovalStep } from './workflowApproval';
import {
  resolveWorkflowCommandTarget,
  resolveUniqueWorkflowStartTarget,
  WorkflowCommandTargetError,
  type WorkflowCommandAction,
} from './workflowCommands';
import { presentWorkflowStepLabel, presentWorkflowTabLabel } from './workflowStepPresentation';
import { isProductWorkflow, ProductStageRelay } from './ProductStageRelay';
import {
  ProductCurrentStageView,
  ProductProjectViews,
  productWorkflowSectionKeys,
} from './ProductProjectViews';
import {
  parsePersistedPanelExpanded,
  resolveInitialPanelExpanded,
} from './panelExpansion';
import {
  parsePersistedFollowMode,
  resolveInitialFollowMode,
  resolveWorkflowActiveTabIndex,
  resolveWorkflowRealTabIndex,
  shouldShowStandaloneStepStatus,
  type WorkflowFollowMode,
} from './workflowFollowMode';
import { moveSelectedCompositePages, sameCompositePageOrder } from './compositePageReorder';
import { deliveryPending, type WorkflowActionIntent, type WorkflowControlView } from '@/modules/chat/utils/workflowControl';
import {
  filterPresentCompositeItems,
  findAlignedCompositeRevision,
} from './compositeArtifactLayout';
import './WorkflowPanel.scss';

const EMPTY_TASK_CENTER_TASKS: SubAgentTask[] = [];
const WORKFLOW_FOLLOW_MODE_STORAGE_PREFIX = 'lazymind:workflow-follow-mode:';

/** Parse a JSON intent context string and return the text field, or '' if empty/invalid. */
function parseIntentText(raw?: string): string {
  if (!raw || raw === '{}') return '';
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return (parsed as Record<string, unknown>).text as string ?? '';
  } catch {
    return '';
  }
}

/** Fallback: read latest selected text from a slot artifact. */
function parseSelectedSlotText(session: WorkflowSession, slotKey: string, includeUnselected = false): string {
  const candidates = (session.slots ?? [])
    .filter((s) => s.slot === slotKey && (includeUnselected || s.selected))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const latest = candidates[0];
  if (!latest) return '';
  const raw = latest.artifact_value;
  if (raw === null || raw === undefined) return '';
  if (typeof raw === 'string') return raw;
  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    if (obj.text !== undefined) return String(obj.text);
    if (obj.value !== undefined) return String(obj.value);
  }
  return String(raw);
}

/** IntentPopover shows global intent + per-step intent inside a floating popover. */
function IntentPopover({
  session,
  tabs,
  onClose,
}: {
  session: WorkflowSession;
  tabs: TabDef[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const wrapRef = useRef<HTMLDivElement>(null);
  const globalText =
    parseIntentText(session.intent_context)
    || parseSelectedSlotText(session, 'user_intent_summary', true);
  const stepIntents = (session.steps ?? [])
    .filter((s) => !!parseIntentText(s.intent_context))
    .map((s, idx) => ({
      idx: idx + 1,
      stepId: s.step_id,
      text: parseIntentText(s.intent_context),
      tabLabel: tabs.find((t) => getTabStepId(t) === s.step_id)?.label ?? s.step_id,
    }));

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [onClose]);

  return (
    <div className='workflow-panel__intent-popover' ref={wrapRef} role='dialog' aria-label={t('chat.workflowIntentBtn')}
      onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
      <button type='button' className='workflow-panel__intent-close' aria-label={t('common.close')} autoFocus onClick={onClose}>×</button>
      <div className='workflow-panel__intent-popover-title'>{t('chat.workflowIntentBtn')}</div>
      {globalText && (
        <div className='workflow-panel__intent-section'>
          <div className='workflow-panel__intent-section-title'>{t('chat.workflowIntentGlobalTitle')}</div>
          <div className='workflow-panel__intent-section-text'>{globalText}</div>
        </div>
      )}
      {stepIntents.length > 0 && (
        <div className='workflow-panel__intent-section'>
          <div className='workflow-panel__intent-section-title'>{t('chat.workflowIntentStepTitle')}</div>
          <div className='workflow-panel__intent-step-list'>
            {stepIntents.map((si) => (
              <div key={si.stepId} className='workflow-panel__intent-step-row'>
                <span className='workflow-panel__intent-step-badge'>{si.idx}</span>
                <span className='workflow-panel__intent-step-text'>{si.text}</span>
                <span className='workflow-panel__intent-step-arrow'>→</span>
                <span className='workflow-panel__intent-step-tab'>{si.tabLabel}</span>
              </div>
            ))}
          </div>
          <div className='workflow-panel__intent-step-note'>{t('chat.workflowIntentStepMapNote')}</div>
        </div>
      )}
      {!globalText && stepIntents.length === 0 && (
        <div className='workflow-panel__intent-empty'>{t('chat.workflowIntentEmpty')}</div>
      )}
    </div>
  );
}

export interface WorkflowPanelControlAdapter {
  control: WorkflowControlView;
  execute(intent: WorkflowActionIntent): Promise<void>;
}

interface WorkflowPanelProps {
  /** Optional external host surface; omitted by native chat callers. */
  embedded?: boolean;
  externalPresentation?: ExternalWorkflowPresentation;
  onRefresh?: () => Promise<void>;
  controlAdapter?: WorkflowPanelControlAdapter;

  conversationId: string;
  /** Called when the user clicks Continue or Retry — simulates sending a user message. */
  onSendMessage?: (text: string) => void;
  /** Called when the user clicks the reference button on a slot item. */
  onReference?: (slot: SlotRevision) => void;
  /** Called when the user clicks the Stop button during an active session. */
  onStop?: () => void;
  /** Called after a session is successfully dismissed. */
  onDismissed?: () => void;
}

/**
 * AutoSlotGrid renders all available slot revisions in a responsive grid,
 * without requiring a pre-defined UI spec.
 */
function AutoSlotGrid({
  session,
  onRefresh,
  onReference,
  readOnly,
}: {
  session: WorkflowSession;
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const externalPresentation = React.useContext(ExternalWorkflowPresentationContext);
  if (!session.slots || session.slots.length === 0) {
    return (
      <div className='workflow-panel__empty' role='status' aria-live='polite'>
        <span>{t(externalPresentation ? workflowEmptyStateKey(session, session.current_step_id) : 'chat.workflowWaitingForResults')}</span>
      </div>
    );
  }

  const bySlot: Record<string, SlotRevision[]> = {};
  for (const s of session.slots) {
    if (!s.selected) continue;
    if (!bySlot[s.slot_id]) bySlot[s.slot_id] = [];
    bySlot[s.slot_id].push(s);
  }

  return (
    <div className='workflow-panel__auto-grid'>
      {Object.entries(bySlot).map(([slotId, revisions]) => (
        <div key={slotId} className='workflow-panel__slot-group'>
          <span className='workflow-panel__slot-label'>{slotId}</span>
          <div className='workflow-panel__slot-items'>
            {revisions.map((rev) => (
              <SlotRenderer
                key={`${rev.slot_id}-${rev.list_index ?? -1}`}
                slot={rev}
                sessionId={session.session_id}
                slotId={slotId}
                revisionCount={rev.revision_count}
                onRefresh={onRefresh}
                onReference={onReference}
                readOnly={readOnly}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * CompositeSlotGrid renders a composite-layout tab where multiple slots are
 * aligned by sort_order. Each row corresponds to one sort_order value; within
 * a row, columns are laid out according to composite_layout.
 */

// ---------------------------------------------------------------------------
// Helpers for composite_layout parsing
// ---------------------------------------------------------------------------

function isInnerTabsNode(node: CompositeLayoutNode): node is InnerTabsNode {
  return typeof node === 'object' && node !== null && 'tabs' in node;
}

function isColumnNode(node: CompositeLayoutNode): node is CompositeColumnNode {
  return typeof node === 'object' && node !== null && 'slot' in node;
}

/** Resolve a leaf node to { slotId, weight }. Returns null for unknown shapes. */
function resolveColumnSlotId(
  node: CompositeLayoutNode,
): { slotId: string | InnerTabsNode; weight: number } | null {
  if (typeof node === 'string') {
    return { slotId: node, weight: 1 };
  }
  if (isColumnNode(node)) {
    if (node.slot === undefined) return null;
    return { slotId: node.slot, weight: node.weight ?? 1 };
  }
  return null;
}

/**
 * Flatten a format-C CompositePanelNode tree into a flat column list.
 * For 'row' nodes, children become columns proportioned by weight.
 * For 'column' nodes at root, we treat the whole tree as one column (single slot fallback).
 * tabs[] leaf nodes become an InnerTabsNode for backward compat rendering.
 */
function flattenFormatCNode(
  node: import('@/modules/chat/store/workflowPanel').CompositePanelNode,
  weight: number,
): Array<{ slotId: string | InnerTabsNode; weight: number }> {
  if (node.slot) {
    return [{ slotId: node.slot, weight }];
  }
  if (node.tabs && node.tabs.length > 0) {
    // Convert format-C tabs (string[]) to legacy InnerTabsNode for rendering
    const innerTabsNode: InnerTabsNode = {
      tabs: node.tabs.map((slotId) => slotId as CompositeLayoutNode),
    };
    return [{ slotId: innerTabsNode, weight }];
  }
  if (node.direction === 'row' && node.children) {
    const childWeight = node.children.reduce((s, c) => s + (c.weight ?? 1), 0);
    return node.children.flatMap((child) =>
      flattenFormatCNode(child, ((child.weight ?? 1) / childWeight) * weight),
    );
  }
  // column direction or unknown: render as a single nested block — just flatten children
  if (node.direction === 'column' && node.children) {
    // For now, render only the first child in column containers (rows handle horizontal splitting)
    // A full nested column render would require CSS grid nesting, handled in the tree renderer.
    return node.children.flatMap((child) => flattenFormatCNode(child, child.weight ?? 1));
  }
  return [];
}

/** Build the effective column list from composite_layout (or fall back to slot ids). */
function buildColumns(
  tab: TabDef,
): Array<{ slotId: string | InnerTabsNode; weight: number }> {
  const layout = tab.composite_layout;
  if (!layout) {
    return tab.slots.map((s) => ({ slotId: s.id, weight: 1 }));
  }

  // Format C: { direction, children } tree
  if (!Array.isArray(layout) && typeof layout === 'object' && 'direction' in layout) {
    const result = flattenFormatCNode(
      layout as import('@/modules/chat/store/workflowPanel').CompositePanelNode,
      1,
    );
    return result.length > 0 ? result : tab.slots.map((s) => ({ slotId: s.id, weight: 1 }));
  }

  // Legacy array format
  if (!Array.isArray(layout) || layout.length === 0) {
    return tab.slots.map((s) => ({ slotId: s.id, weight: 1 }));
  }
  const first = layout[0];
  const cols =
    Array.isArray(first)
      ? (first as CompositeLayoutNode[])
      : layout as CompositeLayoutNode[];
  return cols
    .map((n) => resolveColumnSlotId(n))
    .filter((c): c is NonNullable<typeof c> => c !== null);
}

function getTabStepId(tab: TabDef): string | undefined {
  return tab.step_id ?? tab.id;
}

const LEGACY_DESIGN_ROUTER_SLOT_IDS = [
  'design_routing_summary',
  'design_light_evidence',
  'design_heavy_evidence',
];

function isDesignRouterTab(tab: TabDef): boolean {
  const slotIds = new Set(tab.slots.map((slot) => slot.id));
  return LEGACY_DESIGN_ROUTER_SLOT_IDS.every((slotId) => slotIds.has(slotId));
}

/** Keep pre-v12 product sessions compatible with the router's grouped step scope. */
function getTabScopeStepIds(tab: TabDef): string[] {
  if (tab.status_step_ids?.length) return tab.status_step_ids;
  if (isDesignRouterTab(tab)) {
    return [
      tab.step_id ?? 'route_design_scope',
      'collect_design_light_evidence',
      'collect_design_heavy_evidence',
    ];
  }
  return tab.step_id ? [tab.step_id] : [];
}

/** Backfill conditional evidence display for sessions created before the rule entered workflow.yaml. */
function getEffectiveCompositeBehavior(tab: TabDef): TabDef['composite_behavior'] {
  if (tab.composite_behavior?.visible_when?.length || !isDesignRouterTab(tab)) {
    return tab.composite_behavior;
  }
  return {
    ...tab.composite_behavior,
    visible_when: [
      { slot: 'design_light_evidence', material: 'design_routing_record', path: 'data.overall_effort', equals: 'light' },
      { slot: 'design_heavy_evidence', material: 'design_routing_record', path: 'data.overall_effort', equals: 'heavy' },
    ],
  };
}

/**
 * Lock slot editing only while the plugin session is actively running.
 * When idle (waiting / failed / completed), editable artifact formats stay editable
 * according to their workflow readOnly setting, so the user can revise and re-run
 * a later step from the updated content.
 */
function isWorkflowSessionReadOnly(
  session: WorkflowSession,
  autoRunning = false,
): boolean {
  return autoRunning || session.status === 'active';
}
function revisionMatchesTabScope(
  session: WorkflowSession,
  tab: TabDef,
  slot: SlotRevision,
  scope: 'selected' | 'tab',
): boolean {
  if (scope === 'selected') {
    return Boolean(slot.selected);
  }
  const declaredStepIds = getTabScopeStepIds(tab);
  if (declaredStepIds.length > 0) return Boolean(slot.step_id && declaredStepIds.includes(slot.step_id));
  const isStepTab = session.steps?.some((s) => s.step_id === tab.id);
  if (isStepTab) {
    return slot.step_id === tab.id;
  }
  return Boolean(slot.selected);
}

/** Slot ids that currently have at least one revision under the tab's empty-column scope. */
function getPresentSlotIds(
  tab: TabDef,
  session: WorkflowSession,
  scope: 'selected' | 'tab' = 'selected',
): Set<string> {
  const participating = new Set(tab.slots.map((s) => s.id));
  const present = new Set<string>();
  for (const slot of session.slots ?? []) {
    if (!participating.has(slot.slot)) continue;
    if (!revisionMatchesTabScope(session, tab, slot, scope)) continue;
    present.add(slot.slot);
  }
  return present;
}

/**
 * Resolve which slot ids should be visible for a tab from `composite_behavior`.
 * Returns null when no behavior is declared (show all configured columns/slots).
 */
function resolveVisibleSlotIds(
  tab: TabDef,
  session: WorkflowSession,
): Set<string> | null {
  const behavior = getEffectiveCompositeBehavior(tab);
  if (!behavior) return null;

  const scope = behavior.empty_column_scope === 'tab' ? 'tab' : 'selected';
  const present = getPresentSlotIds(tab, session, scope);
  const allowed = new Set(filterWorkflowSlotIdsByConditions(
    tab.slots.map((slot) => slot.id),
    session.slots,
    behavior.visible_when,
  ));

  for (const group of behavior.mutually_exclusive ?? []) {
    const members = (group.slots ?? []).filter((id) => allowed.has(id));
    if (members.length < 2) continue;
    const prefer = (group.prefer?.length ? group.prefer : members)
      .filter((id) => members.includes(id));
    const winner = prefer.find((id) => present.has(id))
      ?? members.find((id) => present.has(id));
    if (!winner) continue;
    for (const id of members) {
      if (id !== winner) allowed.delete(id);
    }
  }

  if (behavior.hide_empty_columns) {
    for (const id of [...allowed]) {
      if (!present.has(id)) allowed.delete(id);
    }
  }

  return allowed;
}

function filterColumnsByVisibleSlots(
  columns: Array<{ slotId: string | InnerTabsNode; weight: number }>,
  visible: Set<string> | null,
): Array<{ slotId: string | InnerTabsNode; weight: number }> {
  if (!visible) return columns;
  const filtered = columns.filter((col) => {
    if (typeof col.slotId !== 'string') return true;
    return visible.has(col.slotId);
  });
  return filtered;
}

function getTabSlotRevisions(
  session: WorkflowSession,
  tab: TabDef,
  artifactKey: string,
): SlotRevision[] {
  const slots = session.slots ?? [];
  const declaredStepIds = getTabScopeStepIds(tab);
  if (declaredStepIds.length > 0) {
    return slots.filter((s) => s.slot === artifactKey && Boolean(s.step_id && declaredStepIds.includes(s.step_id)));
  }
  const isStepTab = session.steps?.some((s) => s.step_id === tab.id);
  if (isStepTab) {
    return slots.filter((s) => s.slot === artifactKey && s.step_id === tab.id);
  }
  return slots.filter((s) => s.slot === artifactKey && s.selected);
}

/** Render legacy model-authored English route summaries from their structured source record. */
function localizeDesignRoutingSummaryRevisions(
  session: WorkflowSession,
  artifactKey: string,
  revisions: SlotRevision[],
): SlotRevision[] {
  if (artifactKey !== 'design_routing_summary') return revisions;
  const routingRecord = (session.slots ?? [])
    .filter((slot) => slot.selected && slot.slot === 'design_routing_record')
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0];
  const chineseSummary = buildChineseDesignRoutingSummary(routingRecord?.artifact_value);
  if (!chineseSummary) return revisions;

  return revisions.map((revision) => {
    const raw = revision.artifact_value;
    const existingText = typeof raw === 'string'
      ? raw
      : raw && typeof raw === 'object'
        ? String((raw as Record<string, unknown>).text ?? '')
        : '';
    if (!revision.selected || (!existingText.includes('Design Routing Summary') && !existingText.includes('Handoff:'))) {
      return revision;
    }
    return {
      ...revision,
      artifact_value: raw && typeof raw === 'object' && !Array.isArray(raw)
        ? { ...raw, text: chineseSummary }
        : { text: chineseSummary },
    };
  });
}

function isStructuredArtifactRevision(slot: SlotRevision): boolean {
  if (slot.content_type === 'json') return true;
  const raw = slot.artifact_value;
  if (!raw || typeof raw !== 'object') return false;
  if (raw.type === 'json') return true;
  const source = String(raw.filename ?? raw.name ?? raw.path ?? raw.url ?? '');
  const normalized = source.split(/[?#]/, 1)[0].toLowerCase();
  return isWriterIrSource(normalized) || normalized.endsWith('.json');
}

/** Prefer a structured sibling artifact over its Markdown export when both exist. */
function resolvePreferredStructuredSlotDefs(tab: TabDef, session: WorkflowSession): SlotDef[] {
  const declaredSlotIds = new Set(tab.slots.map((slot) => slot.id));

  return tab.slots.flatMap((slotDef) => {
    if (!slotDef.id.endsWith('_md')) return [slotDef];
    const irSlotId = slotDef.id.slice(0, -3);
    const hasIRArtifact = getTabSlotRevisions(session, tab, irSlotId)
      .some(isStructuredArtifactRevision);
    if (!hasIRArtifact) return [slotDef];
    if (declaredSlotIds.has(irSlotId)) return [];

    return [{
      ...slotDef,
      id: irSlotId,
      label: slotDef.label.replace(/\s*[（(]\s*markdown\s*[）)]/i, '').trim() || irSlotId,
      type: 'text',
    }];
  });
}

/** Pick the first HTML material in this composite row for its filmstrip thumbnail. */
function findCompositeHtmlRevision(
  session: WorkflowSession,
  tab: TabDef,
  sortOrder: number,
): SlotRevision | undefined {
  for (const slot of tab.slots) {
    if (slot.widget?.widgetType !== 'html-slide') continue;
    const revision = findSlotRevision(session, tab, slot.id, sortOrder);
    if (revision) return revision;
  }
  return undefined;
}

/** Get all distinct sort_orders present across the participating slots. */
function getCompositeRows(
  tab: TabDef,
  session: WorkflowSession,
): number[] {
  const participating = new Set(tab.slots.map((s) => s.id));
  const orders = new Set<number>();
  const configuredStepIds = getTabScopeStepIds(tab);
  const scopeStepIds = configuredStepIds.length > 0
    ? configuredStepIds
    : session.steps?.some((s) => s.step_id === tab.id)
      ? [tab.id]
      : [];
  for (const slot of session.slots ?? []) {
    const matchesTabStep = scopeStepIds.length > 0
      ? Boolean(slot.step_id && scopeStepIds.includes(slot.step_id))
      : slot.selected;
    if (matchesTabStep && participating.has(slot.slot) && slot.sort_order !== undefined) {
      orders.add(slot.sort_order);
    }
  }
  return Array.from(orders).sort((a, b) => a - b);
}

/** Find a slot revision for (slot, sort_order). */
function findSlotRevision(
  session: WorkflowSession,
  tab: TabDef,
  artifactKey: string,
  sortOrder: number,
): SlotRevision | undefined {
  const revisions = getTabSlotRevisions(session, tab, artifactKey).filter(
    (slot) => slot.slot === artifactKey,
  );
  return findAlignedCompositeRevision(
    revisions,
    sortOrder,
    tab.composite_behavior?.repeat_single_slots?.includes(artifactKey) ?? false,
  );
}

// ---------------------------------------------------------------------------
// InnerTabsCell: renders an {tabs: [...]} node for a single row
// ---------------------------------------------------------------------------

function InnerTabsCell({
  tabsNode,
  tab,
  session,
  slotDefs,
  sortOrder,
  onRefresh,
  onReference,
  hideImageMutationActions,
  readOnly,
}: {
  tabsNode: InnerTabsNode;
  tab: TabDef;
  session: WorkflowSession;
  slotDefs: SlotDef[];
  sortOrder: number;
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  hideImageMutationActions?: boolean;
  readOnly?: boolean;
}) {
  const [activeIdx, setActiveIdx] = useState(0);

  const innerSlotIds = tabsNode.tabs
    .map((n) => (typeof n === 'string' ? n : isColumnNode(n) ? (typeof n.slot === 'string' ? n.slot : null) : null))
    .filter((id): id is string => id !== null)
    .filter((slotId) => Boolean(findSlotRevision(session, tab, slotId, sortOrder)));

  useEffect(() => {
    if (activeIdx >= innerSlotIds.length) setActiveIdx(0);
  }, [activeIdx, innerSlotIds.length]);

  if (innerSlotIds.length === 0) {
    return <div className='composite-cell__empty'>—</div>;
  }

  return (
    <div className='composite-cell__inner-tabs'>
      <div className='composite-cell__inner-tab-bar' role='tablist'>
        {innerSlotIds.map((slotId, i) => {
          const def = slotDefs.find((s) => s.id === slotId);
          return (
            <button
              key={slotId}
              role='tab'
              aria-selected={i === activeIdx}
              className={`composite-cell__inner-tab-btn${i === activeIdx ? ' composite-cell__inner-tab-btn--active' : ''}`}
              onClick={() => setActiveIdx(i)}
              type='button'
            >
              {def?.label ?? slotId}
            </button>
          );
        })}
      </div>
      {innerSlotIds.map((slotId, i) => {
        const def = slotDefs.find((s) => s.id === slotId);
        const artifactKey = def?.id ?? slotId;
        const rev = findSlotRevision(session, tab, artifactKey, sortOrder);
        return (
          <div key={slotId} role='tabpanel' hidden={i !== activeIdx}>
            {rev ? (
              <SlotRenderer
                slot={rev}
                widget={def?.widget}
                expectedType={def?.type}
                sessionId={session.session_id}
                slotId={slotId}
                revisionCount={rev.revision_count}
                onRefresh={onRefresh}
                onReference={onReference}
                hideImageMutationActions={hideImageMutationActions}
                readOnly={readOnly}
              />
            ) : (
              <div className='composite-cell__empty'>—</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompositeSlotGrid
// ---------------------------------------------------------------------------

type PageBarPosition = 'top' | 'bottom' | 'left' | 'right';

function CompositeThumbnailRail({
  position,
  pages,
  currentPage,
  onChange,
  onReorder,
  reordering = false,
  tab,
  session,
}: {
  position: PageBarPosition;
  pages: number[];
  currentPage: number;
  onChange: (page: number) => void;
  onReorder?: (nextPages: number[]) => void | Promise<void>;
  reordering?: boolean;
  tab: TabDef;
  session: WorkflowSession;
}) {
  const { t } = useTranslation();
  const isCol = position === 'left' || position === 'right';
  const idx = Math.max(0, pages.indexOf(currentPage));
  const dragPagesRef = useRef<Set<number>>(new Set());
  const [insertIdx, setInsertIdx] = useState<number | null>(null);
  const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
  const [draggingPages, setDraggingPages] = useState<Set<number>>(new Set());

  useEffect(() => {
    const available = new Set(pages);
    setSelectedPages((selected) => {
      const next = new Set(Array.from(selected).filter((page) => available.has(page)));
      if (next.size === selected.size) return selected;
      return next;
    });
  }, [pages.join(',')]);

  const computeInsertIdx = useCallback((event: React.DragEvent, itemIdx: number) => {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    if (isCol) return event.clientY < rect.top + rect.height / 2 ? itemIdx : itemIdx + 1;
    return event.clientX < rect.left + rect.width / 2 ? itemIdx : itemIdx + 1;
  }, [isCol]);

  const handlePageClick = (sortOrder: number, event: React.MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedPages((selected) => {
        const next = new Set(selected);
        if (next.has(sortOrder)) next.delete(sortOrder);
        else next.add(sortOrder);
        return next;
      });
    } else {
      setSelectedPages(new Set([sortOrder]));
    }
    onChange(sortOrder);
  };

  const handleDragStart = (sortOrder: number, event: React.DragEvent) => {
    if (!onReorder || reordering) return;
    const moving = selectedPages.has(sortOrder)
      ? new Set(selectedPages)
      : new Set([sortOrder]);
    dragPagesRef.current = moving;
    setSelectedPages(moving);
    setDraggingPages(moving);
    event.dataTransfer.setData(
      'application/x-workflow-page-sort',
      JSON.stringify(Array.from(moving)),
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (pageIdx: number, event: React.DragEvent) => {
    if (!onReorder || dragPagesRef.current.size === 0) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    setInsertIdx(computeInsertIdx(event, pageIdx));
  };

  const resetDrag = () => {
    dragPagesRef.current = new Set();
    setInsertIdx(null);
    setDraggingPages(new Set());
  };

  const handleDrop = async (pageIdx: number, event: React.DragEvent) => {
    event.preventDefault();
    const moving = dragPagesRef.current;
    const gapIdx = computeInsertIdx(event, pageIdx);
    resetDrag();
    if (!moving.size || !onReorder) return;
    const next = moveSelectedCompositePages(pages, moving, gapIdx);
    if (sameCompositePageOrder(next, pages)) return;
    await onReorder(next);
    setSelectedPages(new Set());
  };

  const canDrag = Boolean(onReorder) && !reordering;
  const hasAnyHtmlPreview = pages.some((sortOrder) =>
    Boolean(findCompositeHtmlRevision(session, tab, sortOrder)),
  );

  return (
    <div
      className={[
        'composite-thumb-rail',
        `composite-thumb-rail--${isCol ? 'col' : 'row'}`,
        `composite-thumb-rail--${position}`,
        !hasAnyHtmlPreview ? 'composite-thumb-rail--compact' : '',
      ].filter(Boolean).join(' ')}
      onDragLeave={canDrag ? (event) => {
        if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) {
          setInsertIdx(null);
        }
      } : undefined}
    >
      <div className='composite-thumb-rail__nav'>
        <button
          type='button'
          className='composite-thumb-rail__arrow'
          disabled={idx <= 0 || reordering}
          onClick={() => idx > 0 && onChange(pages[idx - 1])}
          aria-label={t('chat.workflowPreviousPage')}
        >
          {isCol ? '↑' : '←'}
        </button>
        <div
          className={`composite-thumb-rail__list composite-thumb-rail__list--${isCol ? 'col' : 'row'}`}
          role='list'
        >
          {canDrag && <div className={`composite-thumb-rail__insert${insertIdx === 0 ? ' composite-thumb-rail__insert--active' : ''}`} aria-hidden='true' />}
          {pages.map((sortOrder, pageIdx) => {
            const revision = findCompositeHtmlRevision(session, tab, sortOrder);
            const hasHtmlPreview = Boolean(revision);
            const selected = selectedPages.has(sortOrder);
            const dragging = draggingPages.has(sortOrder);
            return (
              <React.Fragment key={`${sortOrder}-${pageIdx}`}>
                <button
                  type='button'
                  role='listitem'
                  draggable={canDrag}
                  className={[
                    'composite-thumb-rail__item',
                    sortOrder === currentPage ? 'composite-thumb-rail__item--active' : '',
                    selected ? 'composite-thumb-rail__item--selected' : '',
                    canDrag ? 'composite-thumb-rail__item--draggable' : '',
                    dragging ? 'composite-thumb-rail__item--dragging' : '',
                    !hasHtmlPreview ? 'composite-thumb-rail__item--fallback' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={(event) => handlePageClick(sortOrder, event)}
                  onDragStart={(event) => handleDragStart(sortOrder, event)}
                  onDragOver={(event) => handleDragOver(pageIdx, event)}
                  onDrop={(event) => { void handleDrop(pageIdx, event); }}
                  onDragEnd={resetDrag}
                  title={canDrag ? t('chat.workflowPageMultiSelectDragHint') : undefined}
                  aria-label={t('chat.workflowRowAria', { index: pageIdx + 1 })}
                  aria-current={sortOrder === currentPage ? 'true' : undefined}
                  aria-pressed={selected}
                >
                  {hasHtmlPreview && <span className='composite-thumb-rail__badge'>{pageIdx + 1}</span>}
                  {selectedPages.size > 1 && selected && (
                    <span className='composite-thumb-rail__selection-badge' aria-hidden='true'>
                      {selectedPages.size}
                    </span>
                  )}
                  <span
                    className={`composite-thumb-rail__preview${hasHtmlPreview ? '' : ' composite-thumb-rail__preview--fallback'}`}
                    aria-hidden='true'
                  >
                    {revision ? (
                      <SlideThumb slot={revision} sessionId={session.session_id} />
                    ) : (
                      <span className='composite-thumb-rail__page-number'>{pageIdx + 1}</span>
                    )}
                  </span>
                </button>
                {canDrag && <div className={`composite-thumb-rail__insert${insertIdx === pageIdx + 1 ? ' composite-thumb-rail__insert--active' : ''}`} aria-hidden='true' />}
              </React.Fragment>
            );
          })}
        </div>
        <button
          type='button'
          className='composite-thumb-rail__arrow'
          disabled={idx >= pages.length - 1 || reordering}
          onClick={() => idx < pages.length - 1 && onChange(pages[idx + 1])}
          aria-label={t('chat.workflowNextPage')}
        >
          {isCol ? '↓' : '→'}
        </button>
      </div>
    </div>
  );
}

function CompositeSlotGrid({
  tab,
  session,
  onRefresh,
  onReference,
  onFocusSortOrder,
  readOnly,
}: {
  tab: TabDef;
  session: WorkflowSession;
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  onFocusSortOrder?: (sortOrder: number | undefined) => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const externalPresentation = React.useContext(ExternalWorkflowPresentationContext);
  const reorderSlotItems = useWorkflowStore((state) => state.reorderSlotItems);
  const rows = getCompositeRows(tab, session);
  const columns = filterColumnsByVisibleSlots(
    buildColumns(tab),
    resolveVisibleSlotIds(tab, session),
  );
  const hideEmptyCells = Boolean(tab.composite_behavior?.hide_empty_columns);
  const hideImageMutationActions = tab.id === 'result';

  // Compute total weight for flex proportions.
  const totalWeight = columns.reduce((s, c) => s + c.weight, 0) || 1;
  const pageBarPosition = tab.composite_tab_position as PageBarPosition | undefined;
  const paged = Boolean(pageBarPosition);
  const stackCompositeCells = Boolean(
    tab.composite_layout
      && !Array.isArray(tab.composite_layout)
      && tab.composite_layout.direction === 'column',
  );
  const [slideExpanded, setSlideExpanded] = useState(false);
  const [currentPage, setCurrentPage] = useState<number | null>(null);
  const [reorderError, setReorderError] = useState<string | null>(null);
  const [reordering, setReordering] = useState(false);

  useEffect(() => {
    if (!paged) return;
    if (!rows.length) {
      setCurrentPage(null);
      return;
    }
    setCurrentPage((page) => page != null && rows.includes(page) ? page : rows[0]);
  }, [paged, rows.join(',')]);

  useEffect(() => {
    if (paged) onFocusSortOrder?.(currentPage ?? undefined);
  }, [paged, currentPage, onFocusSortOrder]);

  const activePage = currentPage ?? rows[0];
  const reorderableCompositeSlotIds = tab.slots
    .filter((slot) => slot.cardinality === 'list' && slot.ordered)
    .map((slot) => slot.id)
    .filter((slotId) => getTabSlotRevisions(session, tab, slotId)
      .filter((revision) => revision.selected && revision.list_index !== undefined)
      .length > 1);
  const canReorderPages = paged
    && rows.length > 1
    && reorderableCompositeSlotIds.length > 0
    && !readOnly;

  const handlePageReorder = useCallback(async (nextPages: number[]) => {
    if (!canReorderPages || reordering || nextPages.length !== rows.length) return;
    if (nextPages.every((page, index) => page === rows[index])) return;

    const focusedVisualIdx = Math.max(0, nextPages.indexOf(activePage));
    // Composite pagination aligns every participating ordered-list slot by its
    // visual sort_order. Reorder all such slots together so page identity stays
    // aligned for text, images, HTML previews, notes, and future widget types.
    setReordering(true);
    setReorderError(null);
    try {
      for (const slotId of reorderableCompositeSlotIds) {
        const revisions = getTabSlotRevisions(session, tab, slotId)
          .filter((revision) => revision.selected
            && revision.sort_order !== undefined
            && revision.list_index !== undefined)
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        if (revisions.length < 2) continue;
        const bySortOrder = new Map(revisions.map((revision) => [revision.sort_order as number, revision]));
        const nextListOrder = nextPages
          .map((sortOrder) => bySortOrder.get(sortOrder)?.list_index)
          .filter((listIndex): listIndex is number => listIndex !== undefined);
        if (nextListOrder.length !== revisions.length) {
          throw new Error(t('chat.workflowPageReorderFailed'));
        }
        await reorderSlotItems(
          session.session_id,
          slotId,
          nextListOrder,
          revisions[0]?.order_version ?? 0,
        );
      }
      await onRefresh?.();
      const nextFocusedPage = focusedVisualIdx + 1;
      setCurrentPage(nextFocusedPage);
      onFocusSortOrder?.(nextFocusedPage);
    } catch (error) {
      setReorderError(error instanceof Error ? error.message : t('chat.workflowPageReorderFailed'));
    } finally {
      setReordering(false);
    }
  }, [activePage, canReorderPages, onFocusSortOrder, onRefresh, reorderSlotItems, reordering, reorderableCompositeSlotIds, rows, session, tab, t]);

  if (rows.length === 0) {
    return (
      <div className='workflow-panel__empty' role='status' aria-live='polite'>
        <span>{t(externalPresentation ? workflowEmptyStateKey(session, resolveWorkflowTabStepId(tab, session.steps)) : 'chat.workflowWaitingForResults')}</span>
      </div>
    );
  }

  const renderSlotCell = (
    slotId: string,
    sortOrder: number,
    key: React.Key,
    style?: React.CSSProperties,
  ) => {
    const def = tab.slots.find((slot) => slot.id === slotId);
    const rev = findSlotRevision(session, tab, def?.id ?? slotId, sortOrder);
    if (!rev && hideEmptyCells) return null;
    return (
      <div key={key} className='composite-grid__cell' style={style}>
        {def?.label && <span className='composite-grid__cell-label'>{def.label}</span>}
        {rev ? (
          <SlotRenderer
            slot={rev}
            widget={def?.widget}
            slideNavigation={paged ? {
              index: rows.indexOf(activePage),
              total: rows.length,
              expanded: slideExpanded,
              onExpandedChange: setSlideExpanded,
              onChange: (index) => {
                if (index >= 0 && index < rows.length) setCurrentPage(rows[index]);
              },
            } : undefined}
            expectedType={def?.type}
            sessionId={session.session_id}
            slotId={slotId}
            revisionCount={rev.revision_count}
            onRefresh={onRefresh}
            onReference={onReference}
            hideImageMutationActions={hideImageMutationActions}
            readOnly={readOnly}
          />
        ) : (
          <div className='composite-grid__cell-empty'>—</div>
        )}
      </div>
    );
  };

  const hasNestedContainer = (node: CompositePanelNode): boolean =>
    Boolean(node.children?.some((child) => child.direction || hasNestedContainer(child)));

  const formatCLayout = tab.composite_layout && !Array.isArray(tab.composite_layout)
    ? tab.composite_layout
    : undefined;
  const nodeHasRevision = (node: CompositePanelNode, sortOrder: number): boolean => {
    if (node.slot) return Boolean(findSlotRevision(session, tab, node.slot, sortOrder));
    if (node.tabs?.length) {
      return node.tabs.some((slotId) => Boolean(findSlotRevision(session, tab, slotId, sortOrder)));
    }
    return Boolean(node.children?.some((child) => nodeHasRevision(child, sortOrder)));
  };
  const renderNestedComposite = (
    node: CompositePanelNode,
    sortOrder: number,
    path: string,
    root = false,
  ): React.ReactNode => {
    if (node.slot) return renderSlotCell(node.slot, sortOrder, path);
    if (node.tabs?.length) {
      const tabSlotIds = (node.tabs as unknown[])
        .map((item) => typeof item === 'string'
          ? item
          : String((item as { slot?: string })?.slot ?? ''))
        .filter(Boolean);
      return (
        <div key={path} className='composite-grid__cell'>
          <InnerTabsCell
            tabsNode={{ tabs: tabSlotIds }}
            tab={tab}
            session={session}
            slotDefs={tab.slots}
            sortOrder={sortOrder}
            onRefresh={onRefresh}
            onReference={onReference}
            hideImageMutationActions={hideImageMutationActions}
            readOnly={readOnly}
          />
        </div>
      );
    }
    if (!node.direction || !node.children?.length) {
      return hideEmptyCells ? null : <div key={path} className='composite-grid__cell-empty'>—</div>;
    }
    const children = filterPresentCompositeItems(
      node.children,
      (child) => nodeHasRevision(child, sortOrder),
      hideEmptyCells,
    );
    if (children.length === 0) return null;
    return (
      <div
        key={path}
        className={`composite-grid__tree composite-grid__tree--${node.direction}${root ? ' composite-grid__tree--root' : ''}`}
      >
        {children.map((child, index) => (
          <div
            key={`${path}-${index}`}
            className='composite-grid__tree-child'
            style={{ flex: `${child.weight ?? 1} 1 0` }}
          >
            {renderNestedComposite(child, sortOrder, `${path}-${index}`)}
          </div>
        ))}
      </div>
    );
  };

  const renderRow = (sortOrder: number) => {
    const rowColumns = filterPresentCompositeItems(
      columns,
      (column) => {
        if (typeof column.slotId === 'string') {
          return Boolean(findSlotRevision(session, tab, column.slotId, sortOrder));
        }
        return column.slotId.tabs.some((node) => {
          const slotId = typeof node === 'string'
            ? node
            : isColumnNode(node) && typeof node.slot === 'string'
              ? node.slot
              : undefined;
          return slotId ? Boolean(findSlotRevision(session, tab, slotId, sortOrder)) : false;
        });
      },
      hideEmptyCells,
    );
    const rowTotalWeight = rowColumns.reduce((sum, column) => sum + column.weight, 0) || totalWeight;
    return (
        <div
          key={sortOrder}
          className={`composite-grid__row${formatCLayout && hasNestedContainer(formatCLayout) ? ' composite-grid__row--tree' : stackCompositeCells ? ' composite-grid__row--stack' : ''}`}
          onClick={() => onFocusSortOrder?.(sortOrder)}
          role='button'
          tabIndex={0}
          aria-label={t('chat.workflowRowAria', { index: sortOrder })}
        >
          {formatCLayout && hasNestedContainer(formatCLayout)
            ? renderNestedComposite(formatCLayout, sortOrder, `page-${sortOrder}`, true)
            : rowColumns.map((col, colIdx) => {
            const flexBasis = `${(col.weight / rowTotalWeight) * 100}%`;
            if (isInnerTabsNode(col.slotId)) {
              return (
                <div
                  key={colIdx}
                  className='composite-grid__cell'
                  style={{ flexBasis, flexGrow: col.weight, flexShrink: 1 }}
                >
                  <InnerTabsCell
                    tabsNode={col.slotId}
                    tab={tab}
                    session={session}
                    slotDefs={tab.slots}
                    sortOrder={sortOrder}
                    onRefresh={onRefresh}
                    onReference={onReference}
                    hideImageMutationActions={hideImageMutationActions}
                    readOnly={readOnly}
                  />
                </div>
              );
            }
            const slotId = col.slotId as string;
            return renderSlotCell(slotId, sortOrder, slotId, {
              flexBasis,
              flexGrow: col.weight,
              flexShrink: 1,
            });
          })}
        </div>
    );
  };

  if (!paged) {
    return <div className='composite-grid'>{rows.map(renderRow)}</div>;
  }

  const rail = (
    <CompositeThumbnailRail
      position={pageBarPosition!}
      pages={rows}
      currentPage={activePage}
      onChange={setCurrentPage}
      onReorder={canReorderPages ? handlePageReorder : undefined}
      reordering={reordering}
      tab={tab}
      session={session}
    />
  );

  return (
    <div className='composite-shell composite-shell--paged'>
      <div className={`composite-with-pagebar composite-with-pagebar--${pageBarPosition}`}>
        {(pageBarPosition === 'top' || pageBarPosition === 'left') && rail}
        <div className='composite-main'>
          <WorkflowTabActions actions={tab.actions} tab={tab} session={session} rows={rows} />
          {reorderError && <span className='composite-toolbar__error'>{reorderError}</span>}
          <div className='composite-grid composite-grid--paged'>{renderRow(activePage)}</div>
        </div>
        {(pageBarPosition === 'bottom' || pageBarPosition === 'right') && rail}
      </div>
    </div>
  );
}

/**
 * TabSlotGrid renders slots according to the workflow UI tab definition.
 * Passes sort_order, sessionId, slotId to each SlotRenderer for Phase 3 actions.
 */
// ---------------------------------------------------------------------------
// SortableImageList — drag-and-drop reordering for image list slots
// Uses HTML5 native drag events; no external library needed.
// Insert indicator is a vertical line between items, not a highlight on the item.
// ---------------------------------------------------------------------------

function SortableImageList({
  revisions,
  session,
  slotDef,
  isDraggable,
  onRefresh,
  onReference,
  onFocusSortOrder,
  onAddItem,
  readOnly,
}: {
  revisions: SlotRevision[];
  session: WorkflowSession;
  slotDef: SlotDef;
  isDraggable: boolean;
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  onFocusSortOrder?: (sortOrder: number | undefined) => void;
  onAddItem?: () => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const reorderSlotItems = useWorkflowStore((s) => s.reorderSlotItems);
  // localOrder stores list_index values in display order.
  const [localOrder, setLocalOrder] = useState<number[]>(() =>
    revisions.map((r) => r.list_index ?? 0),
  );
  useEffect(() => {
    setLocalOrder(revisions.map((r) => r.list_index ?? 0));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revisions.map((r) => `${r.list_index}`).join(',')]);

  const dragSrcIdx = useRef<number | null>(null);
  // insertIdx is a gap index: 0 = before first item, n = after last item.
  const [insertIdx, setInsertIdx] = useState<number | null>(null);

  const handleDragStart = useCallback((idx: number, e: React.DragEvent) => {
    e.stopPropagation();
    // Mark as internal sort drag so outer file-upload listeners can ignore it.
    e.dataTransfer.setData('application/x-workflow-sort', String(idx));
    e.dataTransfer.effectAllowed = 'move';
    dragSrcIdx.current = idx;
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.stopPropagation();
  }, []);

  // Compute which gap the pointer is closest to based on the drag position
  // relative to the hovered item element.
  const computeInsertIdx = useCallback((e: React.DragEvent, itemIdx: number) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const midX = rect.left + rect.width / 2;
    return e.clientX < midX ? itemIdx : itemIdx + 1;
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, itemIdx: number) => {
    e.preventDefault();
    e.stopPropagation();
    setInsertIdx(computeInsertIdx(e, itemIdx));
  }, [computeInsertIdx]);

  const handleContainerDragLeave = useCallback((e: React.DragEvent) => {
    e.stopPropagation();
    // Only clear when leaving the container entirely (not entering a child).
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) {
      setInsertIdx(null);
    }
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent, itemIdx: number) => {
    e.preventDefault();
    e.stopPropagation();
    const srcIdx = dragSrcIdx.current;
    const gapIdx = computeInsertIdx(e, itemIdx);
    dragSrcIdx.current = null;
    setInsertIdx(null);

    if (srcIdx === null) return;
    // Dropping back into same position is a no-op.
    if (gapIdx === srcIdx || gapIdx === srcIdx + 1) return;

    // next is the new list_index sequence after the move.
    const next = [...localOrder];
    const [moved] = next.splice(srcIdx, 1);
    // After removing srcIdx, adjust gap index if needed.
    const adjustedGap = gapIdx > srcIdx ? gapIdx - 1 : gapIdx;
    next.splice(adjustedGap, 0, moved);
    setLocalOrder(next);
    try {
      // order_version is carried on each revision; use the first available one.
      const orderVersion = revisions[0]?.order_version ?? 0;
      await reorderSlotItems(session.session_id, slotDef.id, next, orderVersion);
      onRefresh?.();
    } catch {
      setLocalOrder(revisions.map((r) => r.list_index ?? 0));
    }
  }, [localOrder, revisions, session.session_id, slotDef.id, reorderSlotItems, onRefresh, computeInsertIdx]);

  const handleDragEnd = useCallback(() => {
    dragSrcIdx.current = null;
    setInsertIdx(null);
  }, []);

  // Fallback handlers on the container so that dragging into the trailing
  // "Add item" card area (which has no per-item handlers) still works.
  const handleContainerDragOver = useCallback((e: React.DragEvent) => {
    // Only handle if we're not already over a child item (those call stopPropagation).
    e.preventDefault();
    // Show the insert indicator at the last position (after all items).
    setInsertIdx(localOrder.length);
  }, [localOrder.length]);

  const handleContainerDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const srcIdx = dragSrcIdx.current;
    dragSrcIdx.current = null;
    setInsertIdx(null);
    if (srcIdx === null) return;
    // Target gap is after all items.
    const gapIdx = localOrder.length;
    // No-op if already at the end.
    if (gapIdx === srcIdx + 1) return;
    const next = [...localOrder];
    const [moved] = next.splice(srcIdx, 1);
    next.push(moved);
    setLocalOrder(next);
    try {
      const orderVersion = revisions[0]?.order_version ?? 0;
      await reorderSlotItems(session.session_id, slotDef.id, next, orderVersion);
      onRefresh?.();
    } catch {
      setLocalOrder(revisions.map((r) => r.list_index ?? 0));
    }
  }, [localOrder, revisions, session.session_id, slotDef.id, reorderSlotItems, onRefresh]);

  const byListIndex: Record<number, SlotRevision> = {};
  for (const r of revisions) {
    if (r.list_index !== undefined) byListIndex[r.list_index] = r;
  }

  const canDrag = isDraggable && !readOnly;
  const useGridLayout = slotDef.widget?.itemLayout === 'grid' && !canDrag;
  const itemWidth = slotDef.widget?.itemWidth;
  const itemHeight = slotDef.widget?.itemHeight;
  const gridMaxCols = slotDef.widget?.gridMaxCols;
  const imageListStyle = {
    ...(typeof itemWidth === 'number'
      ? { '--workflow-image-item-width': `${itemWidth}px` }
      : {}),
    ...(typeof itemHeight === 'number'
      ? { '--workflow-image-item-height': `${itemHeight}px` }
      : {}),
    ...(typeof itemWidth === 'number' && typeof gridMaxCols === 'number'
      ? {
        '--workflow-image-list-max-width': `${
          itemWidth * gridMaxCols + Math.max(0, gridMaxCols - 1) * 12
        }px`,
      }
      : {}),
  } as React.CSSProperties;

  return (
    <div
      className={`workflow-panel__image-list${canDrag ? ' workflow-panel__image-list--sortable' : ''}${useGridLayout ? ' workflow-panel__image-list--grid' : ''}`}
      style={imageListStyle}
      onDragLeave={canDrag ? handleContainerDragLeave : undefined}
      onDragEnter={canDrag ? handleDragEnter : undefined}
      onDragOver={canDrag ? handleContainerDragOver : undefined}
      onDrop={canDrag ? handleContainerDrop : undefined}
    >
      {/* Insert indicator before first item */}
      {canDrag && (
        <div className={`workflow-panel__image-insert-gap${insertIdx === 0 ? ' workflow-panel__image-insert-gap--active' : ''}`} aria-hidden='true' />
      )}
      {localOrder.map((listIndex, idx) => {
        const rev = byListIndex[listIndex];
        if (!rev) return null;
        return (
          <React.Fragment key={`${rev.slot_id}-${rev.sort_order ?? rev.list_index ?? 0}`}>
            <div
              draggable={canDrag}
              onDragStart={canDrag ? (e) => handleDragStart(idx, e) : undefined}
              onDragEnter={canDrag ? handleDragEnter : undefined}
              onDragOver={canDrag ? (e) => handleDragOver(e, idx) : undefined}
              onDrop={canDrag ? (e) => handleDrop(e, idx) : undefined}
              onDragEnd={canDrag ? handleDragEnd : undefined}
              onClick={() => onFocusSortOrder?.(rev.sort_order)}
              role='button'
              tabIndex={0}
              aria-label={t('chat.workflowImageAria', { index: listIndex })}
              className={`workflow-panel__image-list-item${dragSrcIdx.current === idx ? ' workflow-panel__image-list-item--dragging' : ''}`}
            >
              <SlotRenderer
                slot={rev}
                cardMode
                widget={slotDef.widget}
                expectedType={slotDef.type}
                sessionId={session.session_id}
                slotId={slotDef.id}
                revisionCount={rev.revision_count}
                isDraggable={canDrag}
                onRefresh={onRefresh}
                onReference={onReference}
                readOnly={readOnly}
              />
            </div>
            {/* Insert indicator after each item */}
            {canDrag && (
              <div className={`workflow-panel__image-insert-gap${insertIdx === idx + 1 ? ' workflow-panel__image-insert-gap--active' : ''}`} aria-hidden='true' />
            )}
          </React.Fragment>
        );
      })}
      {/* Add new item card */}
      {onAddItem && !readOnly && (
        <button
          className='workflow-panel__image-add-card'
          onClick={onAddItem}
          title={t('chat.workflowAddAttachment')}
          aria-label={t('chat.workflowAddAttachment')}
          type='button'
        >
          <span className='workflow-panel__image-add-card-icon'>+</span>
          <span className='workflow-panel__image-add-card-label'>{t('chat.workflowAddAttachment')}</span>
        </button>
      )}
    </div>
  );
}

function NamedTabSlot({
  slotDef,
  revisions,
  artifactStream,
  session,
  onRefresh,
  onReference,
  onFocusSortOrder,
  onAddItem,
  readOnly,
  hideLabel = false,
  slotStepId,
}: {
  slotDef: SlotDef;
  hideLabel?: boolean;
  slotStepId?: string;
  revisions: SlotRevision[];
  session: WorkflowSession;
  artifactStream?: TaskArtifactStream;
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  onFocusSortOrder?: (sortOrder: number | undefined) => void;
  onAddItem: () => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const externalPresentation = React.useContext(ExternalWorkflowPresentationContext);
  const slotLabel = slotDef.label ?? slotDef.id;
  const isImageList = slotDef.type === 'image' && slotDef.cardinality === 'list';
  const isDraggable = Boolean(slotDef.ordered) && !readOnly;
  const [nativeCollapsed, setContentCollapsed] = useState(slotDef.widget?.collapsed === true);
  const collapseWhenEmpty = externalPresentation && slotDef.widget?.collapseWhenEmpty !== false;
  const [externalCollapsed, toggleExternalCollapsed] = useSlotCollapse(
    revisions.length > 0 || Boolean(artifactStream), collapseWhenEmpty, slotDef.widget?.collapsed === true,
  );
  const contentCollapsed = externalPresentation ? externalCollapsed : nativeCollapsed;
  const prefersFullGridRow = slotDef.widget?.itemLayout === 'grid'
    || (slotDef.widget?.itemWidth ?? 0) >= 600
    || slotDef.widget?.collapsed === true;
  const isWriterDocument = slotDef.widget?.widgetType === 'writer-document';
  const showStream = Boolean(artifactStream && (
    revisions.length === 0 || artifactStream.state === 'streaming'
  ));

  const content = showStream && artifactStream ? (
    <SlotMarkdownStream stream={artifactStream} />
  ) : revisions.length === 0 ? (
    <div
      className='workflow-panel__slot-placeholder'
      aria-label={`${slotLabel} pending`}
    >
      <span>{externalPresentation ? t(workflowEmptyStateKey(session, slotStepId)) : '—'}</span>
    </div>
  ) : isImageList ? (
    <SortableImageList
      revisions={revisions}
      session={session}
      slotDef={slotDef}
      isDraggable={isDraggable}
      onRefresh={onRefresh}
      onReference={onReference}
      onFocusSortOrder={onFocusSortOrder}
      onAddItem={readOnly ? undefined : onAddItem}
      readOnly={readOnly}
    />
  ) : (
    revisions.map((rev) => (
      <div
        key={`${rev.slot_id}-${rev.list_index ?? -1}`}
        onClick={() => onFocusSortOrder?.(rev.sort_order)}
        role='button'
        tabIndex={0}
        aria-label={t('chat.workflowContentItemAria', { index: rev.sort_order ?? '' })}
      >
        <SlotRenderer
          slot={rev}
          widget={slotDef.widget}
          originalFileSlot={
            slotDef.id === 'delivered_markdown'
              ? session.slots?.find((item) => item.slot === 'final_document' && item.selected)
              : undefined
          }
          expectedType={slotDef.type}
          sessionId={session.session_id}
          slotId={slotDef.id}
          revisionCount={rev.revision_count}
          onRefresh={onRefresh}
          onReference={onReference}
          readOnly={readOnly}
        />
      </div>
    ))
  );

  return (
    <div className={`workflow-panel__named-slot${prefersFullGridRow ? ' workflow-panel__named-slot--full-grid-row' : ''}${isWriterDocument ? ' workflow-panel__named-slot--writer-document' : ''}`}>
      {(!hideLabel || collapseWhenEmpty) && <div className='workflow-panel__slot-heading'>
        {(slotDef.label || slotDef.id) && (
          <span className='workflow-panel__slot-label'>{slotLabel}</span>
        )}
        {externalPresentation && contentCollapsed && revisions.length === 0 && !artifactStream &&
          <span className='workflow-panel__empty-summary' role='status'>{t(workflowEmptyStateKey(session, slotStepId))}</span>}
        {(slotDef.widget?.collapsed !== undefined || collapseWhenEmpty) && (
          <button
            type='button'
            className={`workflow-panel__slot-collapse${contentCollapsed ? ' workflow-panel__slot-collapse--collapsed' : ''}`}
            aria-expanded={!contentCollapsed}
            aria-label={contentCollapsed ? t('chat.workflowPanelExpand') : t('chat.workflowPanelCollapse')}
            onClick={externalPresentation ? toggleExternalCollapsed : () => setContentCollapsed((value) => !value)}
          >
            <span aria-hidden='true'>⌃</span>
          </button>
        )}
      </div>}
      {!contentCollapsed && content}
    </div>
  );
}

function TabSlotGrid({
  tab,
  session,
  tasks,
  onRefresh,
  onReference,
  onFocusSortOrder,
  readOnly,
}: {
  tab: TabDef;
  session: WorkflowSession;
  tasks: SubAgentTask[];
  onRefresh?: () => void;
  onReference?: (slot: SlotRevision) => void;
  onFocusSortOrder?: (sortOrder: number | undefined) => void;
  readOnly?: boolean;
}) {
  const externalPresentation = React.useContext(ExternalWorkflowPresentationContext);
  const { t } = useTranslation();
  const addFileInputRef = useRef<HTMLInputElement>(null);
  const addingSlotIdRef = useRef<string>('');
  const addingSlotTypeRef = useRef<string>('');
  const { createSlotItem } = useWorkflowStore();

  const handleAddItem = useCallback((slotId: string, slotType: string) => {
    if (readOnly) return;
    addingSlotIdRef.current = slotId;
    addingSlotTypeRef.current = slotType;
    addFileInputRef.current?.click();
  }, [readOnly]);

  const handleAddFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || readOnly) return;
    const slotId = addingSlotIdRef.current;
    if (!slotId) return;
    const slotType = addingSlotTypeRef.current;
    const ct = slotType === 'image' ? 'image' : slotType === 'file' ? 'file' : undefined;
    try {
      const storedPath = await uploadFileInChunks(file);
      await createSlotItem(session.session_id, slotId, { path: storedPath }, file.name, undefined, ct);
      onRefresh?.();
    } catch {
      // upload failure — no-op
    }
  }, [session.session_id, createSlotItem, onRefresh, readOnly]);
  if (tab.layout === 'composite') {
    return (
      <CompositeSlotGrid
        tab={tab}
        session={session}
        onRefresh={onRefresh}
        onReference={onReference}
        onFocusSortOrder={onFocusSortOrder}
        readOnly={readOnly}
      />
    );
  }
  const resolveVisibleSlots = (slotDefs: SlotDef[]): SlotDef[] => {
    const visible = resolveVisibleSlotIds(tab, session);
    if (!visible) return slotDefs;
    return slotDefs.filter((slotDef) => visible.has(slotDef.id) || Boolean(findWriterArtifactStream(
      session,
      getTabStepId(tab),
      slotDef.id,
      tasks,
    )));
  };
  const visibleSlots = resolveVisibleSlots(resolvePreferredStructuredSlotDefs(tab, session));
  const allHidden = visibleSlots.length === 0 || Boolean(tab.composite_behavior?.hide_empty_columns)
    && visibleSlots.every(def => getTabSlotRevisions(session, tab, def.id).length === 0
      && !findWriterArtifactStream(session, getTabStepId(tab), def.id, tasks));
  if (externalPresentation && allHidden) return <div className='workflow-panel__empty' role='status'>
    {t(workflowEmptyStateKey(session, resolveWorkflowTabStepId(tab, session.steps)))}
  </div>;
  return (
    <div className={`workflow-panel__tab-content workflow-panel__tab-content--${tab.layout ?? 'vertical'}`}>
      {/* Hidden file input for adding new items */}
      <input
        ref={addFileInputRef}
        type='file'
        accept='image/*'
        style={{ display: 'none' }}
        onChange={handleAddFileChange}
        aria-hidden='true'
      />
      {visibleSlots.map((slotDef) => {
        const artifactKey = slotDef.id;
        const revisions = localizeDesignRoutingSummaryRevisions(
          session,
          artifactKey,
          getTabSlotRevisions(session, tab, artifactKey),
        );
        const artifactStream = findWriterArtifactStream(
          session,
          getTabStepId(tab),
          slotDef.id,
          tasks,
        );
        const hideEmpty = Boolean(tab.composite_behavior?.hide_empty_columns);
        if (hideEmpty && revisions.length === 0 && !artifactStream) {
          return null;
        }
        return (
          <NamedTabSlot
            key={slotDef.id}
            slotDef={slotDef}
            slotStepId={resolveWorkflowTabStepId(tab, session.steps)}
            hideLabel={visibleSlots.length === 1 && slotDef.widget?.widgetType === 'writer-document'
              && slotDef.widget?.collapsed === undefined && slotDef.label === tab.label}
            revisions={revisions}
            artifactStream={artifactStream}
            session={session}
            onRefresh={onRefresh}
            onReference={onReference}
            onFocusSortOrder={onFocusSortOrder}
            onAddItem={() => handleAddItem(slotDef.id, slotDef.type)}
            readOnly={readOnly}
          />
        );
      })}
    </div>
  );
}

const STATUS_KEY: Record<string, string> = {
  active: 'chat.workflowStatusRunning',
  completed: 'chat.workflowStatusDone',
  waiting: 'chat.workflowStatusPaused',
  failed: 'chat.workflowStatusFailed',
  stopped: 'chat.workflowStatusStopped',
};

const STEP_STATUS_KEY: Record<string, string> = {
  succeeded: 'chat.workflowStatusDone',
  completed: 'chat.workflowStatusDone',
  pending: 'chat.workflowStatusRunning',
  queued: 'chat.workflowStatusRunning',
  running: 'chat.workflowStatusRunning',
  waiting: 'chat.workflowStatusWaiting',
  failed: 'chat.workflowStatusFailed',
  interrupted: 'chat.workflowStatusStopped',
  stopped: 'chat.workflowStatusStopped',
};

function readPersistedExpanded(conversationId: string): boolean | null {
  try {
    return parsePersistedPanelExpanded(
      localStorage.getItem(`${WORKFLOW_PANEL_EXPANDED_STORAGE_PREFIX}${conversationId}`),
    );
  } catch {
    return null;
  }
}

function readPersistedFollowMode(sessionId: string): WorkflowFollowMode | null {
  try {
    return parsePersistedFollowMode(
      localStorage.getItem(`${WORKFLOW_FOLLOW_MODE_STORAGE_PREFIX}${sessionId}`),
    );
  } catch {
    return null;
  }
}

function persistFollowMode(sessionId: string, mode: WorkflowFollowMode) {
  try {
    localStorage.setItem(`${WORKFLOW_FOLLOW_MODE_STORAGE_PREFIX}${sessionId}`, mode);
  } catch {
    // The selected mode remains active for this page.
  }
}

function persistExpanded(conversationId: string, expanded: boolean) {
  try {
    localStorage.setItem(
      `${WORKFLOW_PANEL_EXPANDED_STORAGE_PREFIX}${conversationId}`,
      String(expanded),
    );
  } catch {
    // The live layout state still works when browser storage is unavailable.
  }
}

export function WorkflowPanel({
  conversationId,
  onReference,
  onSendMessage,
  onStop,
  onDismissed,
  embedded = false, onRefresh, controlAdapter, externalPresentation,
}: WorkflowPanelProps) {
  const { t, i18n } = useTranslation();
  const { session, loading, refresh: refreshConversation } = useWorkflowSession(conversationId, Boolean(onRefresh));
  const refresh = onRefresh ?? refreshConversation;
  const activities = externalPresentation?.activities ?? {};
  const runningTasks = externalPresentation ? activeExecutionTasks(session) : [];
  const latestActivity = runningTasks.map(step => activities[step.task_id]).find(activity => activity?.kind && !activity.finished);
  const taskCenterTasks = useTaskCenterStore((state) =>
    conversationId
      ? state.tasksByConversation[conversationId] ?? EMPTY_TASK_CENTER_TASKS
      : EMPTY_TASK_CENTER_TASKS,
  );
  const bumpDismissedRefresh = useWorkflowStore((s) => s.bumpDismissedRefresh);
  const autoRunning = useWorkflowStore((s) =>
    conversationId ? (s.autoRunningByConversation[conversationId] ?? false) : false,
  );
  const setAutoRunning = useWorkflowStore((s) => s.setAutoRunning);
  const [activeTabId, setActiveTabId] = React.useState('');
  const [localCollapsed, setCollapsed] = useState(false);
  const collapsed = externalPresentation?.collapsed ?? localCollapsed;
  const toggleCollapsed = externalPresentation?.onToggleCollapse
    ?? (() => setCollapsed(value => !value));
  const fetchWorkflowUI = useWorkflowStore((s) => s.fetchWorkflowUI);
  const setFocusedTab = useWorkflowStore((s) => s.setFocusedTab);
  const setFocusedSortOrder = useWorkflowStore((s) => s.setFocusedSortOrder);
  // Focused tab id mirrored out of the session so polling refreshes don't
  // reset the user's current tab.
  const focusedTabByConversation = useWorkflowStore((s) => s.focusedTabByConversation);
  const persistedFocusedTab = conversationId ? focusedTabByConversation[conversationId] : undefined;
  const [ui, setUI] = useState<WorkflowUI>({});
  const [dismissing, setDismissing] = useState(false);
  const [stateGraphOpen, setStateGraphOpen] = useState(false);
  const persistedExpandedRef = useRef(readPersistedExpanded(conversationId));
  const hasExplicitExpandedChoiceRef = useRef(persistedExpandedRef.current !== null);
  const defaultPanelModeAppliedRef = useRef(false);
  const [expanded, setExpanded] = useState(() =>
    resolveInitialPanelExpanded(persistedExpandedRef.current),
  );
  const [followState, setFollowState] = useState<{
    sessionId: string;
    mode: WorkflowFollowMode;
  } | null>(null);
  const panelExpanded = embedded ? Boolean(externalPresentation?.expanded) : expanded;
  const initialExpandedRef = useRef(expanded);
  // Track which slots are currently being edited; dismiss stays blocked until
  // each editor saves or cancels. Footer retry/continue flushes pending saves.
  const editingSlots = useRef<Set<string>>(new Set());
  const snapshotFns = useRef(new Map<string, () => unknown>());
  const flushFns = useRef<Map<string, () => Promise<boolean>>>(new Map());
  const [anySlotEditing, setAnySlotEditing] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState('');
  // Preserve the exact command body after an uncertain network result. Replaying
  // the same bytes and idempotency key is safe; inventing a second command is not.
  const uncertainWorkflowCommand = useRef<{
    fingerprint: string;
    payload: WorkflowTransitionRequest;
  } | null>(null);
  const uncertainProductRestart = useRef<{
    fingerprint: string;
    payload: WorkflowRestartOnLatestRequest;
  } | null>(null);
  const [viewingProductSession, setViewingProductSession] = useState<string | null>(null);
  const [requestedProductStage, setRequestedProductStage] = useState<{ sessionId: string; stage: ProductStageId; requestId: number } | null>(null);
  const [productStateRevision, setProductStateRevision] = useState(0);
  const [footerActions, setFooterActions] = useState<Map<string, SlotFooterAction>>(new Map());
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const tabsRef = useRef<HTMLDivElement | null>(null);
  const tabsWheelCleanupRef = useRef<(() => void) | null>(null);
  const setTabsScrollRef = useCallback((element: HTMLDivElement | null) => {
    tabsRef.current = element;
    tabsWheelCleanupRef.current?.();
    tabsWheelCleanupRef.current = null;
    if (!element) return;

    const handleWheel = (event: WheelEvent) => {
      // Keep native horizontal gestures, Shift+wheel and pinch zoom intact.
      if (event.defaultPrevented || event.ctrlKey || event.shiftKey || event.deltaX !== 0 || event.deltaY === 0) return;
      const maxScrollLeft = element.scrollWidth - element.clientWidth;
      if (maxScrollLeft <= 0) return;

      const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
        ? 16
        : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? element.clientWidth : 1;
      const nextScrollLeft = Math.max(0, Math.min(maxScrollLeft, element.scrollLeft + event.deltaY * unit));
      // Let the surrounding conversation scroll once this direction reaches an edge.
      if (nextScrollLeft === element.scrollLeft) return;
      element.scrollLeft = nextScrollLeft;
      event.preventDefault();
      event.stopPropagation();
    };

    // React's passive wheel listener cannot prevent simultaneous page scrolling.
    element.addEventListener('wheel', handleWheel, { passive: false });
    tabsWheelCleanupRef.current = () => element.removeEventListener('wheel', handleWheel);
  }, []);

  useEffect(() => {
    const container = tabsRef.current;
    const selected = container?.querySelector('[aria-selected="true"]');
    if (!container || !selected) return;
    const viewport = container.getBoundingClientRect();
    const tab = selected.getBoundingClientRect();
    // Follow runtime stage changes without scrolling the conversation or editor.
    if (tab.left < viewport.left) container.scrollLeft += tab.left - viewport.left;
    else if (tab.right > viewport.right) container.scrollLeft += tab.right - viewport.right;
  }, [activeTabId, ui.tabs, collapsed]);
  const documentFooter = useMemo(
    () => buildDocumentFooterItems(footerActions),
    [footerActions],
  );

  useEffect(() => {
    setProductStateRevision(0);
  }, [session?.session_id]);

  const handleProductDecisionChanged = useCallback(() => {
    setProductStateRevision((value) => value + 1);
    refresh();
  }, [refresh]);

  const setExpandedMode = useCallback((nextExpanded: boolean, persistUserChoice = true) => {
    if (nextExpanded) setCollapsed(false);
    setExpanded(nextExpanded);
    if (persistUserChoice) {
      hasExplicitExpandedChoiceRef.current = true;
      persistExpanded(conversationId, nextExpanded);
    }
    window.dispatchEvent(new CustomEvent(WORKFLOW_PANEL_EXPANDED_EVENT, {
      detail: { conversationId, expanded: nextExpanded },
    }));
  }, [conversationId]);

  const handleStop = useCallback(() => {
    setAutoRunning(conversationId, false);
    onStop?.();
    window.setTimeout(() => {
      void refresh();
    }, 250);
  }, [conversationId, onStop, refresh, setAutoRunning]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent(WORKFLOW_PANEL_EXPANDED_EVENT, {
      detail: { conversationId, expanded: initialExpandedRef.current },
    }));
    return () => {
      window.dispatchEvent(new CustomEvent(WORKFLOW_PANEL_EXPANDED_EVENT, {
        detail: { conversationId, expanded: false },
      }));
    };
  }, [conversationId]);

  const handleDismiss = useCallback(async () => {
    if (!session || dismissing || anySlotEditing) return;
    setDismissing(true);
    try {
      await WorkflowSessionApi().dismissSession(session.session_id);
      bumpDismissedRefresh(conversationId);
      onDismissed?.();
      refresh();
    } catch {
      setDismissing(false);
    }
  }, [session, dismissing, anySlotEditing, refresh, t, onDismissed, bumpDismissedRefresh, conversationId]);
  const [intentOpen, setIntentOpen] = useState(false);

  const handleSlotEditingChange = useCallback((key: string, editing: boolean) => {
    if (editing) {
      editingSlots.current.add(key);
    } else {
      editingSlots.current.delete(key);
    }
    setAnySlotEditing(editingSlots.current.size > 0);
  }, []);

  const registerSnapshot = useCallback((key: string, read: () => unknown) => {
    snapshotFns.current.set(key, read);
    return () => { if (snapshotFns.current.get(key) === read) snapshotFns.current.delete(key); };
  }, []);
  const getSnapshot = useCallback((key: string) => snapshotFns.current.get(key)?.(), []);

  const registerFlush = useCallback((key: string, flush: () => Promise<boolean>) => {
    flushFns.current.set(key, flush);
    return () => {
      flushFns.current.delete(key);
    };
  }, []);

  const registerFooterAction = useCallback((key: string, action: SlotFooterAction | null) => {
    setFooterActions((previous) => {
      const next = new Map(previous);
      if (action) next.set(key, action);
      else next.delete(key);
      return next;
    });
    return () => {
      setFooterActions((previous) => {
        if (!previous.has(key)) return previous;
        const next = new Map(previous);
        next.delete(key);
        return next;
      });
    };
  }, []);

  const flushPendingEdits = useCallback(async (flushKey?: string): Promise<boolean> => {
    const selectedFlusher = flushKey ? flushFns.current.get(flushKey) : undefined;
    const flushers = flushKey
      ? (selectedFlusher ? [selectedFlusher] : [])
      : [...flushFns.current.values()];
    if (flushers.length === 0) return true;
    const results = await Promise.all(flushers.map((flush) => flush()));
    return results.every(Boolean);
  }, []);

  useEffect(() => {
    editingSlots.current.clear();
    flushFns.current.clear();
    setFooterActions(new Map());
    setAnySlotEditing(false);
    setActionPending(false);
    setActionError('');
    uncertainWorkflowCommand.current = null;
    uncertainProductRestart.current = null;
  }, [session?.session_id]);

  useEffect(() => {
    if (!session?.workflow_id) return;
    const lang = i18n.language || '';
    const cached = useWorkflowStore.getState().workflowUIByWorkflow[`${session.workflow_id}:${lang}`];
    if (cached) {
      setUI(cached);
    }
    // Always re-fetch once to avoid stale cached tab/slot layouts after workflow.yaml updates.
    fetchWorkflowUI(session.workflow_id).then(setUI);
  }, [session?.workflow_id, fetchWorkflowUI, i18n.language]);

  useEffect(() => {
    if (
      defaultPanelModeAppliedRef.current
      || hasExplicitExpandedChoiceRef.current
      || ui.default_panel_mode === undefined
    ) return;
    defaultPanelModeAppliedRef.current = true;
    setExpandedMode(resolveInitialPanelExpanded(null, ui.default_panel_mode), false);
  }, [setExpandedMode, ui.default_panel_mode]);

  useEffect(() => {
    const sessionId = session?.session_id;
    const defaultFollowMode = ui.follow_mode?.default;
    if (!sessionId || !defaultFollowMode) {
      setFollowState(null);
      return;
    }
    setFollowState({
      sessionId,
      mode: resolveInitialFollowMode(
        readPersistedFollowMode(sessionId),
        defaultFollowMode,
      ),
    });
  }, [session?.session_id, ui.follow_mode?.default]);

  const setSessionFollowMode = useCallback((mode: WorkflowFollowMode) => {
    const sessionId = session?.session_id;
    if (!sessionId || !ui.follow_mode?.default) return;
    setFollowState({ sessionId, mode });
    persistFollowMode(sessionId, mode);
  }, [session?.session_id, ui.follow_mode?.default]);

  const followingEnabled = Boolean(ui.follow_mode?.default);
  const followMode = followState && followState.sessionId === session?.session_id
    ? followState.mode
    : 'free';

  // Restore the previously focused tab when UI loads.
  useEffect(() => {
    const tabs = filterWorkflowTabs(
      ui.tabs ?? [],
      session?.slots ?? [],
      ui.tab_visibility_ready_material,
      { steps: session?.steps, projection: session?.projection },
    );
    if (!tabs.length || !persistedFocusedTab || (followingEnabled && followMode === 'following')) return;
    if (tabs.some((tab) => tab.id === persistedFocusedTab)) {
      setActiveTabId(persistedFocusedTab);
    }
  }, [followMode, followingEnabled, ui.tabs, ui.tab_visibility_ready_material, persistedFocusedTab, session?.projection, session?.slots, session?.steps]);

  // Until the user explicitly chooses a visible tab, follow the runtime
  // frontier. This also moves focus immediately when a skip material removes
  // the previously selected tab.
  useEffect(() => {
    const tabs = filterWorkflowTabs(
      ui.tabs ?? [],
      session?.slots ?? [],
      ui.tab_visibility_ready_material,
      { steps: session?.steps, projection: session?.projection },
    );
    if (followingEnabled && followMode === 'following' && session && tabs.length) {
      const runtimeIndex = resolveWorkflowRealTabIndex(session, tabs);
      if (runtimeIndex !== -1) setActiveTabId(tabs[runtimeIndex].id);
      return;
    }
    const focusedTabVisible = Boolean(
      persistedFocusedTab && tabs.some((tab) => tab.id === persistedFocusedTab),
    );
    if (!tabs.length || focusedTabVisible || !session) return;
    let idx = tabs.findIndex((tab) => getTabStepId(tab) === session.current_step_id);
    if (idx === -1 && (session.status === 'completed' || session.status === 'failed')) {
      idx = tabs.length - 1;
    }
    if (idx !== -1) setActiveTabId(tabs[idx].id);
  }, [
    ui.tabs,
    ui.tab_visibility_ready_material,
    followMode,
    followingEnabled,
    persistedFocusedTab,
    session?.current_step_id,
    session?.projection,
    session?.session_id,
    session?.slots,
    session?.status,
    session?.steps,
  ]);

  // Track focused tab changes.
  const handleTabChange = useCallback((idx: number, tabId: string) => {
    if (followingEnabled && followMode === 'following' && session) {
      const visibleTabs = filterWorkflowTabs(
        ui.tabs ?? [], session.slots ?? [], ui.tab_visibility_ready_material,
        { steps: session.steps, projection: session.projection },
      );
      const runtimeIndex = resolveWorkflowRealTabIndex(session, visibleTabs);
      if (runtimeIndex === -1 || idx !== runtimeIndex) {
        setSessionFollowMode('free');
        antdMessage.info(t('chat.workflowFreeBrowseActivatedMessage'));
      }
    }
    setActiveTabId(tabId);
    setFocusedTab(conversationId, tabId);
    setFocusedSortOrder(conversationId, undefined);
  }, [conversationId, followMode, followingEnabled, session, setFocusedTab, setFocusedSortOrder, setSessionFollowMode, t, ui.tab_visibility_ready_material, ui.tabs]);

  const handleFocusSortOrder = useCallback((sortOrder: number | undefined) => {
    setFocusedSortOrder(conversationId, sortOrder);
  }, [conversationId, setFocusedSortOrder]);

  const runWorkflowCommand = useCallback(async (
    targetSessionId: string,
    action: WorkflowCommandAction,
    options: {
      completedContinueStepId?: string;
      currentStepId?: string;
      rollbackStepId?: string;
    } = {},
  ) => {
    const fingerprint = JSON.stringify([targetSessionId, action, options]);
    let payload: WorkflowTransitionRequest;
    if (uncertainWorkflowCommand.current?.fingerprint === fingerprint) {
      payload = uncertainWorkflowCommand.current.payload;
    } else {
      const response = await WorkflowSessionApi().getProjection(
        targetSessionId,
        { silentError: true } as never,
      );
      const snapshot = response.data?.data;
      if (!snapshot || !Number.isInteger(snapshot.state_version) || !snapshot.projection) {
        throw new WorkflowCommandTargetError(
          'WORKFLOW_COMMAND_TARGET_MISSING',
          action,
          'The latest workflow projection is unavailable.',
        );
      }
      const stepId = resolveWorkflowCommandTarget(action, snapshot.projection, options);
      const commandId = uuidv4();
      payload = {
        contract_version: WORKFLOW_CONTRACT_VERSION,
        command_id: commandId,
        tool: 'advance_step_and_hand_off',
        session_id: targetSessionId,
        expected_state_version: snapshot.state_version,
        retry_origin: 'user',
        steps: [{ step_id: stepId }],
      };
      uncertainWorkflowCommand.current = { fingerprint, payload };
    }

    setAutoRunning(conversationId, true);
    try {
      const response = await WorkflowSessionApi().advanceStepAndHandOff(
        targetSessionId,
        payload,
        { silentError: true } as never,
      );
      const result = response.data?.result;
      if (!response.data?.ok || !result?.accepted) {
        const commandError = new Error(result?.error?.message || response.data?.error?.message || 'Workflow command was rejected.');
        Object.assign(commandError, { code: result?.error?.code || response.data?.error?.code });
        throw commandError;
      }
      uncertainWorkflowCommand.current = null;
      await Promise.allSettled([
        useWorkflowStore.getState().loadActiveSession(conversationId, { silentError: true }),
        useTaskCenterStore.getState().loadConversationTasks(conversationId),
      ]);
      const latest = useWorkflowStore.getState().sessionByConversation[conversationId];
      if (!latest || latest.status !== 'active') setAutoRunning(conversationId, false);
    } catch (cause) {
      // An HTTP response is a definite rejection and must use a fresh projection
      // on the next click. A timeout/network loss is uncertain, so keep and replay
      // this exact idempotent command instead.
      if ((cause as { response?: unknown })?.response) {
        uncertainWorkflowCommand.current = null;
      }
      setAutoRunning(conversationId, false);
      await Promise.allSettled([
        useWorkflowStore.getState().loadActiveSession(conversationId, { silentError: true }),
        useTaskCenterStore.getState().loadConversationTasks(conversationId),
      ]);
      throw cause;
    }
  }, [conversationId, setAutoRunning]);

  const handleProductSessionReady = useCallback(async (sessionId: string, start: boolean) => {
    // Read the acknowledged successor directly. Starting it is a typed workflow
    // command; stage relay must never create a synthetic chat turn.
    const [detail, projection] = await Promise.all([
      WorkflowSessionApi().getSession(sessionId, { silentError: true } as never),
      WorkflowSessionApi().getProjection(sessionId, { silentError: true } as never),
    ]);
    const next: WorkflowSession | undefined = detail.data?.data?.session;
    if (!next || next.conversation_id !== conversationId) {
      throw new Error(t('chat.productStageRelay.openFailed'));
    }
    next.projection = projection.data?.data?.projection ?? {};
    next.status = reconcileWorkflowSessionStatus(next.status, next.projection);
    const startTarget = start
      ? resolveUniqueWorkflowStartTarget(next.projection)
      : undefined;
    if (startTarget && next.status === 'active') {
      // A prepared successor can be persisted as active before its first task
      // exists. Keep the local control state retryable if dispatch fails.
      next.status = 'waiting';
    }
    useWorkflowStore.getState().setSession(conversationId, next);
    setFocusedTab(conversationId, '');
    setFocusedSortOrder(conversationId, undefined);
    setActiveTabId('');
    if (startTarget) {
      // Re-read inside runWorkflowCommand before dispatch so the target stays
      // authoritative even if the projection changes between these requests.
      await runWorkflowCommand(sessionId, 'continue');
    }
  }, [conversationId, runWorkflowCommand, setFocusedSortOrder, setFocusedTab, t]);

  const retryProductWorkflow = useCallback(async (
    sourceSessionId: string,
    currentStepId: string,
  ) => {
    // A failed product session can be pinned to an older immutable package.
    // Read both authoritative views before deciding whether this is a normal
    // retry or a workspace-preserving restart on the current package head.
    const [projectionResponse, relayResponse] = await Promise.all([
      WorkflowSessionApi().getProjection(sourceSessionId, { silentError: true } as never),
      WorkflowSessionApi().getProductStageRelay(sourceSessionId, { silentError: true } as never),
    ]);
    const snapshot = projectionResponse.data?.data;
    if (!snapshot || !Number.isInteger(snapshot.state_version) || !snapshot.projection) {
      throw new WorkflowCommandTargetError(
        'WORKFLOW_COMMAND_TARGET_MISSING',
        'retry',
        'The latest workflow projection is unavailable.',
      );
    }
    const fingerprint = JSON.stringify([sourceSessionId, 'restart-on-latest']);
    const hasUncertainRestart = uncertainProductRestart.current?.fingerprint === fingerprint;
    const relayState = relayResponse.data?.result;
    if (!hasUncertainRestart && !relayState?.can_restart_on_latest) {
      await runWorkflowCommand(sourceSessionId, 'retry', { currentStepId });
      return;
    }

    if (!hasUncertainRestart) {
      uncertainProductRestart.current = {
        fingerprint,
        payload: {
          idempotency_key: uuidv4(),
          expected_state_version: snapshot.state_version,
        },
      };
    }
    const restartPayload = uncertainProductRestart.current?.payload;
    if (!restartPayload) {
      throw new Error(t('chat.workflowRestartLatestFailed'));
    }

    let response;
    try {
      response = await WorkflowSessionApi().restartOnLatest(
        sourceSessionId,
        restartPayload,
        { silentError: true } as never,
      );
    } catch (cause) {
      // Keep the exact payload only when delivery is uncertain. Any HTTP
      // response is an explicit rejection and the next click starts afresh.
      if ((cause as { response?: unknown })?.response) {
        uncertainProductRestart.current = null;
      }
      throw cause;
    }

    const result = response.data?.result;
    if (
      !result?.restarted
      || !result.session_id
      || result.source_session_id !== sourceSessionId
    ) {
      // The server answered definitively but did not acknowledge the restart.
      uncertainProductRestart.current = null;
      throw new Error(t('chat.workflowRestartLatestFailed'));
    }

    // Keep the restart command cached until the successor is loaded and its
    // optional first dispatch finishes. A follow-up GET/dispatch failure must
    // replay the acknowledged restart instead of creating another successor.
    await handleProductSessionReady(result.session_id, true);
    uncertainProductRestart.current = null;
  }, [handleProductSessionReady, runWorkflowCommand, t]);

  if (loading && !session) {
    return (
      <div
        className='workflow-panel workflow-panel--loading'
        role='status'
        aria-label={t('chat.workflowPanelLoading')}
      />
    );
  }

  if (!session) return null;
  const renderedSession = session;

  const tabs = filterWorkflowTabs(
    ui.tabs ?? [],
    session.slots ?? [],
    ui.tab_visibility_ready_material,
    { steps: session.steps, projection: session.projection },
  );
  const hasTabs = tabs.length > 0;
  const visibleActiveTabIdx = resolveWorkflowActiveTabIndex(tabs, activeTabId);
  const runtimeTabIdx = hasTabs ? resolveWorkflowRealTabIndex(session, tabs) : -1;
  const showActions =
    session.status === 'waiting' ||
    session.status === 'active' ||
    session.status === 'completed' ||
    session.status === 'failed' ||
    session.status === 'stopped';
  const displayStatus = autoRunning ? 'active' : session.status;
  const externalControl = controlAdapter?.control;
  const availableActions = new Set(externalControl?.available_actions ?? []);
  const pendingReview = externalControl?.reviews.find(review => review.status === 'pending');
  const approvalStepId = resolvePendingApprovalStep(session, displayStatus)
    ?? (externalControl?.continuation === 'awaiting_user' ? pendingReview?.step_id : undefined);
  const displayStatusKey = approvalStepId ? 'chat.workflowStatusWaiting'
    : displayStatus === 'waiting' && (session.projection?.blocked?.length ?? 0) > 0 ? 'chat.workflowStatusBlocked'
    : isWorkflowReadyToStart(
    displayStatus,
    session.projection,
    session.steps?.length ?? 0,
  )
    ? 'chat.workflowStatusReady'
    : STATUS_KEY[displayStatus] ?? displayStatus;
  // Only block footer actions while the plugin is actually running (or flush-in-progress).
  // Dirty editors no longer disable retry — click flushes saves first, then proceeds.
  const sessionBusy = displayStatus === 'active' || autoRunning;
  const externalDeliveryBusy = externalControl ? deliveryPending(externalControl) : false;
  const buttonsDisabled = sessionBusy || actionPending || externalDeliveryBusy;
  const viewingProductArtifact = viewingProductSession === session.session_id && isProductWorkflow(session.workflow_id);
  const productSectionKeys = productWorkflowSectionKeys(session.session_id);
  const dismissDisabled = dismissing || anySlotEditing || actionPending;
  const collapseDisabled = (anySlotEditing || actionPending) && !collapsed;
  const completedContinueStepId = resolveCompletedContinueStep(
    session,
    tabs[visibleActiveTabIdx],
  );
  const continueAction = resolveWorkflowContinueAction(session, displayStatus, tabs[visibleActiveTabIdx]);
  const productReadyToStart = isProductWorkflow(session.workflow_id)
    && displayStatus === 'waiting'
    && Boolean(resolveUniqueWorkflowStartTarget(session.projection ?? {}));
  const showContinue = Boolean(continueAction) || productReadyToStart;
  const showStepRollback =
    (session.status === 'completed' || session.status === 'failed')
    && Boolean(session.steps && session.steps.length > 0)
    && (!externalControl || availableActions.has('rewind'));

  // A failed step cannot be checkpoint-resumed — the SubAgent exited uncleanly and there is
  // no valid checkpoint to restore. Only "重试" (full restart) is meaningful in this case.
  // Note: "interrupted" steps CAN be resumed via checkpoint, so only "failed" is blocked.
  const authoritativeCurrent = session.projection?.current ?? [];
  const currentStepStatus = authoritativeCurrent
    .map((id) => session.projection?.nodes?.[id]?.execution)
    .find((status) => status === 'failed')
    ?? (session.current_step_id
      ? session.steps
        ?.filter((s) => s.step_id === session.current_step_id && s.validity !== 'stale')
        ?.sort((a, b) => b.attempt - a.attempt)[0]?.status
      : undefined);
  const effectivePast = new Set(session.projection?.past ?? []);
  const chineseUI = Boolean((i18n.resolvedLanguage || i18n.language)?.toLowerCase().startsWith('zh'));
  const rollbackSteps = showStepRollback ? session.steps!.filter((step, index, all) => effectivePast.has(step.step_id)
    && step.validity !== 'stale'
    && all.findIndex((candidate) => candidate.step_id === step.step_id && candidate.validity !== 'stale') === index) : [];
  const stepLabel = (stepId: string) => presentWorkflowStepLabel(
    stepId,
    renderedSession.workflow_id,
    tabs.find(tab => getTabStepId(tab) === stepId)?.label
      ?? tabs.find(tab => tab.status_step_ids?.includes(stepId))?.label,
    0,
    chineseUI,
  );
  const cachedContinueTargetAvailable = completedContinueStepId
    ? Boolean(session.projection?.continue?.includes(completedContinueStepId))
    : (session.projection?.ready?.length ?? 0) === 1;
  const continueDisabled = buttonsDisabled || currentStepStatus === 'failed'
    || (isProductWorkflow(session.workflow_id) && !cachedContinueTargetAvailable);
  const showRetry = (session.projection?.retryable?.length ?? 0) > 0;
  const activeControlTab = tabs[visibleActiveTabIdx];
  const activeControlStepId = (activeControlTab
    ? resolveWorkflowTabStepId(activeControlTab, session.steps)
    : undefined) ?? session.current_step_id ?? '';
  const supportsExternal = (action: string) => !externalControl || availableActions.has(action);

  async function runFooterAction(action: () => void | Promise<void>, flushKey?: string, flush = true, allowBusy = false) {
    if ((!allowBusy && sessionBusy) || actionPending) return;
    setActionPending(true);
    setActionError('');
    try {
      const saved = !flush || await flushPendingEdits(flushKey);
      if (!saved) return;
      await action();
    } catch (cause) {
      setActionError(
        cause instanceof WorkflowCommandTargetError
          ? t('chat.workflowCommandTargetUnavailable')
          : getLocalizedErrorMessage(cause),
      );
    } finally {
      setActionPending(false);
    }
  }

  function handleContinue() {
    if (!isContinuationCurrent()) return;
    if (controlAdapter) {
      const intent: WorkflowActionIntent = completedContinueStepId
        ? { kind: 'rewind', stepId: completedContinueStepId }
        : externalControl?.continuation === 'stopped'
          ? { kind: 'resume' }
          : { kind: 'continue' };
      void runFooterAction(() => controlAdapter.execute(intent));
      return;
    }
    const message = completedContinueStepId
      ? `${t('chat.workflowRollbackPrefix')}${completedContinueStepId}`
      : t('chat.workflowContinue');
    void runFooterAction(() => {
      if (isContinuationCurrent()) onSendMessage?.(message);
    });
  }

  // Saving edits is asynchronous: execution may have advanced since the click.
  function isContinuationCurrent() {
    if (controlAdapter) return true;
    if (!continueAction) return false;
    const state = useWorkflowStore.getState();
    const latest = state.sessionByConversation[conversationId];
    if (!latest || latest.session_id !== session?.session_id
      || latest.state_version !== session?.state_version || state.autoRunningByConversation[conversationId]) return false;
    const action = resolveWorkflowContinueAction(latest, latest.status, tabs[visibleActiveTabIdx]);
    return action?.kind === continueAction.kind && action.stepId === continueAction.stepId;
  }

  function handleContinueWithApprovalPreference(scope?: 'step' | 'following') {
    if (!session || !approvalStepId || !isContinuationCurrent()) return;
    if (controlAdapter && pendingReview) {
      const kind = availableActions.has('confirm_and_continue') ? 'confirm_and_continue' : 'confirm';
      void runFooterAction(() => controlAdapter.execute({
        kind, review: pendingReview,
        ...(kind === 'confirm_and_continue' && scope ? { preferenceScope: scope } : {}),
      }));
      return;
    }
    if (!scope) { handleContinue(); return; }
    const sessionId = session.session_id;
    void runFooterAction(async () => {
      if (!isContinuationCurrent()) return;
      try {
        await WorkflowSessionApi().setApprovalPreference(sessionId, {
          step_id: approvalStepId,
          scope,
          approval_required: false,
        });
        if (isContinuationCurrent()) {
          if (isProductWorkflow(renderedSession.workflow_id)) {
            await runWorkflowCommand(renderedSession.session_id, 'continue', { completedContinueStepId });
          } else {
            onSendMessage?.(t('chat.workflowContinue'));
          }
        }
      } catch (error) {
        antdMessage.error(getLocalizedErrorMessage(error));
      }
    });
  }

  function handleRetry() {
    if (isProductWorkflow(renderedSession.workflow_id)) {
      void runFooterAction(() => retryProductWorkflow(renderedSession.session_id, renderedSession.current_step_id));
      return;
    }
    if (controlAdapter) {
      void runFooterAction(() => controlAdapter.execute({ kind: 'retry', stepId: activeControlStepId }));
      return;
    }
    void runFooterAction(() => onSendMessage?.(t('chat.workflowRetry')));
  }

  function handleRollback(stepId: string) {
    if (isProductWorkflow(renderedSession.workflow_id)) {
      void runFooterAction(() => runWorkflowCommand(renderedSession.session_id, 'rollback', { rollbackStepId: stepId }));
      return;
    }
    if (controlAdapter) {
      void runFooterAction(() => controlAdapter.execute({ kind: 'rewind', stepId }));
      return;
    }
    void runFooterAction(() => onSendMessage?.(`${t('chat.workflowRollbackPrefix')}${stepId}`));
  }

  const continueLabel = approvalStepId
    ? t('chat.workflowContinueExecution')
    : continueAction?.kind === 'resume'
      ? t('chat.workflowResumeExecution')
    : displayStatus === 'waiting'
      ? t('chat.workflowSaveAndContinue')
    : t('chat.workflowContinue');

  const panel = (
    <ExternalWorkflowPresentationContext.Provider value={Boolean(externalPresentation)}>
    <SlotEditingContext.Provider value={{
      setEditing: handleSlotEditingChange,
      registerFlush,
      registerSnapshot,
      getSnapshot,
      registerFooterAction,
    }}>
    <div
      className={`workflow-panel workflow-panel--${displayStatus}${collapsed ? ' workflow-panel--collapsed' : ''}${expanded && !embedded ? ' workflow-panel--expanded' : ''}${embedded ? ' workflow-panel--embedded' : ''}${externalPresentation ? ' workflow-panel--external-presentation' : ''}`}
      data-session-id={session.session_id}
      aria-label={t('chat.workflowPanelTitle')}
    >
      <div className={`workflow-panel__topbar${!collapsed && hasTabs && tabs.length <= 3 ? ' workflow-panel__topbar--few-steps' : ''}`}>
      {/* Header */}
      <div className='workflow-panel__header'>
        <div className='workflow-panel__header-left'>
          <span className='workflow-panel__title'>{ui.name || session.workflow_id}</span>
          <button
            type='button'
            className={`workflow-panel__status workflow-panel__status--${displayStatus}`}
            aria-label={t('chat.workflowStatusAria', { status: t(displayStatusKey) })}
            onClick={() => session && setStateGraphOpen(true)}
            title={t('chat.workflowViewWorkflow')}
          >
            {t(displayStatusKey)}
          </button>
        </div>
        <div className='workflow-panel__header-right'>
          <div className='workflow-panel__intent-btn-wrap'>
            <Dropdown trigger={['click']} menu={{
              items: [
                { key: 'intent', label: t('chat.workflowIntentBtn'), icon: <InfoCircleOutlined />, onClick: () => setIntentOpen(true) },
              ],
            }}>
              <button ref={moreButtonRef} type='button' className='workflow-panel__more-btn'
                aria-label={t('chat.workflowMoreActions')} title={t('chat.workflowMoreActions')}>
                <MoreOutlined />
              </button>
            </Dropdown>
            {intentOpen && <IntentPopover session={session} tabs={tabs} onClose={() => {
              setIntentOpen(false);
              moreButtonRef.current?.focus();
            }} />}
          </div>
          {followingEnabled && (
            <div className='workflow-panel__follow-mode' role='group' aria-label={t('chat.workflowFollowModeLabel')}>
              <button
                type='button'
                className={`workflow-panel__follow-option${followMode === 'following' ? ' workflow-panel__follow-option--active' : ''}`}
                onClick={() => {
                  setSessionFollowMode('following');
                  if (runtimeTabIdx !== -1) {
                    setActiveTabId(tabs[runtimeTabIdx].id);
                    setFocusedSortOrder(conversationId, undefined);
                  }
                }}
                aria-pressed={followMode === 'following'}
              >{t('chat.workflowFollowProgress')}</button>
              <button
                type='button'
                className={`workflow-panel__follow-option${followMode === 'free' ? ' workflow-panel__follow-option--active' : ''}`}
                onClick={() => setSessionFollowMode('free')}
                aria-pressed={followMode === 'free'}
              >{t('chat.workflowFreeBrowse')}</button>
            </div>
          )}
          <button
            type='button'
            className='workflow-panel__expand-btn'
            hidden={embedded && !externalPresentation?.onToggleExpand}
            onClick={() => externalPresentation?.onToggleExpand ? externalPresentation.onToggleExpand() : setExpandedMode(!expanded)}
            aria-label={t((embedded ? externalPresentation?.expanded : expanded) ? 'chat.workflowPanelShrink' : 'chat.workflowPanelExpand')}
            title={t((embedded ? externalPresentation?.expanded : expanded) ? 'chat.workflowPanelShrink' : 'chat.workflowPanelExpand')}
          >
            {(embedded ? externalPresentation?.expanded : expanded) ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          </button>
          {!embedded && !expanded && (
            <Tooltip
              title={anySlotEditing ? t('chat.workflowFinishEditingFirst') : undefined}
              placement='bottomRight'
            >
              <span
                className='workflow-panel__header-action-wrap'
                tabIndex={anySlotEditing ? 0 : undefined}
                aria-label={anySlotEditing ? t('chat.workflowFinishEditingFirst') : undefined}
              >
                <Popconfirm
                  title={t('chat.workflowDismissConfirmTitle')}
                  description={t('chat.workflowDismissConfirmDesc')}
                  onConfirm={handleDismiss}
                  okText={t('chat.workflowDismissConfirmOk')}
                  cancelText={t('chat.workflowDismissConfirmCancel')}
                  okButtonProps={{ danger: true, size: 'small' }}
                  cancelButtonProps={{ size: 'small' }}
                  disabled={dismissDisabled}
                  placement='bottomRight'
                >
                  <button
                    type='button'
                    className='workflow-panel__dismiss-btn'
                    disabled={dismissDisabled}
                    aria-label={t('chat.workflowDismissBtn')}
                    title={anySlotEditing ? undefined : t('chat.workflowDismissBtn')}
                  >
                    <svg width='12' height='12' viewBox='0 0 12 12' fill='none' xmlns='http://www.w3.org/2000/svg' aria-hidden='true'>
                      <path d='M2 2L10 10M10 2L2 10' stroke='currentColor' strokeWidth='1.5' strokeLinecap='round' />
                    </svg>
                  </button>
                </Popconfirm>
              </span>
            </Tooltip>
          )}
          {(!embedded || externalPresentation?.onToggleCollapse) && !panelExpanded && (
            <Tooltip
              title={collapseDisabled ? t('chat.workflowFinishEditingFirst') : undefined}
              placement='bottomRight'
            >
              <span
                className='workflow-panel__header-action-wrap'
                tabIndex={collapseDisabled ? 0 : undefined}
                aria-label={collapseDisabled ? t('chat.workflowFinishEditingFirst') : undefined}
              >
                <button
                  type='button'
                  className='workflow-panel__collapse-btn'
                  onClick={toggleCollapsed}
                  disabled={collapseDisabled}
                  aria-label={collapsed ? t('chat.workflowPanelExpand') : t('chat.workflowPanelCollapse')}
                  title={collapseDisabled
                    ? undefined
                    : collapsed
                      ? t('chat.workflowPanelExpand')
                      : t('chat.workflowPanelCollapse')}
                >
                  <svg
                    width='12'
                    height='12'
                    viewBox='0 0 12 12'
                    fill='none'
                    xmlns='http://www.w3.org/2000/svg'
                    className={`workflow-panel__collapse-icon${collapsed ? ' workflow-panel__collapse-icon--up' : ''}`}
                  >
                    <path d='M2 4L6 8L10 4' stroke='currentColor' strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round' />
                  </svg>
                </button>
              </span>
            </Tooltip>
          )}
        </div>
      </div>

      {!collapsed && isProductWorkflow(session.workflow_id) && (
        <ProductProjectViews
          key={productSectionKeys.projectViews}
          sessionId={session.session_id}
          refreshKey={`${session.updated_at}:${session.status}:${session.slots?.length ?? 0}:${productStateRevision}`}
          stageRunning={session.status === 'active'}
          disabled={actionPending}
          beforeProjectMutation={flushPendingEdits}
          onPreviewChange={setViewingProductSession}
          onBusyChange={setActionPending}
          onDecisionChanged={handleProductDecisionChanged}
          onRequestStage={(stage) => setRequestedProductStage((previous) => ({ sessionId: session.session_id, stage, requestId: (previous?.requestId ?? 0) + 1 }))}
        />
      )}

      {/* Compact step navigation; long workflows scroll horizontally. */}
      {!collapsed && hasTabs && !viewingProductArtifact && (
        <div className='workflow-panel__tabs' role='tablist' aria-label={t('chat.workflowStages')} ref={setTabsScrollRef}
          onKeyDown={(event) => {
            const direction = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
            if (!direction && event.key !== 'Home' && event.key !== 'End') return;
            event.preventDefault();
            const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
              : (visibleActiveTabIdx + direction + tabs.length) % tabs.length;
            handleTabChange(nextIndex, tabs[nextIndex].id);
            const target = event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex];
            target?.focus();
            target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
          }}>
          {tabs.map((tab, idx) => {
            const statusStepIds = tab.status_step_ids ?? [tab.step_id ?? tab.id];
            const step = session.steps
              ?.filter((s) => statusStepIds.includes(s.step_id) && s.validity !== 'stale')
              .sort((a, b) => (
                Number(b.step_id === session.current_step_id)
                - Number(a.step_id === session.current_step_id)
                || b.attempt - a.attempt
              ))[0];
            const stepStatus = step?.status;
            const tabLabel = presentWorkflowTabLabel(
              tab.label,
              renderedSession.workflow_id,
              chineseUI,
            );
            const stepStatusLabel = stepStatus
              ? t(STEP_STATUS_KEY[stepStatus] ?? 'chat.workflowStatusWaiting')
              : '';
            const runtimeMarkerVisible = idx === runtimeTabIdx && idx !== visibleActiveTabIdx;
            return (
              <React.Fragment key={tab.id}>
                {idx > 0 && (
                  <svg className='workflow-panel__tab-separator' viewBox='0 0 12 12' fill='none' aria-hidden='true'>
                    <path d='M4.5 2.5L8 6L4.5 9.5' stroke='currentColor' strokeWidth='1.25' strokeLinecap='round' strokeLinejoin='round' />
                  </svg>
                )}
                <button
                  role='tab'
                  id={`workflow-tab-${session.session_id}-${tab.id}`}
                  tabIndex={idx === visibleActiveTabIdx ? 0 : -1}
                  aria-selected={idx === visibleActiveTabIdx}
                  aria-controls={`workflow-tab-panel-${tab.id}`}
                  className={`workflow-panel__tab${idx === visibleActiveTabIdx ? ' workflow-panel__tab--active' : ''}${idx === runtimeTabIdx ? ' workflow-panel__tab--runtime-current' : ''}`}
                  onClick={() => handleTabChange(idx, tab.id)}
                  type='button'
                >
                  <span className='workflow-panel__tab-badge' aria-hidden='true'>{idx + 1}</span>
                  <span className='workflow-panel__tab-label'>{tabLabel}</span>
                  {runtimeMarkerVisible && (
                    <span className='workflow-panel__tab-runtime-marker'>
                      <span className='workflow-panel__tab-runtime-dot' aria-hidden='true' />
                      {t('chat.workflowCurrentStep')}
                    </span>
                  )}
                  {shouldShowStandaloneStepStatus(stepStatus, runtimeMarkerVisible) && (
                    <span
                      className={`workflow-panel__step-status workflow-panel__step-status--${stepStatus}`}
                      aria-label={t('chat.workflowStepStatusAria', { status: stepStatusLabel })}
                      title={stepStatusLabel}
                    />
                  )}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      )}

      </div>

      <div className='workflow-panel__trust-notice' role='note'>
        <InfoCircleOutlined aria-hidden='true' />
        <span>{t('chat.workflowFullTrustNotice')}</span>
      </div>

      {!collapsed && externalPresentation && runningTasks.length > 0 && <div className='workflow-external-activity'>
        <div className='workflow-external-activity__text' role='status'>
          {latestActivity?.kind ? t(`chat.workflowActivity_${latestActivity.kind}`, { tool: latestActivity.tool }) : t('chat.workflowActivity_working')}
        </div>
        {runningTasks.filter(task => !activities[task.task_id]?.finished).map(task => {
          const progress = activities[task.task_id]?.progress;
          return <div key={task.task_id} className={`workflow-external-activity__progress${progress === undefined ? ' workflow-external-activity__progress--indeterminate' : ''}`}
            role='progressbar' aria-label={t('chat.workflowStepProgress', { step: tabs.find(tab => (tab.status_step_ids ?? [tab.step_id ?? tab.id]).includes(task.step_id))?.label ?? task.step_id })}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
            <span style={{ width: `${progress ?? 30}%` }} />
          </div>;
        })}
      </div>}

      {/* Body */}
      {!collapsed && (
        <ProductCurrentStageView key={productSectionKeys.currentStage} sessionId={session.session_id} hidden={viewingProductArtifact}>
          {hasTabs ? (
            tabs.map((tab, idx) => {
              const preview = externalPresentation && !anySlotEditing ? executionPreview(session, tab, activities) : session;
              const previewing = preview !== session;
              return <div
                key={tab.id}
                id={`workflow-tab-panel-${tab.id}`}
                role='tabpanel'
                aria-labelledby={`workflow-tab-${session.session_id}-${tab.id}`}
                hidden={idx !== visibleActiveTabIdx}
              >
                <WorkflowPanelTabActiveContext.Provider value={idx === visibleActiveTabIdx}>
                <SlotDownloadContext.Provider value={!previewing && workflowTabAllowsDownload(tab, idx, tabs.length)}>
                  {previewing && <div className="workflow-panel__preview-label" role="status">{t('chat.workflowGeneratingPreview')}</div>}
                  <TabSlotGrid
                    tab={executionPreviewTab(tab, session, preview)}
                    session={preview}
                    readOnly={previewing || isWorkflowSessionReadOnly(session, autoRunning)}
                    tasks={taskCenterTasks}
                    onRefresh={refresh}
                    onReference={onReference}
                    onFocusSortOrder={handleFocusSortOrder}
                  />
                </SlotDownloadContext.Provider>
                </WorkflowPanelTabActiveContext.Provider>
              </div>;
            })
          ) : (
            <AutoSlotGrid
              session={{ ...session, slots: filterFallbackWorkflowSlots(session.workflow_id, session.slots ?? [], ui) }}
              onRefresh={refresh}
              onReference={onReference}
            />
          )}
        </ProductCurrentStageView>
      )}

      {!collapsed && session.status === 'completed' && isProductWorkflow(session.workflow_id) && (
        <ProductStageRelay
          key={productSectionKeys.stageRelay}
          sessionId={session.session_id}
          refreshKey={productStateRevision}
          disabled={buttonsDisabled}
          beforeAction={flushPendingEdits}
          onBusyChange={setActionPending}
          onSessionReady={handleProductSessionReady}
          preferredStage={requestedProductStage?.sessionId === session.session_id ? requestedProductStage : undefined}
        />
      )}

      {/* Footer */}
      {!collapsed && !viewingProductArtifact && (showActions || controlAdapter) && (documentFooter.actionItems.length > 0 || documentFooter.statusMessages.length > 0
        || rollbackSteps.length > 0 || sessionBusy || (showContinue && !approvalStepId) || displayStatus === 'failed' || displayStatus === 'stopped') && (
        <div className='workflow-panel__footer' role='group' aria-label={t('chat.workflowSessionControls')}>
          {actionError && (
            <span
              className='workflow-panel__footer-action-status workflow-panel__footer-action-status--error'
              role='alert'
            >
              {actionError}
            </span>
          )}
          {documentFooter.actionItems.length > 0 || documentFooter.statusMessages.length > 0 ? (
            <div className='workflow-panel__footer-document'>
              {documentFooter.statusMessages.length > 0 || documentFooter.actionItems.some(item => item.kind === 'link') ? (
                <div className='workflow-panel__footer-meta'>
                  {documentFooter.actionItems.filter(item => item.kind === 'link').map(item => item.kind === 'link' && (
                    <a key={item.key} className='workflow-panel__footer-link' href={item.href} target='_blank' rel='noopener noreferrer'>
                      {item.label}<ExportOutlined aria-hidden />
                    </a>
                  ))}
                  {documentFooter.statusMessages.map((message) => (
                    <span
                      key={message.key}
                      className={
                        message.tone === 'error'
                          ? 'workflow-panel__footer-action-status workflow-panel__footer-action-status--error'
                          : message.tone === 'success'
                            ? 'workflow-panel__footer-action-status workflow-panel__footer-action-status--success'
                            : 'workflow-panel__footer-action-status'
                      }
                      role={message.tone === 'error' ? 'alert' : 'status'}
                    >
                      {message.text}
                    </span>
                  ))}
                </div>
              ) : null}
              {documentFooter.actionItems.length > 0 ? (
                <div className='workflow-panel__footer-actions'>
                  {documentFooter.actionItems.map((item) => {
                    if (item.kind === 'link') return null;

                    const { action } = item;
                    return (
                      <div key={item.key} className={action.menu ? 'workflow-panel__split-action' : undefined}>
                        <button
                          key={item.key}
                          type='button'
                          className={`workflow-panel__action-btn workflow-panel__action-btn--${action.tone ?? 'secondary'}`}
                          disabled={actionPending || action.disabled}
                          aria-disabled={actionPending || action.disabled}
                          onClick={() => {
                            if (action.flushBeforeAction) {
                              void runFooterAction(action.onClick, action.flushKey);
                              return;
                            }
                            action.onClick();
                          }}
                        >
                          {action.icon === 'write-back' ? <CloudUploadOutlined aria-hidden /> : null}
                          {action.icon === 'download' ? <DownloadOutlined aria-hidden /> : null}
                          {action.icon === 'copy' ? <CopyOutlined aria-hidden /> : null}
                          {action.label}
                        </button>
                        {action.menu && (
                          <Dropdown
                            menu={{
                              className: action.selectedMenuKey ? 'workflow-panel__format-menu' : undefined,
                              selectable: Boolean(action.selectedMenuKey),
                              selectedKeys: action.selectedMenuKey ? [action.selectedMenuKey] : [],
                              items: action.menu.map((option) => ({
                                ...option,
                                onClick: () => { if (action.flushBeforeAction) void runFooterAction(option.onClick, action.flushKey); else option.onClick(); },
                                icon: action.selectedMenuKey
                                  ? <span className='workflow-panel__format-radio' aria-hidden='true' />
                                  : option.icon,
                              })),
                            }}
                            trigger={['click']}
                            disabled={actionPending || action.disabled}
                          >
                            <button type='button' className={`workflow-panel__action-btn workflow-panel__action-btn--${action.tone ?? 'secondary'}`}
                              disabled={actionPending || action.disabled} aria-label={action.menuLabel ?? t('chat.writerCopy.chooseFormat')}>
                              <DownOutlined />
                            </button>
                          </Dropdown>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}
          {sessionBusy && !approvalStepId && (
            <span className='workflow-panel__execution-status' role='status'>
              {t('chat.workflowStatusRunning')}{session.current_step_id ? ` · ${stepLabel(session.current_step_id)}` : ''}
            </span>
          )}
          {displayStatus === 'active' && (onStop || controlAdapter) && supportsExternal('stop') && (
            <button
              type='button'
              className='workflow-panel__action-btn workflow-panel__action-btn--danger'
              onClick={controlAdapter
                ? () => { void runFooterAction(() => controlAdapter.execute({ kind: 'stop' }), undefined, false, true); }
                : handleStop}
              title={t('chat.workflowStop')}
            >
              {t('chat.workflowStop')}
            </button>
          )}
          {((displayStatus === 'failed' || displayStatus === 'stopped') && supportsExternal('retry') || (isProductWorkflow(session.workflow_id) && showRetry)) && (
            <button
              type='button'
              className='workflow-panel__action-btn workflow-panel__action-btn--secondary'
              disabled={buttonsDisabled}
              aria-disabled={buttonsDisabled}
              onClick={handleRetry}
              title={
                actionPending
                  ? t('chat.workflowSavingBeforeAction')
                  : buttonsDisabled
                    ? t('chat.workflowBtnDisabledHint')
                    : anySlotEditing
                      ? t('chat.workflowRetryFlushHint')
                      : session.status === 'failed' && isProductWorkflow(session.workflow_id)
                        ? t('chat.workflowRetryLatestHint')
                        : t('chat.workflowRetry')
              }
            >
              {actionPending ? t('chat.workflowSavingBeforeAction') : t('chat.workflowRetry')}
            </button>
          )}
          {showContinue && !approvalStepId && supportsExternal(
            externalControl?.continuation === 'stopped' ? 'resume' : completedContinueStepId ? 'rewind' : 'continue',
          ) && (
            <button
              type='button'
              className='workflow-panel__action-btn workflow-panel__action-btn--primary'
              disabled={continueDisabled}
              aria-disabled={continueDisabled}
              onClick={handleContinue}
              title={
                currentStepStatus === 'failed'
                  ? t('chat.workflowContinueDisabledFailed')
                  : isProductWorkflow(session.workflow_id) && !cachedContinueTargetAvailable
                    ? t('chat.workflowCommandTargetUnavailable')
                  : actionPending
                    ? t('chat.workflowSavingBeforeAction')
                    : buttonsDisabled
                      ? t('chat.workflowBtnDisabledHint')
                      : anySlotEditing
                        ? t('chat.workflowContinueFlushHint')
                        : completedContinueStepId
                          ? t('chat.workflowContinueWithLatestOutline')
                          : continueLabel
              }
            >
              {actionPending ? t('chat.workflowSavingBeforeAction') : continueLabel}
            </button>
          )}
          {rollbackSteps.length > 0 && (
            <div className='workflow-panel__rollback' role='group' aria-label={t('chat.workflowRollbackLabel')}>
              <span className='workflow-panel__rollback-label'>{t('chat.workflowRollbackLabel')}</span>
              <div className='workflow-panel__rollback-steps'>
                {rollbackSteps.map(step => (
                  <button key={step.step_id} type='button'
                    className='workflow-panel__action-btn workflow-panel__action-btn--secondary'
                    disabled={buttonsDisabled}
                    onClick={() => handleRollback(step.step_id)}
                    title={actionPending ? t('chat.workflowSavingBeforeAction')
                      : buttonsDisabled ? t('chat.workflowBtnDisabledHint')
                        : `${t('chat.workflowRollbackPrefix')}${stepLabel(step.step_id)}`}>
                    {stepLabel(step.step_id)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    {!collapsed && approvalStepId && (!externalControl
      || Boolean(pendingReview && (availableActions.has('confirm_and_continue') || availableActions.has('confirm')))) && (
      <WorkflowApprovalActions disabled={continueDisabled} onContinue={scope => {
        void handleContinueWithApprovalPreference(scope);
      }} />
    )}
    </div>
    {session && (
      <StateGraphModal
        open={stateGraphOpen}
        onClose={() => setStateGraphOpen(false)}
        sessionId={session.session_id}
        workflowId={session.workflow_id}
        liveRefresh
        conversationId={conversationId}
      />
    )}
    </SlotEditingContext.Provider>
    </ExternalWorkflowPresentationContext.Provider>
  );

  if (expanded && !embedded) {
    const host = document.querySelector('.detail-container');
    if (host) return createPortal(panel, host);
  }
  return panel;
}
