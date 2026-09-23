import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { WorkflowSession } from '@/modules/chat/store/workflowPanel';
import { WorkflowPanel } from './index';

const mocks = vi.hoisted(() => ({
  currentSession: null as WorkflowSession | null,
  fetchWorkflowUI: vi.fn(),
  getProjection: vi.fn(),
  getProductStageRelay: vi.fn(),
  getSession: vi.fn(),
  restartOnLatest: vi.fn(),
  advanceStepAndHandOff: vi.fn(),
  setSession: vi.fn(),
  setAutoRunning: vi.fn(),
  loadActiveSession: vi.fn(),
  loadConversationTasks: vi.fn(),
  refresh: vi.fn(),
  uuidv4: vi.fn(),
}));

vi.mock('uuid', () => ({ v4: mocks.uuidv4 }));

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'zh-CN', resolvedLanguage: 'zh-CN' },
    t: (key: string) => key,
  }),
}));

vi.mock('antd', () => ({
  Dropdown: ({ children }: { children: React.ReactNode }) => children,
  message: { error: vi.fn() },
  Popconfirm: ({ children }: { children: React.ReactNode }) => children,
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@ant-design/icons', () => ({
  CheckCircleFilled: () => null,
  CloudUploadOutlined: () => null,
  DownOutlined: () => null,
  DownloadOutlined: () => null,
  ExclamationCircleFilled: () => null,
  ExportOutlined: () => null,
  FileTextOutlined: () => null,
  FullscreenOutlined: () => null,
  FullscreenExitOutlined: () => null,
  InfoCircleOutlined: () => null,
  MoreOutlined: () => null,
}));

vi.mock('@/components/StateGraphModal', () => ({ default: () => null }));

vi.mock('@/components/request', () => ({
  BASE_URL: '',
  getLocalizedErrorMessage: (cause: unknown) => cause instanceof Error ? cause.message : String(cause),
  localizeErrorCode: (code: string) => code,
}));

vi.mock('@/modules/chat/hooks/useWorkflow', () => ({
  useWorkflowSession: () => ({
    session: mocks.currentSession,
    loading: false,
    refresh: mocks.refresh,
  }),
}));

vi.mock('@/modules/chat/store/workflowPanel', () => {
  const state = {
    autoRunningByConversation: {} as Record<string, boolean>,
    workflowUIByWorkflow: {} as Record<string, unknown>,
    focusedTabByConversation: {} as Record<string, string>,
    bumpDismissedRefresh: vi.fn(),
    setAutoRunning: mocks.setAutoRunning,
    fetchWorkflowUI: mocks.fetchWorkflowUI,
    setFocusedTab: vi.fn(),
    setFocusedSortOrder: vi.fn(),
    createSlotItem: vi.fn(),
    loadActiveSession: mocks.loadActiveSession,
    setSession: mocks.setSession,
    sessionByConversation: {} as Record<string, unknown>,
  };
  const useWorkflowStore = Object.assign(
    (selector?: (value: typeof state) => unknown) => selector ? selector(state) : state,
    { getState: () => state },
  );
  return {
    buildChineseDesignRoutingSummary: () => '',
    filterWorkflowTabs: (tabs: unknown[]) => tabs,
    filterFallbackWorkflowSlots: (_workflowId: string, slots: unknown[]) => slots,
    filterWorkflowSlotIdsByConditions: (slotIds: string[]) => slotIds,
    workflowTabAllowsDownload: () => false,
    useWorkflowStore,
  };
});

vi.mock('@/modules/chat/store/taskCenter', () => {
  const state = {
    tasksByConversation: {} as Record<string, unknown[]>,
    loadConversationTasks: mocks.loadConversationTasks,
  };
  return {
    useTaskCenterStore: Object.assign(
      (selector?: (value: typeof state) => unknown) => selector ? selector(state) : state,
      { getState: () => state },
    ),
  };
});

vi.mock('@/modules/chat/utils/request', () => ({
  WORKFLOW_CONTRACT_VERSION: 'workflow.v1',
  WorkflowSessionApi: () => ({
    getProjection: mocks.getProjection,
    getProductStageRelay: mocks.getProductStageRelay,
    getSession: mocks.getSession,
    restartOnLatest: mocks.restartOnLatest,
    advanceStepAndHandOff: mocks.advanceStepAndHandOff,
  }),
}));

