import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ConversationSettingsApi,
  FALLBACK_CHAT_ENTRY_DEFAULTS,
  parseChatEntryDefaults,
  parseThinkingDepth,
  resolveConversationThinkingDepth,
  WorkflowSessionApi,
} from './request';

const { patchMock, postMock, getMock } = vi.hoisted(() => ({
  patchMock: vi.fn(),
  postMock: vi.fn(),
  getMock: vi.fn(),
}));

vi.mock('@/components/request', () => ({
  axiosInstance: {
    defaults: {},
    patch: patchMock,
    post: postMock,
    get: getMock,
  },
  BASE_URL: '',
}));

describe('WorkflowSessionApi.convertDocument', () => {
  it.each([undefined, 0, 7])('preserves the optional draft baseline %s in the preview body', (draftVersion) => {
    WorkflowSessionApi().convertDocument('session', 'draft_document', -1, 4, 'latex', '# Draft', draftVersion);
    expect(postMock).toHaveBeenLastCalledWith(
      '/api/core/workflow-sessions/session/slots/draft_document/items/idx/-1:action-preview',
      { action: 'convert_document', base_revision: 4,
        ...(draftVersion !== undefined ? { base_draft_version: draftVersion } : {}),
        input: { output_format: 'latex', document: '# Draft' } },
      { silentError: true },
    );
  });
});

describe('WorkflowSessionApi.getProductProjectArtifact', () => {
  it('reads the project-bound view through the current session without navigation', () => {
    WorkflowSessionApi().getProductProjectArtifact('session/with spaces', 'prototype');
    expect(getMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/session%2Fwith%20spaces/product-artifacts/prototype',
      { params: { format: 'html' } },
    );
  });

  it('patches the editable Markdown representation without creating another project', () => {
    const payload = { base_revision_id: 'revision/2', base_revision: 2, markdown: '# Updated', idempotency_key: 'edit-1' };
    WorkflowSessionApi().updateProductProjectMarkdown('session/1', 'design', payload);
    expect(patchMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/session%2F1/product-artifacts/design/markdown', payload, undefined,
    );
  });

  it('posts an explicit decision confirmation with encoded identifiers', () => {
    const payload = { action: 'accept' as const, expected_state_version: 4, expected_decision_hash: 'hash', idempotency_key: 'command-1' };
    WorkflowSessionApi().updateProductDecision('session/1', 'decision/1', payload);
    expect(postMock).toHaveBeenCalledWith('/api/core/workflow-sessions/session%2F1/product-decisions/decision%2F1', payload, undefined);
  });
});

describe('WorkflowSessionApi.advanceStepAndHandOff', () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it('posts a versioned, idempotent command while preserving caller options and headers', () => {
    const payload = {
      contract_version: 'workflow.v1' as const,
      command_id: 'workflow-ui-command-1',
      tool: 'advance_step_and_hand_off' as const,
      session_id: 'session/with spaces',
      expected_state_version: 25,
      retry_origin: 'user' as const,
      steps: [{ step_id: 'build_design_outline', runtime_instruction: '继续生成设计大纲' }],
    };

    WorkflowSessionApi().advanceStepAndHandOff(
      'session/with spaces',
      payload,
      {
        timeout: 12_345,
        headers: {
          Authorization: 'Bearer local-token',
          'Idempotency-Key': 'must-be-replaced',
          'Workflow-Contract-Version': 'workflow.v999',
        },
      },
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/session%2Fwith%20spaces:advance-step-and-hand-off',
      payload,
      {
        timeout: 12_345,
        headers: {
          Authorization: 'Bearer local-token',
          'Workflow-Contract-Version': 'workflow.v1',
          'Idempotency-Key': payload.command_id,
        },
      },
    );
  });
});

