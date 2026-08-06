export type WorkflowSessionStatus = 'active' | 'completed' | 'failed' | 'waiting';

interface RuntimeProjectionStatus {
  completed?: boolean;
  current?: string[];
  ready?: string[];
  blocked?: string[];
}

/**
 * Reconcile the persisted session status with the runtime projection.
 *
 * The projection is computed from attempts and graph reachability, so it can
 * already be quiescent while a delayed session-status write still says active.
 * In that case the UI must allow the user to continue instead of presenting a
 * permanently busy workflow.
 */
export function reconcileWorkflowSessionStatus(
  status: WorkflowSessionStatus,
  projection?: RuntimeProjectionStatus,
): WorkflowSessionStatus {
  if (!projection) return status;
  if (projection.completed) return 'completed';
  if (
    status === 'active'
    && (projection.current?.length ?? 0) === 0
    && ((projection.ready?.length ?? 0) > 0 || (projection.blocked?.length ?? 0) > 0)
  ) {
    return 'waiting';
  }
  return status;
}