vi.mock('@/modules/chat/utils/chunkUpload', () => ({ uploadFileInChunks: vi.fn() }));

vi.mock('./ProductProjectViews', () => ({
  ProductCurrentStageView: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ProductProjectViews: () => null,
  productWorkflowSectionKeys: (sessionId: string) => ({
    projectViews: `${sessionId}:views`,
    currentStage: `${sessionId}:current`,
    stageRelay: `${sessionId}:relay`,
  }),
}));

vi.mock('./ProductStageRelay', () => ({
  isProductWorkflow: (workflowId: string) => (
    workflowId === 'product_solution_delivery' || workflowId === 'product-solution-delivery'
  ),
  ProductStageRelay: () => null,
}));

vi.mock('./SlotComponents', async () => {
  const { createContext } = await import('react');
  return {
    isWriterIrSource: () => false,
    SlotDownloadContext: createContext(true),
    SlotMarkdownStream: () => null,
    SlotRenderer: () => null,
  };
});

vi.mock('./ppt/SlideThumb', () => ({ SlideThumb: () => null }));
vi.mock('./actions/WorkflowTabActions', () => ({ WorkflowTabActions: () => null }));
vi.mock('./writerArtifactStream', () => ({ findWriterArtifactStream: () => undefined }));

const failedProductSession: WorkflowSession = {
  session_id: 'product-session-old',
  conversation_id: 'conversation-1',
  workflow_id: 'product_solution_delivery',
  status: 'failed',
  current_step_id: 'write_product_solution_document',
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-10T00:00:01Z',
  slots: [],
  steps: [],
  projection: {
    current: ['write_product_solution_document'],
    ready: [],
    retryable: ['write_product_solution_document'],
    continue: [],
    nodes: {
      write_product_solution_document: {
        requires_approval: false,
        execution: 'failed',
        validity: 'effective',
        reachability: 'unreachable',
        readiness: 'not_applicable',
        branch: 'active',
      },
    },
  },
};

function projectionResponse(
  sessionId: string,
  stateVersion: number,
  projection: WorkflowSession['projection'],
) {
  return Promise.resolve({ data: { data: {
    session_id: sessionId,
    state_version: stateVersion,
    graph_hash: 'graph-hash',
    schema_version: 'workflow.v1',
    projection,
  } } });
}

function relayResponse(canRestartOnLatest: boolean) {
  return Promise.resolve({ data: { result: {
    supported: true,
    can_relay: false,
    can_restart_on_latest: canRestartOnLatest,
    update_available: canRestartOnLatest,
    session_id: failedProductSession.session_id,
    state_version: 7,
    current_stage: 'design',
    run_status: 'failed',
    next_stages: [],
    actions: [],
    artifacts: [],
  } } });
}

function successorProjection(execution = 'none'): WorkflowSession['projection'] {
  return {
    current: ['route_product_stage'],
    ready: ['route_product_stage'],
    retryable: [],
    continue: [],
    nodes: {
      route_product_stage: {
        requires_approval: false,
        execution,
        validity: 'effective',
        reachability: 'reachable',
        readiness: 'ready',
        branch: 'active',
      },
    },
  };
}

function successorSession(): WorkflowSession {
  return {
    ...failedProductSession,
    session_id: 'product-session-new',
    status: 'active',
    current_step_id: 'route_product_stage',
    updated_at: '2026-09-10T00:00:02Z',
    projection: successorProjection(),
  };
}

function restartAccepted() {
  return Promise.resolve({ data: { result: {
    source_session_id: failedProductSession.session_id,
    session_id: 'product-session-new',
    restarted: true,
    status: 'active',
    state_version: 1,
    ready_steps: ['route_product_stage'],
  } } });
}

function commandAccepted() {
  return Promise.resolve({ data: {
    contract_version: 'workflow.v1',
    request_id: 'request-1',
    ok: true,
    result: {
      accepted: true,
      command_id: 'advance-key',
      session_id: 'product-session-new',
      state_version: 3,
      projection: successorProjection('pending'),
    },
  } });
}

