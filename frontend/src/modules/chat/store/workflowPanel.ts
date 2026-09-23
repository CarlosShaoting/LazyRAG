import type { Descriptor } from "@/api/generated/core-client";
import { create } from "zustand";
import { WorkflowInfoApi, WorkflowSessionApi, TempUploadServiceApi } from "@/modules/chat/utils/request";
import i18n from "@/i18n";
import type { ChatConfig } from "@/modules/chat/components/ChatConfigs";
import { extractErrorCode, getLocalizedErrorMessage } from "@/components/request";
import {
  emptyWorkflowProjection,
  markWorkflowResyncRequired,
  reduceWorkflowEvent,
  type WorkflowProjectionState,
  type WorkflowStreamEvent,
} from '@/modules/chat/store/workflowProjection';
import {
  subscribeWorkflowEventStream,
  type WorkflowEventStreamSubscription,
} from '@/modules/chat/utils/workflowEventStream';
import { reconcileWorkflowSessionStatus } from '@/modules/chat/store/workflowStatus';

export function buildWorkflowSearchConfig(
  chatConfig?: Pick<ChatConfig, "knowledgeBaseId" | "creators" | "tags">,
): Record<string, unknown> {
  const kbIds = chatConfig?.knowledgeBaseId?.filter(Boolean) ?? [];
  return {
    dataset_list: kbIds.map((id) => ({ id })),
    creators: chatConfig?.creators ?? [],
    tags: chatConfig?.tags ?? [],
  };
}

// ---------------------------------------------------------------------------
// DraftStore — two-layer draft management for slot text editing
// key format: `${sessionId}:${slotId}:${listIndex}`
// ---------------------------------------------------------------------------

interface DraftEntry {
  value: Record<string, unknown>;
  timer: ReturnType<typeof setTimeout> | null;
  /** The list_index to use when calling the backend API (-1 for single/NULL slots). */
  apiListIndex: number;
  baseRevision?: number;
  baseDraftVersion?: number;
}

const DRAFT_FLUSH_DELAY_MS = 60_000;
const DRAFT_LS_PREFIX = 'slotDraft:';
const DRAFT_BASELINE_LS_PREFIX = 'slotDraftBaseline:';

const _drafts = new Map<string, DraftEntry>();

