import { describe, expect, it } from 'vitest';

import type { TabDef, WorkflowSession } from '@/modules/chat/store/workflowPanel';
import {
  parsePersistedFollowMode,
  resolveInitialFollowMode,
  resolveWorkflowActiveTabIndex,
  resolveWorkflowRealTabIndex,
  shouldShowStandaloneStepStatus,
} from './workflowFollowMode';

const tabs: TabDef[] = [
  { id: 'analysis', step_id: 'analyze', label: '分析', slots: [] },
  {
    id: 'materials',
    step_id: 'collect',
    status_step_ids: ['collect', 'search'],
    label: '素材',
    slots: [],
  },
  { id: 'delivery', step_id: 'generate', label: '生成', slots: [] },
];

function session(overrides: Partial<WorkflowSession>): WorkflowSession {
  return {
    session_id: 'session-1',
    conversation_id: 'conversation-1',
    workflow_id: 'ppt-workflow',
    workflow_mode: 'dynamic',
    status: 'active',
    current_step_id: '',
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    ...overrides,
  };
}

describe('workflow follow preference', () => {
  it('uses a persisted choice before the workflow default', () => {
    expect(resolveInitialFollowMode(null, 'following')).toBe('following');
    expect(resolveInitialFollowMode('free', 'following')).toBe('free');
    expect(resolveInitialFollowMode(null, undefined)).toBe('free');
  });

  it('ignores invalid persisted values', () => {
    expect(parsePersistedFollowMode('following')).toBe('following');
    expect(parsePersistedFollowMode('free')).toBe('free');
    expect(parsePersistedFollowMode('invalid')).toBeNull();
  });

  it('keeps free-browse focus on the same tab when a conditional tab is inserted', () => {
    const before = [tabs[0], tabs[2]];
    expect(resolveWorkflowActiveTabIndex(before, 'delivery')).toBe(1);
    expect(resolveWorkflowActiveTabIndex(tabs, 'delivery')).toBe(2);
  });

  it('does not render a second status dot beside the runtime current marker', () => {
    expect(shouldShowStandaloneStepStatus('running', true)).toBe(false);
    expect(shouldShowStandaloneStepStatus('running', false)).toBe(true);
    expect(shouldShowStandaloneStepStatus('succeeded', false)).toBe(false);
  });
});
describe('resolveWorkflowRealTabIndex', () => {
  it('uses an effective running projection node and status_step_ids mapping', () => {
    expect(resolveWorkflowRealTabIndex(session({
      projection: {
        current: ['search'],
        nodes: {
          search: {
            requires_approval: false,
            execution: 'running',
            validity: 'effective',
            reachability: 'reachable',
            readiness: 'not_applicable',
            branch: 'active',
          },
        },
      },
    }), tabs)).toBe(1);
  });

  it('falls back to current_step_id for an older session', () => {
    expect(resolveWorkflowRealTabIndex(session({ current_step_id: 'generate' }), tabs)).toBe(2);
  });

  it('keeps a failed session on its actual failed step', () => {
    expect(resolveWorkflowRealTabIndex(session({
      status: 'failed',
      projection: {
        current: ['collect'],
        nodes: {
          collect: {
            requires_approval: false,
            execution: 'failed',
            validity: 'effective',
            reachability: 'unreachable',
            readiness: 'not_applicable',
            branch: 'active',
          },
        },
      },
    }), tabs)).toBe(1);
  });

  it('keeps an effective failed step current when session status and legacy pointer fell back', () => {
    expect(resolveWorkflowRealTabIndex(session({
      status: 'waiting',
      current_step_id: 'analyze',
      projection: {
        current: ['generate'],
        nodes: {
          generate: {
            requires_approval: false,
            execution: 'failed',
            validity: 'effective',
            reachability: 'unreachable',
            readiness: 'not_applicable',
            branch: 'active',
          },
          collect: {
            requires_approval: true,
            execution: 'succeeded',
            validity: 'effective',
            reachability: 'unreachable',
            readiness: 'not_applicable',
            branch: 'active',
          },
        },
      },
      steps: [{
        id: 'step-approval', session_id: 'session-1', step_id: 'collect', attempt: 1,
        task_id: 'task-approval', status: 'succeeded', validity: 'effective',
        created_at: '2026-09-10T00:02:00Z', updated_at: '2026-09-10T00:03:00Z',
      }],
    }), tabs)).toBe(2);
  });

  it('uses the latest succeeded approval node while waiting', () => {
    expect(resolveWorkflowRealTabIndex(session({
      status: 'waiting',
      projection: {
        nodes: {
          collect: {
            requires_approval: true,
            execution: 'succeeded',
            validity: 'effective',
            reachability: 'unreachable',
            readiness: 'not_applicable',
            branch: 'active',
          },
        },
      },
      steps: [{
        id: 'step-approval', session_id: 'session-1', step_id: 'collect', attempt: 1,
        task_id: 'task-approval', status: 'succeeded', validity: 'effective',
        created_at: '2026-09-10T00:02:00Z', updated_at: '2026-09-10T00:03:00Z',
      }],
    }), tabs)).toBe(1);
  });

  it('uses the latest actually executed step when a session completes', () => {
    expect(resolveWorkflowRealTabIndex(session({
      status: 'completed',
      steps: [
        {
          id: 'step-1', session_id: 'session-1', step_id: 'analyze', attempt: 1,
          task_id: 'task-1', status: 'succeeded', validity: 'effective',
          created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-10T00:01:00Z',
        },
        {
          id: 'step-2', session_id: 'session-1', step_id: 'collect', attempt: 1,
          task_id: 'task-2', status: 'succeeded', validity: 'effective',
          created_at: '2026-09-10T00:02:00Z', updated_at: '2026-09-10T00:03:00Z',
        },
      ],
    }), tabs)).toBe(1);
  });

  it('uses the latest actually executed step when a session stops', () => {
    expect(resolveWorkflowRealTabIndex(session({
      status: 'stopped',
      steps: [{
        id: 'step-stopped', session_id: 'session-1', step_id: 'generate', attempt: 1,
        task_id: 'task-stopped', status: 'cancelled', validity: 'effective',
        created_at: '2026-09-10T00:02:00Z', updated_at: '2026-09-10T00:03:00Z',
      }],
    }), tabs)).toBe(2);
  });
});