describe('WorkflowSessionApi.restartOnLatest', () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it('posts the workspace-preserving restart with its idempotency key', () => {
    const payload = {
      idempotency_key: 'restart-on-latest-1',
      expected_state_version: 17,
    };

    WorkflowSessionApi().restartOnLatest(
      'session/with spaces',
      payload,
      {
        timeout: 12_345,
        headers: {
          Authorization: 'Bearer local-token',
          'Idempotency-Key': 'must-be-replaced',
        },
      },
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/session%2Fwith%20spaces:restart-on-latest',
      payload,
      {
        timeout: 12_345,
        headers: {
          Authorization: 'Bearer local-token',
          'Idempotency-Key': payload.idempotency_key,
        },
      },
    );
  });
});

describe('WorkflowSessionApi.saveWriterDocument', () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it('omits slot when saving the active draft document', () => {
    WorkflowSessionApi().saveWriterDocument(
      'ps-1',
      12,
      4,
      '# Draft',
      'draft_document',
      'draft',
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/ps-1/writer-document:save',
      { base_revision: 12, base_draft_version: 4, document: '# Draft', mode: 'draft' },
      undefined,
    );
  });

  it('keeps the explicit slot when saving an outline document', () => {
    WorkflowSessionApi().saveWriterDocument(
      'ps-1',
      3,
      undefined,
      '# Outline',
      'outline_document',
      'checkpoint',
      { type: 'heading', target_id: 'section-2', restart: true },
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/ps-1/writer-document:save',
      {
        base_revision: 3,
        document: '# Outline',
        mode: 'checkpoint',
        slot: 'outline_document',
        numbering_update: { type: 'heading', target_id: 'section-2', restart: true },
      },
      undefined,
    );
  });
});

describe('WorkflowSessionApi.patchSlotItem', () => {
  beforeEach(() => {
    patchMock.mockReset();
  });

  it('sends both slot revision and mutable draft version baselines', () => {
    WorkflowSessionApi().patchSlotItem(
      'ps-1', 'draft_document', -1, { text: '# Draft' }, 'text', 'draft', 7, 3,
    );

    expect(patchMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/ps-1/slots/draft_document/items/idx/-1',
      {
        value: { text: '# Draft' },
        content_type: 'text',
        mode: 'draft',
        base_revision: 7,
        base_draft_version: 3,
      },
      undefined,
    );
  });
});

describe('WorkflowSessionApi single-paragraph rewrite adapter', () => {
  const paragraph = {
    target: { type: 'block', block_type: 'paragraph', node_id: 'p1' },
    preview: { old_text: 'Whole paragraph.', new_text: 'Polished paragraph.' },
    patch: { type: 'writer_ir_patch', payload: { hunks: [] } },
  };
  const shared = {
    status: 'ready', action: 'rewrite_selection', base_revision: 4, representation: 'ir',
    artifact: { content_type: 'json', value: { document_id: 'doc' } },
    commit: { token: 'preview-token' },
  };

  it('unwraps one result without losing the full candidate or commit token', async () => {
    postMock.mockResolvedValue({ data: { code: 0, data: { ...shared, results: [paragraph] } } });
    const payload = { action: 'rewrite_selection' as const, base_revision: 4,
      input: { type: 'ir' as const, instruction: 'Polish', selection_ranges: [{ node_id: 'p1' }] } };
    const response = await WorkflowSessionApi().previewRewriteSelection('session', 'draft_document', -1, payload);
    expect(postMock).toHaveBeenLastCalledWith(
      '/api/core/workflow-sessions/session/slots/draft_document/items/idx/-1:action-preview', payload, undefined,
    );
    expect(response.data.data).toEqual({ ...shared, ...paragraph });
  });

  it.each([{ results: [] }, { results: [paragraph, paragraph] }])('rejects a non-single result', async ({ results }) => {
    postMock.mockResolvedValue({ data: { data: { ...shared, results } } });
    await expect(WorkflowSessionApi().previewRewriteSelection('session', 'draft_document', -1, {
      action: 'rewrite_selection', base_revision: 4,
      input: { type: 'markdown', instruction: 'Polish', selection_ranges: [{ selected_text: 'quote' }] },
    })).rejects.toThrow('Expected one paragraph');
  });

  it('leaves the unrelated PPT protocol unchanged', async () => {
    const ppt = { ...shared, ...paragraph, representation: 'ppt_html' };
    postMock.mockResolvedValue({ data: { data: ppt } });
    const response = await WorkflowSessionApi().previewRewriteSelection('session', 'slides', 0, {
      action: 'rewrite_selection', base_revision: 4,
      input: { instruction: 'Polish', selection: { type: 'ppt_html', page: 1, el: 'title' } },
    });
    expect(response.data.data).toEqual(ppt);
  });
});