function readDraftBaseline(key: string): Pick<DraftEntry, 'baseRevision' | 'baseDraftVersion'> {
  try {
    const raw = localStorage.getItem(DRAFT_BASELINE_LS_PREFIX + key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as { baseRevision?: unknown; baseDraftVersion?: unknown };
    return {
      baseRevision: typeof parsed.baseRevision === 'number' ? parsed.baseRevision : undefined,
      baseDraftVersion: typeof parsed.baseDraftVersion === 'number'
        ? parsed.baseDraftVersion
        : undefined,
    };
  } catch {
    return {};
  }
}

// A write-back can finish while a session request that started earlier is still
// in flight. Do not discard the refresh in that case: queue one follow-up load
// so the selected artifact eventually converges to the new provider_sync revision.
const _activeSessionLoads = new Map<string, Promise<void>>();
const _queuedActiveSessionLoads = new Map<string, { silentError?: boolean }>();

function _draftKey(sessionId: string, slotId: string, listIndex: number): string {
  return `${sessionId}:${slotId}:${listIndex}`;
}

export const draftStore = {
  /** Write value to localStorage and reset the 60s auto-flush timer.
   *  apiListIndex: the list_index to use for the backend PATCH call.
   *  Pass -1 for single (non-list) slots. Defaults to listIndex when omitted.
   */
  setDraft(
    sessionId: string,
    slotId: string,
    listIndex: number,
    value: Record<string, unknown>,
    apiListIndex?: number,
    baseRevision?: number,
    baseDraftVersion?: number,
  ) {
    const key = _draftKey(sessionId, slotId, listIndex);
    const existing = _drafts.get(key);
    if (existing?.timer) clearTimeout(existing.timer);
    try {
      localStorage.setItem(DRAFT_LS_PREFIX + key, JSON.stringify(value));
    } catch { /* storage full — ignore */ }
    const effectiveApiIndex = apiListIndex ?? existing?.apiListIndex ?? listIndex;
    const persistedBaseline = existing ? {} : readDraftBaseline(key);
    const effectiveBaseRevision = existing?.baseRevision
      ?? persistedBaseline.baseRevision
      ?? baseRevision;
    const effectiveBaseDraftVersion = existing?.baseDraftVersion
      ?? persistedBaseline.baseDraftVersion
      ?? baseDraftVersion;
    try {
      localStorage.setItem(DRAFT_BASELINE_LS_PREFIX + key, JSON.stringify({
        baseRevision: effectiveBaseRevision,
        baseDraftVersion: effectiveBaseDraftVersion,
      }));
    } catch { /* storage full — ignore */ }
    const timer = setTimeout(() => {
      draftStore.flushDraft(sessionId, slotId, listIndex, effectiveApiIndex);
    }, DRAFT_FLUSH_DELAY_MS);
    _drafts.set(key, {
      value,
      timer,
      apiListIndex: effectiveApiIndex,
      baseRevision: effectiveBaseRevision,
      baseDraftVersion: effectiveBaseDraftVersion,
    });
  },

  /** Clear timer and call patchSlotItemValue to produce a human revision. Does NOT clear localStorage.
   *  apiListIndex: when provided, used for the backend PATCH call (e.g. -1 for single slots);
   *  otherwise falls back to the stored entry's apiListIndex, then listIndex.
   *
   *  When the original artifact value contained a `path` field (large content was offloaded),
   *  the draft text is first uploaded via POST /temp/uploads, then the PATCH carries the new
   *  stored_path instead of the raw text — preserving the large-content offload contract.
   */
  async flushDraft(sessionId: string, slotId: string, listIndex: number, apiListIndex?: number): Promise<boolean> {
    const key = _draftKey(sessionId, slotId, listIndex);
    let value: Record<string, unknown> | null = null;
    let baseline: Pick<DraftEntry, 'baseRevision' | 'baseDraftVersion'> = {};
    let targetIndex = apiListIndex ?? listIndex;
    const entry = _drafts.get(key);
    if (entry) {
      if (entry.timer) clearTimeout(entry.timer);
      _drafts.set(key, { ...entry, timer: null });
      value = entry.value;
      baseline = entry;
      targetIndex = apiListIndex ?? entry.apiListIndex;
    } else {
      value = draftStore.getLocalDraft(sessionId, slotId, listIndex);
      baseline = readDraftBaseline(key);
    }
    if (!value) return false;

    // Detect large-content (offloaded) draft: value carries {text: string, _isOffloaded: true}
    // When the original artifact had a `path` field the SlotText component sets _isOffloaded=true
    // so we know to re-upload the edited text instead of writing it inline to the DB.
    let patchValue = value;
    if (value._isOffloaded && typeof value.text === 'string') {
      try {
        const text = value.text as string;
        const blob = new Blob([text], { type: 'text/plain' });
        const filename = (value._originalFilename as string | undefined) ?? 'artifact.txt';
        const api = TempUploadServiceApi();
        const initRes = await api.initUpload({ filename, size: blob.size, content_type: 'text/plain' });
        const uploadId: string = initRes.data?.data?.upload_id ?? initRes.data?.upload_id;
        await api.uploadPart(uploadId, 1, blob);
        const completeRes = await api.completeUpload(uploadId, { parts: [{ part_number: 1, size: blob.size }] });
        const storedPath: string = completeRes.data?.data?.stored_path ?? completeRes.data?.stored_path;
        patchValue = { type: 'text', path: storedPath, size: blob.size };
      } catch {
        // Upload failed — fall back to inline patch so user doesn't lose their edit
        patchValue = { text: value.text as string };
      }
    }

    try {
      await useWorkflowStore.getState().patchSlotItemValue(
        sessionId,
        slotId,
        targetIndex,
        patchValue,
        undefined,
        'checkpoint',
        baseline.baseRevision,
        baseline.baseDraftVersion,
      );
    } catch {
      return false;
    }
    _drafts.delete(key);
    try { localStorage.removeItem(DRAFT_LS_PREFIX + key); } catch { /* ignore */ }
    try { localStorage.removeItem(DRAFT_BASELINE_LS_PREFIX + key); } catch { /* ignore */ }
    return true;
  },

  /** Flush all pending drafts for a session in parallel. Used before sending chat. */
  async flushAllDrafts(sessionId: string): Promise<void> {
    const prefix = `${sessionId}:`;
    const tasks: Promise<boolean>[] = [];
    for (const key of Array.from(_drafts.keys())) {
      if (!key.startsWith(prefix)) continue;
      const parts = key.split(':');
      if (parts.length < 3) continue;
      const slotId = parts[1];
      const listIndex = Number(parts[2]);
      if (!slotId || isNaN(listIndex)) continue;
      tasks.push(draftStore.flushDraft(sessionId, slotId, listIndex));
    }
    await Promise.all(tasks);
  },

  /** Discard draft without producing a revision. Clears localStorage and timer. */
  cancelDraft(sessionId: string, slotId: string, listIndex: number) {
    const key = _draftKey(sessionId, slotId, listIndex);
    const existing = _drafts.get(key);
    if (existing?.timer) clearTimeout(existing.timer);
    _drafts.delete(key);
    try {
      localStorage.removeItem(DRAFT_LS_PREFIX + key);
      localStorage.removeItem(DRAFT_BASELINE_LS_PREFIX + key);
    } catch { /* ignore */ }
  },

  /** Read a persisted draft from localStorage (for mount-time restore). */
  getLocalDraft(sessionId: string, slotId: string, listIndex: number): Record<string, unknown> | null {
    const key = _draftKey(sessionId, slotId, listIndex);
    try {
      const raw = localStorage.getItem(DRAFT_LS_PREFIX + key);
      if (!raw) return null;
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  },
};

export interface SlotRevision {
  artifact_id?: string;
  document?: Descriptor;
  document_error?: { code: string; retryable: boolean };
  slot_id: string;
  revision: number;
  draft_version?: number;
  list_index?: number;
  /** 1-based display position within a list slot; computed from order_list. */
  sort_order?: number;
  /** Optimistic-lock version of the slot order row; present on list-slot items. */
  order_version?: number;
  selected: boolean;
  slot: string;
  step_id?: string;
  created_at: string;
  /** Artifact content type returned by the backend (e.g. 'text', 'image', 'file'). */
  content_type?: string;
  /** Artifact value as returned by the backend — shape depends on content_type. */
  artifact_value?: any;
  /** Human-readable description for image/file artifacts. */
  caption?: string;
  /** change_source: ai / human / provider_sync (cloud-provider-confirmed). */
  change_source?: "ai" | "human" | "provider_sync";
  /** Whether this draft has a server-owned cloud-provider baseline. */
  write_back_ready?: boolean;
  /** Whether the selected draft differs from that cloud-provider baseline. */
  write_back_dirty?: boolean;
  /** Server-owned delivery state for the selected draft. */
  write_back_state?: 'initial_delivery' | 'synced_clean' | 'synced_dirty' | 'blocked';
  /** Public cloud document URL resolved by the server from source_document. */
  write_back_url?: string;
  /** Host-local path for a provider target backed by a local file. */
  write_back_local_path?: string;
  /** Cloud provider bound to source_document, for example "feishu". */
  provider?: string;
  /** Stable cloud-document identity. It is never a local revision number. */
  provider_document_id?: string;
  /** Most recent local revision confirmed equal to the cloud document. */
  last_synced_revision?: number;
  /** User-visible version number for the selected revision. Mutable drafts reuse the previous number. */
  version_number?: number;
  /** User-visible version number most recently confirmed equal to the cloud document. */
  last_synced_version?: number;
  /** Server-selected editing capability; it does not expose the backing provider. */
  editor_profile?: string;
  /** Number of user-visible versions for this (slot_id, list_index). */
  revision_count?: number;
}

export interface WorkflowSession {
  session_id: string;
  state_version?: number;
  conversation_id: string;
  workflow_id: string;
  /** Execution mode selected when this immutable session was created. */
  workflow_mode: 'auto' | 'dynamic';
  /** Immutable package revision selected when this session was created. */
  pinned_revision_id?: string;
  status: "active" | "completed" | "failed" | "waiting" | "stopped";
  current_step_id: string;
  /** Global intent/constraint for this session, JSON string e.g. {"text":"..."} */
  intent_context?: string;
  created_at: string;
  updated_at: string;
  slots?: SlotRevision[];
  /** Steps for this session, used in completed/waiting state to render rollback step list. */
  steps?: WorkflowSessionStep[];
  /** Go-authoritative runtime projection. Never derive Ready/Past from steps locally. */
  projection?: WorkflowRuntimeProjection;
  /** Fatal runtime error that makes this conversation's pinned workflow graph unusable. */
  runtime_error_code?: string;
  runtime_error_message?: string;
  /** UI focus state mirrored onto the session for legacy readers; the source of
   *  truth lives in `focusedTabByConversation` / `focusedSortOrderByConversation`
   *  so it survives `setSession()` refreshes. */
  focusedTab?: string;
  focusedSortOrder?: number;
}

/** A single step execution record from workflow_session_steps. */
export interface WorkflowSessionStep {
  id: string;
  session_id: string;
  step_id: string;
  attempt: number;
  task_id: string;
  status: string;
  validity?: "effective" | "stale";
  /** Step-level intent/constraint, JSON string e.g. {"text":"..."} */
  intent_context?: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRuntimeProjection {
  status?: string;
  current_step_id?: string;
  attempt_history?: Record<string, Array<{ attempt: number; task_id: string; status: string; validity: string; started_at: string; updated_at?: string; intent_context?: string }>>;
  completed?: boolean;
  past?: string[];
  current?: string[];
  reachable?: string[];
  ready?: string[];
  retryable?: string[];
  rewindable?: string[];
  continue?: string[];
  blocked?: string[];
  stale?: string[];
  pruned?: string[];
  bypassed?: string[];
  nodes?: Record<string, {
    requires_approval: boolean;
    execution: string;
    validity: string;
    reachability: string;
    readiness: string;
    branch: string;
  }>;
}

export function workflowSnapshotSteps(sessionId: string, history: WorkflowRuntimeProjection['attempt_history']): WorkflowSessionStep[] | undefined {
  if (!history) return undefined;
  return Object.entries(history).flatMap(([stepId, attempts]) => stepId === '__end__' ? [] : attempts.map((attempt) => ({
    id: attempt.task_id, session_id: sessionId, step_id: stepId, task_id: attempt.task_id,
    attempt: attempt.attempt, status: attempt.status, validity: attempt.validity === "stale" ? "stale" as const : "effective" as const,
    created_at: attempt.started_at, updated_at: attempt.updated_at ?? attempt.started_at,
    intent_context: attempt.intent_context,
  })));
}

// UI tab/slot declaration from workflow.yaml.
export interface SlotDef {
  id: string;
  label: string;
  type: "image" | "text" | "file";
  cardinality?: "single" | "list";
  exposed?: boolean;
  /** Whether this list slot supports drag-reorder. */
  ordered?: boolean;
  /** The slot key used for the caption of this slot's items. */
  caption_key?: string;
  /** Maximum characters shown in the artifact summary injected into the AI prompt. */
  summary_max_chars?: number;
  /** Runtime widget configuration from ui.slots, hydrated when the workflow UI is loaded. */
  widget?: SlotWidgetConfig;
}

export interface SlotWidgetConfig {
  widgetType?: string;
  readOnly?: boolean;
  maxHeight?: number;
  collapsed?: boolean;
  itemLayout?: 'scroll' | 'grid';
  gridMaxCols?: number;
  itemWidth?: number;
  itemHeight?: number;
  [key: string]: unknown;
}

// composite_layout node types (recursive) — format C.
export interface CompositePanelNode {
  /** Leaf: single slot id. */
  slot?: string;
  /** Leaf: tab-switching area, each item is a slot id. Tab title is derived from slot label. */
  tabs?: string[];
  /** Container: split direction. */
  direction?: 'row' | 'column';
  children?: CompositePanelNode[];
  weight?: number;
}

// Legacy composite layout types kept for backward-compat parsing in buildColumns.
export type CompositeLayoutNode =
  | string
  | CompositeColumnNode
  | InnerTabsNode;

export interface CompositeColumnNode {
  slot?: string | InnerTabsNode;
  weight?: number;
}

export interface InnerTabsNode {
  tabs: CompositeLayoutNode[];
}

/** Declarative action rendered for a workflow tab. */
export interface WorkflowTabAction {
  id: string;
  type: 'export';
  provider: string;
  label?: string;
  /** Provider input names mapped to declared slot ids. */
  inputs: Record<string, string>;
  formats?: string[];
  /** Align mapped list slots by their shared sort_order. */
  alignment?: 'sort_order';
}

export interface TabDef {
  id: string;
  /** Optional workflow step id represented by this tab. Falls back to id when omitted. */
  step_id?: string;
  /** Artifact producer scope. `selected` lets a composite join adjacent workflow steps. */
  slot_scope?: 'step' | 'selected';
  status_step_ids?: string[];
  label: string;
  layout?: 'grid' | 'list' | 'vertical' | 'composite' | 'horizontal';
  slots: SlotDef[];
  /** Composite layout tree (format C) or legacy array (will be normalised at runtime). */
  composite_layout?: CompositePanelNode | CompositeLayoutNode[];
  /** Composite mode: global tab-bar position. */
  composite_tab_position?: 'top' | 'bottom' | 'left' | 'right';
  /**
   * Generic composite display rules declared by the workflow.
   * WorkflowPanel must not special-case workflow IDs; it only executes these rules.
   */
  composite_behavior?: CompositeBehavior;
  /** Hide this tab once the named material has a selected revision. */
  hide_when_material?: string;
  /** Explicitly enable or disable artifact downloads for this tab. */
  allow_download?: boolean;
  /** Actions are rendered through provider modules; the composite stays domain-neutral. */
  actions?: WorkflowTabAction[];
  /** Optional next step exposed after this tab completes; declared by the workflow package. */
  completed_continue_step?: string;
}

export function workflowTabAllowsDownload(
  tab: TabDef,
  index: number,
  total: number,
): boolean {
  return typeof tab.allow_download === 'boolean'
    ? tab.allow_download
    : index === total - 1;
}

/**
 * Apply workflow-declared tab visibility without workflow-specific frontend logic.
 *
 * When readyMaterial is configured, conditional tabs stay hidden until that
 * material exists. This avoids flashing the complete graph while an initial
 * planning step is still deriving skip materials from the launch parameters.
 */
export function filterWorkflowTabs(
  tabs: TabDef[] = [],
  slots: SlotRevision[] = [],
  readyMaterial?: string,
): TabDef[] {
  const present = new Set(
    slots.filter((slot) => slot.selected).map((slot) => slot.slot),
  );
  const visibilityReady = !readyMaterial || present.has(readyMaterial);
  return tabs.filter((tab) => {
    if (!tab.hide_when_material) return true;
    if (!visibilityReady) return false;
    return !present.has(tab.hide_when_material);
  });
}

/** Mutually exclusive column group: keep the first preferred slot that has data. */
export interface CompositeMutuallyExclusiveGroup {
  slots: string[];
  /** Preference order when multiple group members have data. Defaults to `slots`. */
  prefer?: string[];
}

/** Show one configured slot only when another selected material has the expected scalar value. */
export interface CompositeVisibleWhenCondition {
  slot: string;
  material: string;
  /** Optional dot-separated path inside the artifact value. */
  path?: string;
  equals: string | number | boolean;
}

/**
 * Workflow-declared composite display behavior (UI schema).
 * - hide_empty_columns: drop columns with no matching revisions
 * - empty_column_scope: which revisions count as non-empty
 * - mutually_exclusive: among a group, show only one winner column
 * - visible_when: show a slot only when a selected material equals the declared value
 */
export interface CompositeBehavior {
  hide_empty_columns?: boolean;
  empty_column_scope?: 'selected' | 'tab';
  /** Reuse a slot's sole revision on every composite page when no exact sort_order exists. */
  repeat_single_slots?: string[];
  mutually_exclusive?: CompositeMutuallyExclusiveGroup[];
  visible_when?: CompositeVisibleWhenCondition[];
}

function unwrapWorkflowArtifactScalar(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  const record = value as Record<string, unknown>;
  for (const key of ['text', 'value', 'data']) {
    const candidate = record[key];
    if (candidate === null || ['string', 'number', 'boolean'].includes(typeof candidate)) {
      return candidate;
    }
  }
  return value;
}

function normalizeWorkflowArtifactScalar(value: unknown): string {
  const scalar = unwrapWorkflowArtifactScalar(value);
  return typeof scalar === 'string'
    ? scalar.trim().toLowerCase()
    : String(scalar ?? '').trim().toLowerCase();
}

function readWorkflowArtifactPath(value: unknown, path?: string): unknown {
  if (!path) return value;
  let current = value;
  for (const segment of path.split('.')) {
    if (!segment || !current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

/** Match declarative UI conditions against the latest selected material revision. */
export function workflowMaterialEquals(
  slots: SlotRevision[] = [],
  material: string,
  expected: string | number | boolean,
  path?: string,
): boolean {
  const latest = slots
    .filter((slot) => slot.selected && slot.slot === material)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0];
  if (!latest) return false;
  return normalizeWorkflowArtifactScalar(readWorkflowArtifactPath(latest.artifact_value, path))
    === normalizeWorkflowArtifactScalar(expected);
}

/** Apply value-based slot visibility without coupling the renderer to a workflow id. */
export function filterWorkflowSlotIdsByConditions(
  slotIds: string[],
  slots: SlotRevision[] = [],
  conditions: CompositeVisibleWhenCondition[] = [],
): string[] {
  const allowed = new Set(slotIds);
  for (const condition of conditions) {
    if (!allowed.has(condition.slot)) continue;
    if (!workflowMaterialEquals(slots, condition.material, condition.equals, condition.path)) {
      allowed.delete(condition.slot);
    }
  }
  return slotIds.filter((slotId) => allowed.has(slotId));
}

const DESIGN_DOMAIN_LABELS: Record<string, string> = {
  domain_state: '领域对象与状态',
  behavior_policy_trust: '行为、策略与信任',
  ia_semantics: '信息架构与语义',
  journey_interaction_service: '用户旅程、交互与服务',
  ui_visual_system: '界面与视觉系统',
  content_communication: '内容与沟通',
};

const DESIGN_GATE_LABELS: Record<string, string> = {
  privacy: '隐私数据',
  identity: '企业身份',
  permission: '权限控制',
  silent_write: '静默写入外部系统',
  cross_tenant: '跨租户隔离',
  high_loss_irreversible: '高损失或不可逆操作',
};

/** Build a Chinese display summary from the authoritative design-routing record. */
export function buildChineseDesignRoutingSummary(value: unknown): string | null {
  const wrapper = value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
  const record = wrapper?.data && typeof wrapper.data === 'object' && !Array.isArray(wrapper.data)
    ? wrapper.data as Record<string, unknown>
    : wrapper;
  if (!record || !Array.isArray(record.decisions)) return null;

  const decisions = record.decisions.filter(
    (decision): decision is Record<string, unknown> => Boolean(decision && typeof decision === 'object' && !Array.isArray(decision)),
  );
  const heavyCount = decisions.filter((decision) => String(decision.effort).toLowerCase() === 'heavy').length;
  const lightCount = decisions.filter((decision) => String(decision.effort).toLowerCase() === 'light').length;
  const route = String(record.overall_effort).toLowerCase() === 'heavy' ? '重型' : '轻量';
  const domains = Array.isArray(record.primary_domains)
    ? record.primary_domains.map((domain) => DESIGN_DOMAIN_LABELS[String(domain)] ?? String(domain)).join('、')
    : '尚待确认';
  const gates = Array.from(new Set(decisions.flatMap((decision) =>
    Array.isArray(decision.hard_gates) ? decision.hard_gates.map(String) : [],
  )));
  const gateSummary = gates.length
    ? gates.map((gate) => DESIGN_GATE_LABELS[gate] ?? gate).join('、')
    : '未触发强制升级门槛';
  const goal = typeof record.product_goal_basis === 'string' && record.product_goal_basis.trim()
    ? record.product_goal_basis.trim()
    : '沿用当前项目的产品目标与已有材料';
  const nextEvidence = route === '重型'
    ? '后续仅展示并执行重型证据流程，重点核验权限、隐私、跨租户隔离、外部写入与不可逆风险。'
    : '后续仅展示并执行轻量证据流程，聚焦已有事实、关键假设与低成本验证。';

  return [
    '## 产品方案内部路由',
    '',
    `- **产品目标依据：** ${goal}`,
    `- **研究路径：** ${route}`,
    `- **方案覆盖范围：** ${domains}`,
    `- **子决策：** 共 ${decisions.length} 项，其中重型 ${heavyCount} 项、轻量 ${lightCount} 项`,
    `- **关键风险门槛：** ${gateSummary}`,
    '',
    nextEvidence,
    '',
    '路由已完成并通过校验。当前在证据收集前暂停，等待你确认方案范围。',
  ].join('\n');
}

export interface WorkflowUI {
  name?: string;
  tabs?: TabDef[];
  /** Defer tabs with hide_when_material until this planning material exists. */
  tab_visibility_ready_material?: string;
  /** Global widget config keyed by slot id. */
  slots?: Record<string, Record<string, unknown>>;
  /** Authoritative root-slot visibility, retained for the layout-free fallback. */
  exposed_slot_ids?: string[];
}

const PRODUCT_FALLBACK_ARTIFACTS = new Set([
  'direction_document', 'direction_brief', 'competitive_analysis',
  'design_document', 'product_design_spec', 'prd_document', 'prd',
  'prototype', 'review_document', 'review_report',
  'handoff_document', 'development_handoff', 'delivery_summary',
]);

/** A missing tab layout must not turn internal state into user-visible artifacts. */
export function filterFallbackWorkflowSlots(
  workflowId: string, slots: SlotRevision[], ui: WorkflowUI,
): SlotRevision[] {
  const exposed = ui.exposed_slot_ids !== undefined ? new Set(ui.exposed_slot_ids) : undefined;
  const allowed = exposed ?? (
    workflowId === 'product_solution_delivery' || workflowId === 'product-solution-delivery'
      ? PRODUCT_FALLBACK_ARTIFACTS : undefined
  );
  return allowed ? slots.filter((slot) => allowed.has(slot.slot_id)) : slots;
}

/**
 * The catalog keeps reusable slot metadata at the workflow root while UI tabs
 * commonly reference a slot with only `{ id }`.  Hydrate those references so
 * renderers can see properties such as `type`, `cardinality`, and `ordered`.
 */
export function hydrateWorkflowUI(raw: unknown, fallbackName?: string): WorkflowUI {
  if (!raw || typeof raw !== 'object') return {};
  const spec = raw as Record<string, unknown>;
  const rawUI = spec.ui;
  const ui = rawUI && typeof rawUI === 'object' && !Array.isArray(rawUI) ? rawUI as WorkflowUI : {};
  const slotDefs = new Map<string, SlotDef>();
  if (Array.isArray(spec.slots)) {
    for (const value of spec.slots) {
      if (!value || typeof value !== 'object' || Array.isArray(value)) continue;
      const slot = value as SlotDef;
      if (typeof slot.id === 'string' && slot.id) slotDefs.set(slot.id, slot);
    }
  }

  const name = typeof spec.name === 'string' ? spec.name : fallbackName;
  const visibility = Array.isArray(spec.slots)
    ? { exposed_slot_ids: [...slotDefs.values()].filter((slot) => slot.exposed !== false).map((slot) => slot.id) }
    : {};
  const base = name === undefined && !Array.isArray(spec.slots) ? ui : { ...ui, ...visibility, ...(name === undefined ? {} : { name }) };
  if (!Array.isArray(ui.tabs)) {
    return base;
  }
  const hasWidgetConfigs = Boolean(ui.slots && Object.keys(ui.slots).length > 0);
  if (slotDefs.size === 0 && !hasWidgetConfigs) {
    return base;
  }
  return {
    ...base,
    tabs: ui.tabs.map((tab) => ({
      ...tab,
      slots: Array.isArray(tab.slots)
        ? tab.slots.map((slot) => {
          const widget = ui.slots?.[slot.id];
          return {
            ...slotDefs.get(slot.id),
            ...slot,
            ...(widget ? { widget } : {}),
          } as SlotDef;
        })
        : [],
    })),
  };
}

export interface SlotVersionEntry {
  revision: number;
  draft_version?: number;
  /** User-visible version number. Writer working drafts are excluded from this sequence. */
  version?: number;
  change_source: "ai" | "human" | "provider_sync";
  created_at: string;
  selected: boolean;
  /** Whether this historical Writer revision was provider-confirmed. */
  provider_synced?: boolean;
  content_snapshot?: any;
}

interface WorkflowStore {
  // Latest session per conversation (any status, not just active).
  sessionByConversation: Record<string, WorkflowSession | null>;
  loadingByConversation: Record<string, boolean>;
  // Whether auto-advance is running (driver agent triggered next chat turn).
  // Keyed by conversation_id. True = input should be disabled.
  autoRunningByConversation: Record<string, boolean>;
  // Workflow UI definition cache: keyed by workflow_id.
  workflowUIByWorkflow: Record<string, WorkflowUI>;
  // Incremented each time a session is dismissed, keyed by conversation_id.
  // DismissedWorkflowRestoreButton subscribes to this to re-fetch the dismissed list.
  dismissedRefreshTrigger: Record<string, number>;
  // Cached dismissed sessions per conversation. Survives component remounts.
  dismissedSessionsByConversation: Record<string, Array<{ session_id: string; workflow_id: string }>>;

  /** UI focus state keyed by conversation_id; held outside `sessionByConversation`
   *  so server refreshes don't overwrite the user's tab / sort_order focus. */
  focusedTabByConversation: Record<string, string | undefined>;
  focusedSortOrderByConversation: Record<string, number | undefined>;
  /** Canonical Event Stream projection shared by in-chat and standalone panels. */
  projectionBySession: Record<string, WorkflowProjectionState>;

  setSession: (conversationId: string, session: WorkflowSession | null) => void;
  updateSlot: (conversationId: string, slot: SlotRevision) => void;
  loadActiveSession: (
    conversationId: string,
    options?: { silentError?: boolean },
  ) => Promise<void>;
  refreshSlots: (conversationId: string, sessionId: string) => Promise<void>;
  patchSlot: (conversationId: string, sessionId: string, slotId: string, revision: number) => Promise<void>;
  syncSessionSearchConfig: (conversationId: string, sessionId: string, searchConfig: Record<string, unknown>) => Promise<void>;
  setAutoRunning: (conversationId: string, running: boolean) => void;
  fetchWorkflowUI: (workflowId: string) => Promise<WorkflowUI>;
  bumpDismissedRefresh: (conversationId: string) => void;
  fetchDismissedSessions: (conversationId: string) => Promise<void>;
  // Phase 3: slot item management.
  deleteSlotItem: (sessionId: string, slotId: string, listIndex: number, orderVersion?: number) => Promise<void>;
  patchSlotItemValue: (
    sessionId: string,
    slotId: string,
    listIndex: number,
    value: any,
    contentType?: string,
    mode?: 'draft' | 'checkpoint',
    baseRevision?: number,
    baseDraftVersion?: number,
  ) => Promise<number | undefined>;
  reorderSlotItems: (sessionId: string, slotId: string, newSortOrderSeq: number[], version: number) => Promise<void>;
  getSlotVersions: (sessionId: string, slotId: string, listIndex: number) => Promise<SlotVersionEntry[]>;
  rollbackSlotItem: (sessionId: string, slotId: string, listIndex: number, revision: number) => Promise<void>;
  createSlotItem: (sessionId: string, slotId: string, value: any, caption?: string, insertBefore?: number, contentType?: string) => Promise<void>;
  patchSlotCaption: (sessionId: string, slotId: string, listIndex: number, caption: string) => Promise<void>;
  // Track focused tab and sort_order for the AI. Held in sibling maps so the
  // value persists across `setSession()` refreshes that would otherwise wipe it.
  setFocusedTab: (conversationId: string, tabId: string) => void;
  setFocusedSortOrder: (conversationId: string, sortOrder: number | undefined) => void;
  applyWorkflowEvent: (conversationId: string, sessionId: string, event: WorkflowStreamEvent) => void;
  subscribeWorkflowSession: (conversationId: string, sessionId: string) => () => void;
}

const workflowStreams = new Map<string, { refs: number; subscription: WorkflowEventStreamSubscription }>();

export const useWorkflowStore = create<WorkflowStore>()((set, get) => ({
  sessionByConversation: {},
  loadingByConversation: {},
  autoRunningByConversation: {},
  workflowUIByWorkflow: {},
  dismissedRefreshTrigger: {},
  dismissedSessionsByConversation: {},
  focusedTabByConversation: {},
  focusedSortOrderByConversation: {},
  projectionBySession: {},

  bumpDismissedRefresh: (conversationId) => {
    set((s) => ({
      dismissedRefreshTrigger: {
        ...s.dismissedRefreshTrigger,
        [conversationId]: (s.dismissedRefreshTrigger[conversationId] ?? 0) + 1,
      },
    }));
  },

  fetchDismissedSessions: async (conversationId) => {
    try {
      const resp = await WorkflowSessionApi().listDismissedSessions(conversationId);
      const sessions = (resp.data?.data?.sessions ?? []) as Array<{ session_id: string; workflow_id: string }>;
      set((s) => ({
        dismissedSessionsByConversation: {
          ...s.dismissedSessionsByConversation,
          [conversationId]: sessions,
        },
      }));
    } catch {
      // silently ignore — stale cache is fine
    }
  },

  setSession: (conversationId, session) => {
    set((state) => {
      const previous = state.sessionByConversation[conversationId];
      if (session && previous?.session_id === session.session_id
        && (session.state_version ?? 0) < (previous.state_version ?? 0)) return state;
      const next: Partial<WorkflowStore> = {
        sessionByConversation: { ...state.sessionByConversation, [conversationId]: session },
      };
      // REST and SSE must advance the same cached projection. Otherwise the
      // next entity event can resurrect the graph from before the REST load.
      if (session?.projection && session.state_version !== undefined) {
        const cached = state.projectionBySession[session.session_id] ?? emptyWorkflowProjection();
        if (session.state_version >= cached.stateVersion) {
          next.projectionBySession = { ...state.projectionBySession, [session.session_id]: {
            ...cached, stateVersion: session.state_version,
            projection: { ...session.projection, status: session.status, current_step_id: session.current_step_id },
          } };
        }
      }
      if (session && session.status !== 'active') {
        if (state.autoRunningByConversation[conversationId]) {
          next.autoRunningByConversation = {
            ...state.autoRunningByConversation,
            [conversationId]: false,
          };
        }
      }
      return next;
    });
  },

  updateSlot: (conversationId, slot) => {
    set((state) => {
      const session = state.sessionByConversation[conversationId];
      if (!session) return state;
      const slots = session.slots ?? [];
      const idx = slots.findIndex(
        (s) => s.slot_id === slot.slot_id && (s.list_index ?? -1) === (slot.list_index ?? -1),
      );
      let nextSlots: SlotRevision[];
      if (idx >= 0) {
        nextSlots = slots.slice();
        nextSlots[idx] = slot;
      } else {
        nextSlots = [...slots, slot];
      }
      return {
        sessionByConversation: {
          ...state.sessionByConversation,
          [conversationId]: { ...session, slots: nextSlots },
        },
      };
    });
  },

  loadActiveSession: async (conversationId, options) => {
    if (!conversationId) return;
    const activeLoad = _activeSessionLoads.get(conversationId);
    if (activeLoad) {
      const queuedOptions = _queuedActiveSessionLoads.get(conversationId);
      _queuedActiveSessionLoads.set(conversationId, {
        silentError: queuedOptions
          ? Boolean(queuedOptions.silentError && options?.silentError)
          : options?.silentError,
      });
      await activeLoad;
      return;
    }

    const load = (async () => {
      set((s) => ({
        loadingByConversation: { ...s.loadingByConversation, [conversationId]: true },
      }));
      const startSession = get().sessionByConversation[conversationId];
      const startCursor = startSession ? get().projectionBySession[startSession.session_id]?.cursor ?? 0 : 0;
      try {
        const requestOptions = options?.silentError
          ? ({ silentError: true } as never)
          : undefined;
        const res = await WorkflowSessionApi().getLatestSession(
          conversationId,
          requestOptions,
        );
        const session: WorkflowSession | null = res?.data?.data?.session ?? null;
        // Runtime controls and rollback candidates come from Go's projection.
        // Steps are attempt history only; they never define Past/Ready locally.
        if (session?.session_id) {
          try {
            const projectionRes = await WorkflowSessionApi().getProjection(
              session.session_id, { silentError: true } as never,
            );
            const snapshot = projectionRes?.data?.data ?? {};
            session.state_version = snapshot.state_version;
            session.projection = { ...snapshot.projection, status: snapshot.status,
              current_step_id: snapshot.current_step_id, attempt_history: snapshot.attempt_history };
            session.steps = workflowSnapshotSteps(session.session_id, snapshot.attempt_history) ?? [];
            session.current_step_id = snapshot.current_step_id ?? session.current_step_id;
            session.status = reconcileWorkflowSessionStatus(snapshot.status ?? session.status, session.projection);
          } catch (error) {
            const cached = get().sessionByConversation[conversationId];
            session.steps = cached?.session_id === session.session_id ? cached.steps : [];
            session.projection = cached?.session_id === session.session_id ? cached.projection : {};
            if (cached?.session_id === session.session_id) session.status = cached.status;
            const errorCode = extractErrorCode(error);
            if (errorCode === "WORKFLOW_DEFINITION_CHANGED") {
              session.runtime_error_code = errorCode;
              session.runtime_error_message = getLocalizedErrorMessage(error);
            }
          }
        }
        const streamed = session ? get().projectionBySession[session.session_id] : undefined;
        if (!streamed || streamed.cursor <= startCursor || (session?.state_version ?? 0) > streamed.stateVersion) {
          get().setSession(conversationId, session);
        } else {
          _queuedActiveSessionLoads.set(conversationId, { silentError: true });
        }
        // Also refresh dismissed sessions so the restore button appears immediately on load.
        get().fetchDismissedSessions(conversationId);
      } catch {
        // ignore
      } finally {
        set((s) => ({
          loadingByConversation: { ...s.loadingByConversation, [conversationId]: false },
        }));
      }
    })();

    _activeSessionLoads.set(conversationId, load);
    try {
      await load;
    } finally {
      if (_activeSessionLoads.get(conversationId) === load) {
        _activeSessionLoads.delete(conversationId);
      }
      const queuedOptions = _queuedActiveSessionLoads.get(conversationId);
      if (queuedOptions) {
        _queuedActiveSessionLoads.delete(conversationId);
        await get().loadActiveSession(conversationId, queuedOptions);
      }
    }
  },

  refreshSlots: async (conversationId, sessionId) => {
    try {
      const res = await WorkflowSessionApi().getSlots(sessionId);
      const slots: SlotRevision[] = res?.data?.data?.slots ?? [];
      set((state) => {
        const session = state.sessionByConversation[conversationId];
        if (!session) return state;
        return {
          sessionByConversation: {
            ...state.sessionByConversation,
            [conversationId]: { ...session, slots },
          },
        };
      });
    } catch {
      // ignore
    }
  },

  patchSlot: async (conversationId, sessionId, slotId, revision) => {
    try {
      await WorkflowSessionApi().patchSlot(sessionId, slotId, revision);
      get().refreshSlots(conversationId, sessionId);
    } catch {
      // ignore
    }
  },

  syncSessionSearchConfig: async (_conversationId, sessionId, searchConfig) => {
    try {
      await WorkflowSessionApi().syncSessionSearchConfig(sessionId, searchConfig);
    } catch {
      // ignore
    }
  },

  setAutoRunning: (conversationId, running) => {
    set((state) => {
      const status = state.sessionByConversation[conversationId]?.status;
      const effective = running && !['completed', 'failed', 'stopped'].includes(status ?? '');
      return { autoRunningByConversation: { ...state.autoRunningByConversation, [conversationId]: effective } };
    });
  },

  fetchWorkflowUI: async (workflowId) => {
    const lang = i18n.language || "";
    const cacheKey = `${workflowId}:${lang}`;
    // Return cached value if already fetched for this language.
    const cached = get().workflowUIByWorkflow[cacheKey];
    if (cached) return cached;
    try {
      const res = await WorkflowInfoApi().getWorkflow(workflowId, {
        headers: lang ? { "Accept-Language": lang } : undefined,
      });
      const payload = res?.data?.data ?? res?.data ?? {};
      const ui = hydrateWorkflowUI(payload, workflowId);
      set((state) => ({
        workflowUIByWorkflow: { ...state.workflowUIByWorkflow, [cacheKey]: ui },
      }));
      return ui;
    } catch {
      return {};
    }
  },

  deleteSlotItem: async (sessionId, slotId, listIndex, orderVersion) => {
    await WorkflowSessionApi().deleteSlotItem(sessionId, slotId, listIndex, orderVersion);
  },

  patchSlotItemValue: async (
    sessionId, slotId, listIndex, value, contentType, mode, baseRevision, baseDraftVersion,
  ) => {
    const res = await WorkflowSessionApi().patchSlotItem(
      sessionId, slotId, listIndex, value, contentType, mode, baseRevision, baseDraftVersion,
    );
    const revision = res?.data?.data?.revision;
    const draftVersion = res?.data?.data?.draft_version;
    if (typeof revision === 'number' && typeof draftVersion === 'number') {
      set((state) => {
        let changed = false;
        const sessions = { ...state.sessionByConversation };
        Object.entries(sessions).forEach(([conversationId, session]) => {
          if (!session || session.session_id !== sessionId) return;
          let sessionChanged = false;
          const slots = (session.slots ?? []).map((slot) => {
            if (
              slot.slot_id !== slotId
              || (slot.list_index ?? -1) !== listIndex
            ) return slot;
            changed = true;
            sessionChanged = true;
            return { ...slot, revision, draft_version: draftVersion };
          });
          if (sessionChanged) sessions[conversationId] = { ...session, slots };
        });
        return changed ? { sessionByConversation: sessions } : state;
      });
    }
    return typeof revision === 'number' ? revision : undefined;
  },

  reorderSlotItems: async (sessionId, slotId, newSortOrderSeq, version) => {
    await WorkflowSessionApi().reorderSlotItems(sessionId, slotId, newSortOrderSeq, version);
  },

  getSlotVersions: async (sessionId, slotId, listIndex) => {
    const res = await WorkflowSessionApi().getSlotItemVersions(sessionId, slotId, listIndex);
    return res?.data?.data?.versions ?? [];
  },

  rollbackSlotItem: async (sessionId, slotId, listIndex, revision) => {
    await WorkflowSessionApi().rollbackSlotItem(sessionId, slotId, listIndex, revision);
  },

  createSlotItem: async (sessionId, slotId, value, caption, insertBefore, contentType) => {
    await WorkflowSessionApi().createSlotItem(sessionId, slotId, value, caption, insertBefore, contentType);
  },

  patchSlotCaption: async (sessionId, slotId, listIndex, caption) => {
    await WorkflowSessionApi().patchSlotCaption(sessionId, slotId, listIndex, caption);
  },

  setFocusedTab: (conversationId, tabId) => {
    set((state) => {
      // Write to the sibling map; mirror onto the session as a fallback so
      // legacy readers (chatLayout request assembly) still see the value.
      const nextFocusedMap = {
        ...state.focusedTabByConversation,
        [conversationId]: tabId,
      };
      const session = state.sessionByConversation[conversationId];
      const nextSessionMap = session
        ? {
            ...state.sessionByConversation,
            [conversationId]: { ...session, focusedTab: tabId },
          }
        : state.sessionByConversation;
      return {
        focusedTabByConversation: nextFocusedMap,
        sessionByConversation: nextSessionMap,
      };
    });
  },

  setFocusedSortOrder: (conversationId, sortOrder) => {
    set((state) => {
      const nextFocusedMap = {
        ...state.focusedSortOrderByConversation,
        [conversationId]: sortOrder,
      };
      const session = state.sessionByConversation[conversationId];
      const nextSessionMap = session
        ? {
            ...state.sessionByConversation,
            [conversationId]: { ...session, focusedSortOrder: sortOrder },
          }
        : state.sessionByConversation;
      return {
        focusedSortOrderByConversation: nextFocusedMap,
        sessionByConversation: nextSessionMap,
      };
    });
  },

  applyWorkflowEvent: (conversationId, sessionId, event) => {
    set((state) => {
      const previous = state.projectionBySession[sessionId] ?? emptyWorkflowProjection();
      const projectionState = reduceWorkflowEvent(previous, event);
      const session = state.sessionByConversation[conversationId];
      if (!session || session.session_id !== sessionId) {
        return { projectionBySession: { ...state.projectionBySession, [sessionId]: projectionState } };
      }
      const projection = projectionState.projection as WorkflowRuntimeProjection & { status?: string };
      if (projectionState === previous || projectionState.resyncRequired
        || projectionState.stateVersion < (session.state_version ?? 0)) {
        return { projectionBySession: { ...state.projectionBySession, [sessionId]: projectionState } };
      }
      const reconciledStatus = reconcileWorkflowSessionStatus(session.status, projection);
      const steps = workflowSnapshotSteps(sessionId, projection.attempt_history) ?? session.steps;
      return {
        projectionBySession: { ...state.projectionBySession, [sessionId]: projectionState },
        ...(['completed', 'failed', 'stopped'].includes(reconciledStatus) ? {
          autoRunningByConversation: { ...state.autoRunningByConversation, [conversationId]: false },
        } : {}),
        sessionByConversation: {
          ...state.sessionByConversation,
          [conversationId]: { ...session, status: reconciledStatus, projection, steps,
            state_version: projectionState.stateVersion,
            current_step_id: projection.current_step_id ?? session.current_step_id },
        },
      };
    });
    const projectionState = get().projectionBySession[sessionId];
    if (projectionState?.resyncRequired) {
      // Closing and reconnecting without Last-Event-ID asks the server for a fresh snapshot.
      workflowStreams.get(sessionId)?.subscription.resync();
    }
    if (event.type === 'attempt.patch' || event.type === 'step.patch' || event.type === 'workflow.patch') {
      void get().loadActiveSession(conversationId, { silentError: true });
    }
    if (event.type === 'artifact.upsert') {
      void get().refreshSlots(conversationId, sessionId);
    }
  },

  subscribeWorkflowSession: (conversationId, sessionId) => {
    const existing = workflowStreams.get(sessionId);
    if (existing) {
      existing.refs += 1;
    } else {
      const current = get().projectionBySession[sessionId] ?? emptyWorkflowProjection();
      const subscription = subscribeWorkflowEventStream(
        sessionId,
        current.resyncRequired ? 0 : current.cursor,
        (event) => get().applyWorkflowEvent(conversationId, sessionId, event),
        () => set((state) => ({
          projectionBySession: {
            ...state.projectionBySession,
            [sessionId]: markWorkflowResyncRequired(state.projectionBySession[sessionId] ?? emptyWorkflowProjection()),
          },
        })),
      );
      workflowStreams.set(sessionId, { refs: 1, subscription });
    }
    return () => {
      const current = workflowStreams.get(sessionId);
      if (!current) return;
      current.refs -= 1;
      if (current.refs <= 0) {
        current.subscription.close();
        workflowStreams.delete(sessionId);
      }
    };
  },
}));
