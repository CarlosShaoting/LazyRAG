import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WorkflowSession, WorkflowUI } from '@/modules/chat/store/workflowPanel';
import { WorkflowPanel } from './index';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const mocks = vi.hoisted(() => ({
  currentSession: null as any,
  fetchWorkflowUI: vi.fn(),
  getProductStageRelay: vi.fn(),
  refresh: vi.fn(),
  translate: vi.fn((key: string) => key),
}));

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'zh-CN', resolvedLanguage: 'zh-CN' },
    t: mocks.translate,
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
  axiosInstance: {
    defaults: {},
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    get: vi.fn(), post: vi.fn(), patch: vi.fn(),
  },
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
    setAutoRunning: vi.fn(),
    fetchWorkflowUI: mocks.fetchWorkflowUI,
    setFocusedTab: vi.fn(),
    setFocusedSortOrder: vi.fn(),
    createSlotItem: vi.fn(),
    loadActiveSession: vi.fn(),
    setSession: vi.fn(),
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
    loadConversationTasks: vi.fn(),
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
    getProductStageRelay: mocks.getProductStageRelay,
  }),
}));

vi.mock('@/modules/chat/utils/chunkUpload', () => ({ uploadFileInChunks: vi.fn() }));

vi.mock('./SlotComponents', async () => {
  const { createContext } = await import('react');
  return {
    isWriterIrSource: () => false,
    SlotDownloadContext: createContext(true),
    SlotMarkdownStream: () => null,
    SlotRenderer: ({ slotId }: { slotId: string }) => <div data-testid={`slot-${slotId}`} />,
  };
});

vi.mock('./ppt/SlideThumb', () => ({ SlideThumb: () => null }));
vi.mock('./actions/WorkflowTabActions', () => ({ WorkflowTabActions: () => null }));
vi.mock('./writerArtifactStream', () => ({ findWriterArtifactStream: () => undefined }));

const sessionBase: WorkflowSession = {
  session_id: 'same-product-session',
  conversation_id: 'conversation-1',
  workflow_id: 'product_solution_delivery',
  workflow_mode: 'dynamic',
  status: 'active',
  current_step_id: 'write_product_solution_document',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:01Z',
  slots: [{
    slot_id: 'design-document',
    slot: 'design_document',
    step_id: 'write_product_solution_document',
    revision: 1,
    selected: true,
    created_at: '2026-09-09T00:00:01Z',
    content_type: 'text',
    artifact_value: { text: 'one design document' },
  }],
  steps: [],
  projection: {
    completed: false,
    current: ['write_product_solution_document'],
    ready: [],
    retryable: [],
    continue: [],
    past: [],
  },
};

const tabbedUI: WorkflowUI = {
  name: 'Product solution delivery',
  tabs: [{
    id: 'design-document-tab',
    step_id: 'write_product_solution_document',
    label: 'Product design',
    slots: [{ id: 'design_document', label: 'Design document', type: 'text' }],
  }],
};

function expectOneCurrentStageBody(container: HTMLElement) {
  expect(container.querySelectorAll('.workflow-panel')).toHaveLength(1);
  expect(container.querySelectorAll('.workflow-panel__body')).toHaveLength(1);
  expect(container.querySelectorAll('#product-current-work-same-product-session')).toHaveLength(1);
}

describe('WorkflowPanel product section reconciliation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.currentSession = sessionBase;
    mocks.getProductStageRelay.mockResolvedValue({ data: { result: {
      supported: true,
      can_relay: true,
      can_accept_current_artifact: false,
      session_id: 'same-product-session',
      state_version: 1,
      current_stage: 'design',
      run_status: 'awaiting-stage-confirmation',
      next_stages: [{ id: 'prd' }],
      actions: ['continue', 'finish'],
      artifacts: [],
      project: {
        workspace_id: 'workspace-1',
        conversation_id: 'conversation-1',
        current_session_id: 'same-product-session',
        artifacts: [],
        decisions: [],
        open_questions: [],
      },
    } } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('removes the fallback grid and keeps one body while tabs load and relay mounts', async () => {
    const ui = deferred<WorkflowUI>();
    mocks.fetchWorkflowUI.mockReturnValue(ui.promise);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { container, rerender } = render(<WorkflowPanel conversationId='conversation-1' />);

    expectOneCurrentStageBody(container);
    expect(container.querySelectorAll('.workflow-panel__auto-grid')).toHaveLength(1);
    expect(container.querySelectorAll('.product-stage-relay')).toHaveLength(0);

    await act(async () => {
      ui.resolve(tabbedUI);
      await ui.promise;
    });

    await waitFor(() => {
      expectOneCurrentStageBody(container);
      expect(container.querySelectorAll('.workflow-panel__auto-grid')).toHaveLength(0);
      expect(container.querySelectorAll('.workflow-panel__tab-content')).toHaveLength(1);
    });

    mocks.currentSession = {
      ...sessionBase,
      status: 'completed',
      updated_at: '2026-09-09T00:00:02Z',
      projection: {
        ...sessionBase.projection,
        completed: true,
        current: [],
        past: ['write_product_solution_document'],
      },
    };
    rerender(<WorkflowPanel conversationId='conversation-1' />);

    await waitFor(() => {
      expectOneCurrentStageBody(container);
      expect(container.querySelectorAll('.workflow-panel__auto-grid')).toHaveLength(0);
      expect(container.querySelectorAll('.product-stage-relay')).toHaveLength(1);
    });

    const duplicateKeyErrors = consoleError.mock.calls
      .flatMap((call) => call.map(String))
      .filter((message) => /same key|unique ["']?key["']?|encountered two children/i.test(message));
    expect(duplicateKeyErrors).toEqual([]);
  });
});