describe('WorkflowSessionApi.writeBackWriterDocument', () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it('passes the selected GitHub provider through the shared write-back endpoint', () => {
    WorkflowSessionApi().writeBackWriterDocument(
      'ps-github',
      7,
      2,
      undefined,
      undefined,
      'draft_document',
      'github',
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/ps-github/writer-document:write-back',
      { base_revision: 7, base_draft_version: 2, provider: 'github' },
      undefined,
    );
  });

  it('passes a WeChat rendering template through the shared write-back endpoint', () => {
    WorkflowSessionApi().writeBackWriterDocument(
      'ps-wechat',
      8,
      3,
      undefined,
      undefined,
      'draft_document',
      'wechat',
      'clean',
    );

    expect(postMock).toHaveBeenCalledWith(
      '/api/core/workflow-sessions/ps-wechat/writer-document:write-back',
      { base_revision: 8, base_draft_version: 3, provider: 'wechat', template: 'clean' },
      undefined,
    );
  });
});

describe('chat entry defaults', () => {
  beforeEach(() => {
    patchMock.mockReset();
  });

  it('parses two complete profiles from the API envelope', () => {
    const profiles = {
      quick_question: {
        thinking_depth: 'low',
        conversation_settings: {
          chat_executor: 'lazymind',
          enable_workflow: false,
          workflow_mode: 'auto',
          enable_subagent: false,
        },
      },
      new_task: {
        thinking_depth: 'max',
        conversation_settings: {
          chat_executor: 'codex',
          enable_workflow: true,
          workflow_mode: 'dynamic',
          enable_subagent: true,
        },
      },
    } as const;

    expect(parseChatEntryDefaults({ data: profiles })).toEqual(profiles);
  });

  it('falls back per profile when persisted data is incomplete', () => {
    expect(parseChatEntryDefaults({
      quick_question: { thinking_depth: 'turbo' },
      new_task: FALLBACK_CHAT_ENTRY_DEFAULTS.new_task,
    })).toEqual(FALLBACK_CHAT_ENTRY_DEFAULTS);
  });

  it('derives profiles from legacy flat defaults during a rolling upgrade', () => {
    expect(parseChatEntryDefaults({
      enable_workflow: false,
      workflow_mode: 'auto',
      enable_subagent: false,
    })).toEqual({
      quick_question: {
        thinking_depth: 'medium',
        conversation_settings: {
          chat_executor: 'lazymind',
          enable_workflow: false,
          workflow_mode: 'auto',
          enable_subagent: false,
        },
      },
      new_task: {
        thinking_depth: 'high',
        conversation_settings: {
          chat_executor: 'lazymind',
          enable_workflow: false,
          workflow_mode: 'auto',
          enable_subagent: false,
        },
      },
    });
  });

  it('patches only the selected entry profile', () => {
    const next = FALLBACK_CHAT_ENTRY_DEFAULTS.new_task;
    ConversationSettingsApi().patchChatEntryDefault('new_task', next);

    expect(patchMock).toHaveBeenCalledWith(
      '/api/core/user/chat-settings',
      { new_task: next },
      undefined,
    );
  });

  it('normalizes persisted conversation depth and isolates legacy conversations', () => {
    expect(parseThinkingDepth(' MAX ')).toBe('max');
    expect(parseThinkingDepth('turbo')).toBeUndefined();
    expect(resolveConversationThinkingDepth({ thinking_depth: 'high' })).toBe('high');
    expect(resolveConversationThinkingDepth({})).toBe('medium');
  });
});
