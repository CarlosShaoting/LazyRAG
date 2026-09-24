import type {
  TabDef,
  WorkflowSession,
  WorkflowSessionStep,
  WorkflowUI,
} from '@/modules/chat/store/workflowPanel';

export type WorkflowFollowMode = 'following' | 'free';

const ACTIVE_EXECUTION_STATES = new Set([
  'pending',
  'queued',
  'claimed',
  'running',
  'waiting',
]);

function tabMatchesStep(tab: TabDef, stepId: string): boolean {
  return tab.step_id === stepId
    || (!tab.step_id && tab.id === stepId)
    || Boolean(tab.status_step_ids?.includes(stepId));
}

function findTabIndex(tabs: TabDef[], stepId?: string): number {
  if (!stepId) return -1;
  return tabs.findIndex((tab) => tabMatchesStep(tab, stepId));
}

function latestEffectiveStep(
  steps: WorkflowSessionStep[] = [],
  predicate: (step: WorkflowSessionStep) => boolean = () => true,
): WorkflowSessionStep | undefined {
  return [...steps]
    .filter((step) => step.validity !== 'stale' && predicate(step))
    .sort((left, right) => {
      const updatedDelta = Date.parse(right.updated_at) - Date.parse(left.updated_at);
      const createdDelta = Date.parse(right.created_at) - Date.parse(left.created_at);
      return updatedDelta || createdDelta || right.attempt - left.attempt;
    })[0];
}

export function parsePersistedFollowMode(stored: string | null): WorkflowFollowMode | null {
  return stored === 'following' || stored === 'free' ? stored : null;
}

export function resolveInitialFollowMode(
  persistedMode: WorkflowFollowMode | null,
  defaultMode?: NonNullable<WorkflowUI['follow_mode']>['default'],
): WorkflowFollowMode {
  if (persistedMode) return persistedMode;
  return defaultMode === 'following' ? 'following' : 'free';
}

/** Keep the viewed tab stable by identity when conditional tabs are inserted or removed. */
export function resolveWorkflowActiveTabIndex(
  tabs: TabDef[],
  activeTabId?: string,
): number {
  if (!tabs.length) return 0;
  const index = activeTabId
    ? tabs.findIndex((tab) => tab.id === activeTabId)
    : -1;
  return index === -1 ? 0 : index;
}

/** The runtime "current" marker already owns the tab's single status dot. */
export function shouldShowStandaloneStepStatus(
  stepStatus: WorkflowSessionStep['status'] | undefined,
  runtimeMarkerVisible: boolean,
): boolean {
  return Boolean(stepStatus && stepStatus !== 'succeeded' && !runtimeMarkerVisible);
}

/**
 * Resolve the visible tab that represents the runtime fact, independently of
 * the tab the user is currently viewing.
 */
export function resolveWorkflowRealTabIndex(
  session: Pick<WorkflowSession, 'status' | 'current_step_id' | 'steps' | 'projection'>,
  tabs: TabDef[],
): number {
  const projection = session.projection;

  // 1. Prefer an authoritative, effective node that is actively executing.
  for (const stepId of projection?.current ?? []) {
    const node = projection?.nodes?.[stepId];
    if (node?.validity !== 'stale' && ACTIVE_EXECUTION_STATES.has(node?.execution ?? '')) {
      const index = findTabIndex(tabs, stepId);
      if (index !== -1) return index;
    }
  }

  // 2. A failed attempt is still the runtime current step. Prefer this
  // authoritative fact even when the session-level status has already fallen
  // back to waiting or a legacy current-step pointer still names its predecessor.
  const failedCurrentStepId = (projection?.current ?? []).find((stepId) => (
    projection?.nodes?.[stepId]?.validity !== 'stale'
    && projection?.nodes?.[stepId]?.execution === 'failed'
  ));
  const failedCurrentIndex = findTabIndex(tabs, failedCurrentStepId);
  if (failedCurrentIndex !== -1) return failedCurrentIndex;

  // 3. Older sessions expose only the mutable current-step pointer.
  const currentStepIndex = findTabIndex(tabs, session.current_step_id);
  if (currentStepIndex !== -1) return currentStepIndex;

  // 4. Waiting approval can clear current_step_id after the attempt succeeds.
  if (session.status === 'waiting') {
    const approvalStep = latestEffectiveStep(session.steps, (step) => (
      step.status === 'succeeded'
      && Boolean(projection?.nodes?.[step.step_id]?.requires_approval)
    ));
    const approvalIndex = findTabIndex(tabs, approvalStep?.step_id);
    if (approvalIndex !== -1) return approvalIndex;
  }

  // 5. Legacy failed sessions may not expose projection.current.
  if (session.status === 'failed') {
    const failedStepId = latestEffectiveStep(
      session.steps,
      (step) => step.status === 'failed',
    )?.step_id;
    const failedIndex = findTabIndex(tabs, failedStepId);
    if (failedIndex !== -1) return failedIndex;
  }

  // 6. Terminal sessions stay on the last step that actually ran.
  if (session.status === 'completed' || session.status === 'stopped') {
    const lastExecuted = latestEffectiveStep(session.steps);
    const lastExecutedIndex = findTabIndex(tabs, lastExecuted?.step_id);
    if (lastExecutedIndex !== -1) return lastExecutedIndex;
  }

  return -1;
}
