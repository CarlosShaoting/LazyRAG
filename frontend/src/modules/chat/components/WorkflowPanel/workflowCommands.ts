export type WorkflowCommandAction = 'continue' | 'retry' | 'rollback';

/**
 * Structural subset of the runtime projection used by the command buttons.
 * Keeping this type local avoids coupling command resolution to the panel store.
 */
export interface WorkflowCommandProjection {
  ready?: readonly string[];
  continue?: readonly string[];
  retryable?: readonly string[];
  rewindable?: readonly string[];
  current?: readonly string[];
  nodes?: Record<string, { execution?: string }>;
}

export interface ResolveWorkflowCommandTargetOptions {
  completedContinueStepId?: string;
  currentStepId?: string;
  rollbackStepId?: string;
}

export type WorkflowCommandTargetErrorCode =
  | 'WORKFLOW_COMMAND_TARGET_MISSING'
  | 'WORKFLOW_COMMAND_TARGET_AMBIGUOUS'
  | 'WORKFLOW_COMMAND_TARGET_NOT_ALLOWED';

/** A stable, UI-safe error that callers can map to localized copy. */
export class WorkflowCommandTargetError extends Error {
  readonly name = 'WorkflowCommandTargetError';

  constructor(
    readonly code: WorkflowCommandTargetErrorCode,
    readonly action: WorkflowCommandAction,
    message: string,
    readonly candidates: readonly string[] = [],
  ) {
    super(message);
  }
}

function normalizedStepId(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function uniqueStepIds(values: readonly string[] | undefined): string[] {
  const stepIds = new Set<string>();
  for (const value of values ?? []) {
    const stepId = normalizedStepId(value);
    if (stepId) stepIds.add(stepId);
  }
  return [...stepIds];
}

const LIVE_EXECUTIONS = new Set([
  'pending', 'queued', 'claimed', 'running', 'waiting',
]);

/**
 * Return the sole server-authorized start target for a prepared session.
 *
 * A newly created session may still be persisted as `active` even though no
 * attempt is running yet. The projection, rather than that coarse status, is
 * authoritative: dispatch only when no node has a live execution and Ready
 * contains exactly one step. Continue is deliberately not used as a fallback,
 * because it describes completed-step hand-off rather than an unstarted node.
 */
export function resolveUniqueWorkflowStartTarget(
  projection: WorkflowCommandProjection,
): string | undefined {
  const hasLiveExecution = Object.values(projection.nodes ?? {}).some((node) => (
    LIVE_EXECUTIONS.has(normalizedStepId(node?.execution).toLowerCase())
  ));
  if (hasLiveExecution) return undefined;

  const ready = uniqueStepIds(projection.ready);
  return ready.length === 1 ? ready[0] : undefined;
}

function requireUniqueTarget(
  action: WorkflowCommandAction,
  candidates: readonly string[],
): string {
  if (candidates.length === 1) return candidates[0];
  if (candidates.length === 0) {
    throw new WorkflowCommandTargetError(
      'WORKFLOW_COMMAND_TARGET_MISSING',
      action,
      `No server-authorized target is available for ${action}.`,
    );
  }
  throw new WorkflowCommandTargetError(
    'WORKFLOW_COMMAND_TARGET_AMBIGUOUS',
    action,
    `More than one server-authorized target is available for ${action}.`,
    candidates,
  );
}

/**
 * Resolve exactly one target from a fresh, server-authoritative projection.
 * No local step history or inferred graph state is accepted as a fallback.
 */
export function resolveWorkflowCommandTarget(
  action: WorkflowCommandAction,
  projection: WorkflowCommandProjection,
  options: ResolveWorkflowCommandTargetOptions = {},
): string {
  if (action === 'continue') {
    const declaredTarget = normalizedStepId(options.completedContinueStepId);
    if (declaredTarget) {
      const allowedTargets = uniqueStepIds(projection.continue);
      if (allowedTargets.includes(declaredTarget)) return declaredTarget;
      throw new WorkflowCommandTargetError(
        'WORKFLOW_COMMAND_TARGET_NOT_ALLOWED',
        action,
        `The declared continue target "${declaredTarget}" is not allowed by the latest projection.`,
        allowedTargets,
      );
    }
    return requireUniqueTarget(action, uniqueStepIds(projection.ready));
  }

  if (action === 'retry') {
    const retryableTargets = uniqueStepIds(projection.retryable);
    const currentStepId = normalizedStepId(options.currentStepId);
    if (currentStepId && retryableTargets.includes(currentStepId)) {
      return currentStepId;
    }
    return requireUniqueTarget(action, retryableTargets);
  }

  const rollbackStepId = normalizedStepId(options.rollbackStepId);
  if (!rollbackStepId) {
    throw new WorkflowCommandTargetError(
      'WORKFLOW_COMMAND_TARGET_MISSING',
      action,
      'A rollback target is required.',
    );
  }
  const rewindableTargets = uniqueStepIds(projection.rewindable);
  if (rewindableTargets.includes(rollbackStepId)) return rollbackStepId;
  throw new WorkflowCommandTargetError(
    'WORKFLOW_COMMAND_TARGET_NOT_ALLOWED',
    action,
    `The rollback target "${rollbackStepId}" is not allowed by the latest projection.`,
    rewindableTargets,
  );
}