function configureLatestRestart(nextProjection = successorProjection()) {
  mocks.getProjection.mockImplementation((sessionId: string) => (
    sessionId === failedProductSession.session_id
      ? projectionResponse(sessionId, 7, failedProductSession.projection)
      : projectionResponse(sessionId, 2, nextProjection)
  ));
  mocks.getProductStageRelay.mockImplementation(() => relayResponse(true));
  mocks.restartOnLatest.mockImplementation(() => restartAccepted());
  mocks.getSession.mockResolvedValue({ data: { data: { session: successorSession() } } });
  mocks.advanceStepAndHandOff.mockImplementation(() => commandAccepted());
}

describe('WorkflowPanel restart failed product workflow on latest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.currentSession = failedProductSession;
    mocks.fetchWorkflowUI.mockResolvedValue({});
    mocks.loadActiveSession.mockResolvedValue(undefined);
    mocks.loadConversationTasks.mockResolvedValue(undefined);
    mocks.setSession.mockImplementation((_conversationId: string, session: WorkflowSession) => {
      mocks.currentSession = session;
    });
    mocks.uuidv4
      .mockReset()
      .mockReturnValueOnce('restart-key')
      .mockReturnValueOnce('advance-key')
      .mockReturnValue('later-key');
  });

  it('restarts on the latest package and dispatches the successor active session from its sole ready target', async () => {
    configureLatestRestart();
    render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.advanceStepAndHandOff).toHaveBeenCalledTimes(1));
    expect(mocks.restartOnLatest).toHaveBeenCalledWith(
      failedProductSession.session_id,
      { idempotency_key: 'restart-key', expected_state_version: 7 },
      { silentError: true },
    );
    expect(mocks.setSession).toHaveBeenCalledWith(
      'conversation-1',
      expect.objectContaining({ session_id: 'product-session-new', status: 'waiting' }),
    );
    expect(mocks.advanceStepAndHandOff).toHaveBeenCalledWith(
      'product-session-new',
      expect.objectContaining({
        command_id: 'advance-key',
        expected_state_version: 2,
        steps: [{ step_id: 'route_product_stage' }],
      }),
      { silentError: true },
    );
  });

  it.each(['pending', 'running'])('does not duplicate dispatch when a successor node is already %s', async (execution) => {
    configureLatestRestart(successorProjection(execution));
    render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.setSession).toHaveBeenCalledTimes(1));
    expect(mocks.restartOnLatest).toHaveBeenCalledTimes(1);
    expect(mocks.advanceStepAndHandOff).not.toHaveBeenCalled();
  });

  it('keeps the ordinary retry path when the product workflow has no latest-package restart', async () => {
    mocks.getProjection.mockImplementation((sessionId: string) => (
      projectionResponse(sessionId, 7, failedProductSession.projection)
    ));
    mocks.getProductStageRelay.mockImplementation(() => relayResponse(false));
    mocks.advanceStepAndHandOff.mockImplementation(() => commandAccepted());
    render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.advanceStepAndHandOff).toHaveBeenCalledTimes(1));
    expect(mocks.restartOnLatest).not.toHaveBeenCalled();
    expect(mocks.advanceStepAndHandOff).toHaveBeenCalledWith(
      failedProductSession.session_id,
      expect.objectContaining({ steps: [{ step_id: 'write_product_solution_document' }] }),
      { silentError: true },
    );
  });

  it('does not query product relay or restart non-product workflows', async () => {
    mocks.currentSession = { ...failedProductSession, workflow_id: 'document_writer' };
    const onSendMessage = vi.fn();
    mocks.getProjection.mockImplementation((sessionId: string) => (
      projectionResponse(sessionId, 7, failedProductSession.projection)
    ));
    mocks.advanceStepAndHandOff.mockImplementation(() => commandAccepted());
    render(<WorkflowPanel conversationId='conversation-1' onSendMessage={onSendMessage} />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(onSendMessage).toHaveBeenCalledWith('chat.workflowRetry'));
    expect(mocks.advanceStepAndHandOff).not.toHaveBeenCalled();
    expect(mocks.getProductStageRelay).not.toHaveBeenCalled();
    expect(mocks.restartOnLatest).not.toHaveBeenCalled();
  });

  it('shows friendly Chinese rollback names while submitting the original step id', async () => {
    const rollbackProjection: WorkflowSession['projection'] = {
      current: [],
      ready: [],
      retryable: [],
      continue: [],
      past: ['route_product_stage', 'build_direction_outline', 'write_direction_document'],
      rewindable: ['route_product_stage', 'build_direction_outline', 'write_direction_document'],
      nodes: {},
    };
    mocks.currentSession = {
      ...failedProductSession,
      status: 'completed',
      current_step_id: 'write_direction_document',
      projection: rollbackProjection,
      steps: ['route_product_stage', 'build_direction_outline', 'write_direction_document'].map((stepId, index) => ({
        step_id: stepId,
        attempt: 1,
        id: `step-${index}`,
        session_id: failedProductSession.session_id,
        task_id: `task-${index}`,
        status: 'succeeded',
        validity: 'effective' as const,
        created_at: '2026-09-10T00:00:00Z',
        updated_at: '2026-09-10T00:00:01Z',
      })),
    };
    mocks.getProjection.mockImplementation((sessionId: string) => (
      projectionResponse(sessionId, 7, rollbackProjection)
    ));
    mocks.advanceStepAndHandOff.mockImplementation(() => commandAccepted());
    render(<WorkflowPanel conversationId='conversation-1' />);

    expect(screen.getByRole('button', { name: '选择产品阶段' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成产品方向大纲' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '撰写产品方向文档' })).toBeInTheDocument();
    expect(screen.queryByText('route_product_stage')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '生成产品方向大纲' }));
    await waitFor(() => expect(mocks.advanceStepAndHandOff).toHaveBeenCalledTimes(1));
    expect(mocks.advanceStepAndHandOff).toHaveBeenCalledWith(
      failedProductSession.session_id,
      expect.objectContaining({ steps: [{ step_id: 'build_direction_outline' }] }),
      { silentError: true },
    );
  });

  it('replays the exact restart payload after a network-uncertain response', async () => {
    configureLatestRestart();
    mocks.getProductStageRelay
      .mockImplementationOnce(() => relayResponse(true))
      .mockImplementationOnce(() => relayResponse(false));
    mocks.restartOnLatest
      .mockRejectedValueOnce(new Error('network uncertain'))
      .mockImplementationOnce(() => restartAccepted());
    render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.restartOnLatest).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.advanceStepAndHandOff).toHaveBeenCalledTimes(1));
    expect(mocks.restartOnLatest.mock.calls[1][1]).toBe(mocks.restartOnLatest.mock.calls[0][1]);
    expect(mocks.restartOnLatest.mock.calls[1][1]).toEqual({
      idempotency_key: 'restart-key',
      expected_state_version: 7,
    });
  });

  it('drops the restart payload after an explicit HTTP rejection', async () => {
    configureLatestRestart();
    const rejection = Object.assign(new Error('conflict'), { response: { status: 409 } });
    mocks.restartOnLatest
      .mockRejectedValueOnce(rejection)
      .mockImplementationOnce(() => restartAccepted());
    render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.restartOnLatest).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.advanceStepAndHandOff).toHaveBeenCalledTimes(1));
    expect(mocks.restartOnLatest.mock.calls[0][1].idempotency_key).toBe('restart-key');
    expect(mocks.restartOnLatest.mock.calls[1][1].idempotency_key).not.toBe('restart-key');
  });

  it('recovers to a waiting successor with Continue enabled when automatic dispatch fails', async () => {
    configureLatestRestart();
    mocks.advanceStepAndHandOff.mockRejectedValue(
      Object.assign(new Error('dispatch failed'), { response: { status: 503 } }),
    );
    const view = render(<WorkflowPanel conversationId='conversation-1' />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.workflowRetry' }));

    await waitFor(() => expect(mocks.setSession).toHaveBeenCalledWith(
      'conversation-1',
      expect.objectContaining({ session_id: 'product-session-new', status: 'waiting' }),
    ));
    // The hook mock does not subscribe to setSession; publish the acknowledged
    // successor to model the store notification before asserting its controls.
    mocks.currentSession = { ...successorSession(), status: 'waiting' };
    view.rerender(<WorkflowPanel conversationId='conversation-1' />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'chat.workflowSaveAndContinue' })).toBeEnabled());
  });
});
