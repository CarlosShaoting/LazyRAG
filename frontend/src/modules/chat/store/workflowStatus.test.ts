import { describe, expect, it } from 'vitest';
import { reconcileWorkflowSessionStatus } from './workflowStatus';

describe('reconcileWorkflowSessionStatus', () => {
  it('changes a stale active session to waiting when the next step is ready', () => {
    expect(reconcileWorkflowSessionStatus('active', {
      current: [],
      ready: ['typed-artifact'],
      blocked: [],
    })).toBe('waiting');
  });

  it('keeps a session active while an attempt is current', () => {
    expect(reconcileWorkflowSessionStatus('active', {
      current: ['script-tool'],
      ready: [],
      blocked: [],
    })).toBe('active');
  });

  it('uses a completed projection when the persisted status is stale', () => {
    expect(reconcileWorkflowSessionStatus('active', {
      completed: true,
      current: [],
      ready: [],
      blocked: [],
    })).toBe('completed');
  });
});
