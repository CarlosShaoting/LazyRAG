import { describe, expect, it } from 'vitest';

import {
  resolveWorkflowCommandTarget,
  resolveUniqueWorkflowStartTarget,
  WorkflowCommandTargetError,
} from './workflowCommands';

function expectTargetError(
  run: () => unknown,
  code: WorkflowCommandTargetError['code'],
): WorkflowCommandTargetError {
  try {
    run();
  } catch (error) {
    expect(error).toBeInstanceOf(WorkflowCommandTargetError);
    expect((error as WorkflowCommandTargetError).code).toBe(code);
    return error as WorkflowCommandTargetError;
  }
  throw new Error('Expected command target resolution to fail');
}

describe('resolveWorkflowCommandTarget', () => {
  it('uses the declared completed continue target only when projection.continue allows it', () => {
    expect(resolveWorkflowCommandTarget(
      'continue',
      { continue: ['publish'], ready: ['draft'] },
      { completedContinueStepId: 'publish' },
    )).toBe('publish');

    expectTargetError(
      () => resolveWorkflowCommandTarget(
        'continue',
        { continue: ['review'], ready: ['publish'] },
        { completedContinueStepId: 'publish' },
      ),
      'WORKFLOW_COMMAND_TARGET_NOT_ALLOWED',
    );
  });

  it('falls back to the sole ready target when no completed continue target is declared', () => {
    expect(resolveWorkflowCommandTarget('continue', { ready: ['draft'] })).toBe('draft');
  });

  it('fails closed when continue has no target or multiple ready targets', () => {
    expectTargetError(
      () => resolveWorkflowCommandTarget('continue', { ready: [] }),
      'WORKFLOW_COMMAND_TARGET_MISSING',
    );
    const error = expectTargetError(
      () => resolveWorkflowCommandTarget('continue', { ready: ['draft', 'review'] }),
      'WORKFLOW_COMMAND_TARGET_AMBIGUOUS',
    );
    expect(error.candidates).toEqual(['draft', 'review']);
  });

  it('prefers the current step when it is retryable', () => {
    expect(resolveWorkflowCommandTarget(
      'retry',
      { retryable: ['collect', 'draft'] },
      { currentStepId: 'draft' },
    )).toBe('draft');
  });

  it('uses the sole retryable target when current step is not retryable', () => {
    expect(resolveWorkflowCommandTarget(
      'retry',
      { retryable: ['collect'] },
      { currentStepId: 'draft' },
    )).toBe('collect');
  });

  it('fails closed when retry remains ambiguous', () => {
    expectTargetError(
      () => resolveWorkflowCommandTarget(
        'retry',
        { retryable: ['collect', 'draft'] },
        { currentStepId: 'review' },
      ),
      'WORKFLOW_COMMAND_TARGET_AMBIGUOUS',
    );
  });

  it('accepts rollback only for the explicitly selected rewindable target', () => {
    expect(resolveWorkflowCommandTarget(
      'rollback',
      { rewindable: ['outline', 'draft'] },
      { rollbackStepId: 'outline' },
    )).toBe('outline');

    expectTargetError(
      () => resolveWorkflowCommandTarget(
        'rollback',
        { rewindable: ['outline'] },
        { rollbackStepId: 'publish' },
      ),
      'WORKFLOW_COMMAND_TARGET_NOT_ALLOWED',
    );
    expectTargetError(
      () => resolveWorkflowCommandTarget('rollback', { rewindable: ['outline'] }),
      'WORKFLOW_COMMAND_TARGET_MISSING',
    );
  });

  it('normalizes whitespace and duplicate projection entries without inventing targets', () => {
    expect(resolveWorkflowCommandTarget('continue', { ready: [' draft ', 'draft', ''] })).toBe('draft');
  });
});

describe('resolveUniqueWorkflowStartTarget', () => {
  it('returns the sole ready target when no node execution is live', () => {
    expect(resolveUniqueWorkflowStartTarget({
      ready: [' route_product_stage ', 'route_product_stage'],
      nodes: {
        route_product_stage: { execution: 'none' },
        earlier_stage: { execution: 'succeeded' },
      },
    })).toBe('route_product_stage');
  });

  it.each(['pending', 'queued', 'claimed', 'running', 'waiting'])(
    'does not dispatch when any node execution is %s',
    (execution) => {
      expect(resolveUniqueWorkflowStartTarget({
        ready: ['route_product_stage'],
        nodes: {
          route_product_stage: { execution: 'none' },
          active_attempt: { execution },
        },
      })).toBeUndefined();
    },
  );

  it('fails closed for zero or multiple ready targets', () => {
    expect(resolveUniqueWorkflowStartTarget({ ready: [] })).toBeUndefined();
    expect(resolveUniqueWorkflowStartTarget({ ready: ['direction', 'prd'] })).toBeUndefined();
  });

  it('does not infer a start target from continue-only state', () => {
    expect(resolveUniqueWorkflowStartTarget({
      ready: [],
      continue: ['completed_stage'],
      nodes: { completed_stage: { execution: 'succeeded' } },
    })).toBeUndefined();
  });
});
