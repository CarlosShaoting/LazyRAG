import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ProductCurrentStageView,
  ProductProjectViews,
  productPrototypePreviewDocument,
  productWorkflowSectionKeys,
} from './ProductProjectViews';
import { PRODUCT_STAGE_IDS } from './ProductStageRelay';
import type { ProductProjectArtifact, ProductStageRelayState } from '@/modules/chat/utils/request';

const { getState, getArtifact, updateDecision, updateMarkdown, download } = vi.hoisted(() => ({
  getState: vi.fn(), getArtifact: vi.fn(), updateDecision: vi.fn(), updateMarkdown: vi.fn(), download: vi.fn(),
}));
vi.mock('@/modules/chat/utils/request', () => ({
  WorkflowSessionApi: () => ({
    getProductStageRelay: getState, getProductProjectArtifact: getArtifact,
    updateProductDecision: updateDecision, updateProductProjectMarkdown: updateMarkdown,
  }),
}));
vi.mock('./MarkdownArtifactEditor', () => ({
  MarkdownArtifactEditor: ({ markdown, sourceRevision, onSave }: {
    markdown: string;
    sourceRevision: number;
    onSave: (markdown: string, revision: number) => Promise<unknown>;
  }) => <div><span>{markdown}</span><textarea aria-label='project-markdown-editor' defaultValue={markdown} />
    <button type='button' onClick={(event) => void onSave(
      (event.currentTarget.previousElementSibling as HTMLTextAreaElement).value, sourceRevision,
    )}>save-project-markdown</button></div>,
}));
vi.mock('@/modules/chat/utils/download', () => ({ downloadStream: download }));
vi.mock('@/components/request', () => ({ getLocalizedErrorMessage: (cause: Error) => cause.message }));
vi.mock('../MarkdownViewer/MermaidBlock', () => ({
  default: ({ code }: { code: string }) => <div data-testid='project-mermaid'>{code}</div>,
}));
vi.mock('react-i18next', () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

const design: ProductProjectArtifact = {
  artifact_id: 'design-document', stage: 'design', title: 'Shared product design', version: 'v2',
  status: 'accepted', source_session_id: 'design-run', slot_id: 'design_document',
  revision_id: 'revision-design-2', revision: 2, available: true, stale: false,
  available_formats: ['html', 'markdown'],
};
const prototype: ProductProjectArtifact = {
  ...design, stage: 'prototype', title: 'Shared prototype', artifact_id: 'prototype-html',
  source_session_id: 'prototype-run', slot_id: 'prototype_html', revision_id: 'revision-prototype-1',
};
const available: ProductStageRelayState = {
  supported: true, can_relay: false, session_id: 'current-run', state_version: 1,
  current_stage: 'prd', run_status: 'executing', next_stages: [], actions: [], artifacts: [],
  project: {
    workspace_id: 'internal-project-id', conversation_id: 'conversation-1', current_session_id: 'current-run',
    artifacts: [design, prototype], decisions: [{ id: 'decision-1', summary: 'Keep user approval', status: 'accepted' }],
    open_questions: [{ id: 'question-1', question: 'Who reviews exceptions?', owner: 'Product owner' }],
  },
};

function response(stage = 'design', content = '# Same project design') {
  return { data: { result: {
    ...(stage === 'prototype' ? prototype : design), stage, content,
    content_format: stage === 'prototype' ? 'html' : 'markdown', mime_type: stage === 'prototype' ? 'text/html' : 'text/markdown',
    slot_key: stage === 'prototype' ? 'prototype_html' : 'design_document',
  } } };
}

function mount() {
  const props = {
    sessionId: 'current-run', refreshKey: '1', stageRunning: true,
    beforeProjectMutation: vi.fn().mockResolvedValue(true), onPreviewChange: vi.fn(), onBusyChange: vi.fn(),
    onRequestStage: vi.fn(), onDecisionChanged: vi.fn(),
  };
  return { props, ...render(<ProductProjectViews {...props} />) };
}

beforeEach(() => {
  vi.clearAllMocks();
  getState.mockResolvedValue({ data: { result: available } });
  getArtifact.mockImplementation((_sessionId, stage) => Promise.resolve(response(stage)));
  updateMarkdown.mockResolvedValue({ data: { result: {
    session_id: 'current-run', stage: 'design', state_version: 2, markdown: '# Updated design',
    revision_id: 'revision-design-3', revision: 3, slot_id: 'design_document',
    html_synced: true, html_sync_required: false, html_revision_id: 'design-html-2', html_revision: 2,
  } } });
});

describe('ProductProjectViews', () => {
  it('gives each sibling section a unique key while preserving session remounts', () => {
    const first = productWorkflowSectionKeys('same-run');
    const second = productWorkflowSectionKeys('other-run');

    expect(new Set(Object.values(first))).toHaveLength(3);
    expect(Object.values(first).every((key) => key.startsWith('same-run:'))).toBe(true);
    expect(Object.values(second)).not.toEqual(Object.values(first));
  });

  it('shows all shared views during an active stage and previews existing content in the same panel', async () => {
    const { props } = mount();
    await screen.findByText('Keep user approval');
    expect(screen.getAllByRole('tab')).toHaveLength(7);
    for (const stage of PRODUCT_STAGE_IDS) {
      expect(screen.getByRole('tab', { name: new RegExp(`^chat.productStageRelay.stages.${stage}`) })).toBeInTheDocument();
    }
    expect(screen.getByText('chat.productProject.runningHint')).toBeInTheDocument();
    expect(getArtifact).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    expect(await screen.findByRole('heading', { name: 'Same project design' })).toBeInTheDocument();
    expect(props.beforeProjectMutation).not.toHaveBeenCalled();
    expect(props.onPreviewChange).toHaveBeenLastCalledWith('current-run');
    expect(getArtifact).toHaveBeenCalledWith('current-run', 'design', expect.any(Object), 'html');
    expect(screen.queryByText('internal-project-id')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.prd/ }));
    await waitFor(() => expect(props.onPreviewChange).toHaveBeenLastCalledWith(null));
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument();
  });

  it('runs prototype interactions in an isolated inline iframe without host or network authority', async () => {
    const html = '<html><head><base href="https://example.com"><meta http-equiv="refresh" content="0;url=https://example.com"></head><body><button onclick="this.textContent=\'Done\'">Try</button><script>window.demo=true</script></body></html>';
    getArtifact.mockResolvedValue(response('prototype', html));
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.prototype/ }));
    const iframe = await screen.findByTitle('chat.productProject.prototypeTitle');
    expect(iframe).toHaveAttribute('sandbox', 'allow-scripts');
    expect(iframe).toHaveAttribute('referrerpolicy', 'no-referrer');
    const source = iframe.getAttribute('srcdoc') ?? '';
    expect(source).toContain("connect-src 'none'");
    expect(source).toContain("form-action 'none'");
    expect(source).toContain('onclick=');
    expect(source).not.toContain('<base');
    expect(source).not.toContain('http-equiv="refresh"');
  });

  it('offers uncreated stages without inventing content or starting a stage', async () => {
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.handoff/ }));
    expect(await screen.findByText('chat.productProject.emptyHint')).toBeInTheDocument();
    expect(getArtifact).not.toHaveBeenCalled();
  });

  it('opens shared artifacts without making read-only access depend on a pending save', async () => {
    const { props } = mount();
    props.beforeProjectMutation.mockResolvedValue(false);
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    expect(await screen.findByRole('heading', { name: 'Same project design' })).toBeInTheDocument();
    expect(props.beforeProjectMutation).not.toHaveBeenCalled();
    expect(props.onPreviewChange).toHaveBeenCalledWith('current-run');
  });

  it('ignores a late artifact response after the user selects another view', async () => {
    let resolveDesign!: (value: unknown) => void;
    getArtifact.mockImplementation((_sessionId, stage) => stage === 'design'
      ? new Promise((resolve) => { resolveDesign = resolve; })
      : Promise.resolve(response('prototype', '<h1>Current prototype</h1>')));
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    await waitFor(() => expect(getArtifact).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.prototype/ }));
    await screen.findByTitle('chat.productProject.prototypeTitle');
    await act(async () => { resolveDesign(response('design', '# Late obsolete result')); });
    expect(screen.queryByText('Late obsolete result')).not.toBeInTheDocument();
    expect(screen.getByTitle('chat.productProject.prototypeTitle')).toHaveAttribute('srcdoc', expect.stringContaining('Current prototype'));
  });

  it('clears the prior session view and ignores its in-flight response when changing projects', async () => {
    let resolveOld!: (value: unknown) => void;
    getArtifact.mockImplementation(() => new Promise((resolve) => { resolveOld = resolve; }));
    const { props, rerender } = mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    await waitFor(() => expect(getArtifact).toHaveBeenCalledOnce());
    getState.mockResolvedValue({ data: { result: { ...available, project: { ...available.project, artifacts: [], decisions: [], open_questions: [] } } } });
    rerender(<ProductProjectViews {...props} sessionId='other-project-run' refreshKey='2' />);
    await waitFor(() => expect(screen.queryByText('Keep user approval')).not.toBeInTheDocument());
    await act(async () => { resolveOld(response('design', '# Other project must not see this')); });
    expect(screen.queryByText('Other project must not see this')).not.toBeInTheDocument();
    expect(props.onPreviewChange).toHaveBeenLastCalledWith(null);
  });

  it('marks preserved versions affected by edits without exposing source paths', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, project: {
      ...available.project, artifacts: [{ ...design, stale: true, reason: '/private/source/path' }],
    } } } });
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    expect(await screen.findByText('chat.productProject.staleHint')).toBeInTheDocument();
    expect(screen.queryByText('/private/source/path')).not.toBeInTheDocument();
  });

  it('removes document-supplied policy overrides before adding the restrictive preview policy', () => {
    const preview = productPrototypePreviewDocument('<meta http-equiv="Content-Security-Policy" content="default-src *"><h1>Hello</h1>');
    expect(preview.match(/http-equiv="Content-Security-Policy"/g)).toHaveLength(1);
    expect(preview).not.toContain('default-src *');
  });

  it('does not load remote Markdown images or navigate the app when reading evidence links', async () => {
    getArtifact.mockResolvedValue(response('design', '# Design\n![tracker](https://example.com/collect?q=secret)\n[Evidence](https://example.com/source)\n<script>alert(1)</script>'));
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    const link = await screen.findByRole('link', { name: 'Evidence' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('tabpanel').querySelector('script')).toBeNull();
  });

  it('downloads the loaded shared artifact without opening another stage or requesting another copy', async () => {
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productProject.downloadView' }));
    expect(download).toHaveBeenCalledWith(expect.any(Blob), 'design-v2.md');
    expect(download.mock.calls[0][0].type).toBe('text/markdown;charset=utf-8');
    expect(getArtifact).toHaveBeenCalledTimes(1);
    expect(updateDecision).not.toHaveBeenCalled();
  });

  it('opens HTML by default and switches to the Markdown representation in the same project view', async () => {
    getArtifact.mockImplementation((_sessionId, stage, _options, format) => Promise.resolve(
      format === 'markdown'
        ? response(stage, '# Same semantic artifact')
        : { data: { result: { ...design, stage, content: '<!doctype html><html><head><title>View</title></head><body><h1>Same semantic artifact</h1></body></html>', content_format: 'html', mime_type: 'text/html', slot_key: 'design_document_html' } } },
    ));
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    await screen.findByTitle('chat.productProject.prototypeTitle');
    expect(getArtifact).toHaveBeenLastCalledWith('current-run', 'design', expect.any(Object), 'html');
    fireEvent.click(screen.getByRole('tab', { name: 'chat.productProject.markdownView' }));
    expect(await screen.findByDisplayValue('# Same semantic artifact')).toBeInTheDocument();
    expect(getArtifact).toHaveBeenLastCalledWith('current-run', 'design', expect.any(Object), 'markdown');
  });

  it('edits Markdown in the shared project and saves an immutable new version', async () => {
    getArtifact.mockImplementation((_sessionId, stage, _options, format) => Promise.resolve(
      format === 'markdown'
        ? { data: { result: { ...design, stage, editable: true, content: '# Original design', content_format: 'markdown', mime_type: 'text/markdown', slot_key: 'design_document' } } }
        : { data: { result: { ...design, stage, content: '<!doctype html><h1>Original design</h1>', content_format: 'html', mime_type: 'text/html', slot_key: 'design_document_html' } } },
    ));
    const { props } = mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    await screen.findByTitle('chat.productProject.prototypeTitle');
    fireEvent.click(screen.getByRole('tab', { name: 'chat.productProject.markdownView' }));
    const editor = await screen.findByRole('textbox', { name: 'project-markdown-editor' });
    expect(screen.getByText('chat.productProject.editableHint')).toBeInTheDocument();
    fireEvent.change(editor, { target: { value: '# Updated design' } });
    fireEvent.click(screen.getByRole('button', { name: 'save-project-markdown' }));
    await waitFor(() => expect(updateMarkdown).toHaveBeenCalledOnce());
    expect(updateMarkdown).toHaveBeenCalledWith('current-run', 'design', {
      base_revision_id: 'revision-design-2', base_revision: 2,
      markdown: '# Updated design', idempotency_key: expect.any(String),
    }, expect.any(Object));
    expect(await screen.findByDisplayValue('# Updated design')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'chat.productProject.htmlView' }));
    await waitFor(() => expect(props.beforeProjectMutation).toHaveBeenCalledOnce());
    expect(await screen.findByTitle('chat.productProject.prototypeTitle')).toHaveAttribute(
      'srcdoc', expect.stringContaining('Original design'),
    );
  });

  it('renders Markdown timelines and quadrant diagrams as diagrams in the shared view', async () => {
    getArtifact.mockResolvedValue(response('design', [
      '# Product plan',
      '```mermaid',
      'timeline',
      '  title Delivery milestones',
      '  Q1 : Validate scope',
      '```',
      '```mermaid',
      'quadrantChart',
      '  x-axis Low effort --> High effort',
      '  y-axis Low impact --> High impact',
      '  Search: [0.25, 0.75]',
      '```',
    ].join('\n')));
    mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.design/ }));
    const diagrams = await screen.findAllByTestId('project-mermaid');
    expect(diagrams).toHaveLength(2);
    expect(diagrams[0]).toHaveTextContent('Delivery milestones');
    expect(diagrams[1]).toHaveTextContent('Low effort');
  });

  it('keeps the stage editor mounted and preserves editing state while a shared view is open', () => {
    const { rerender } = render(<ProductCurrentStageView sessionId='same-run' hidden={false}><textarea aria-label='Editor' defaultValue='draft' /></ProductCurrentStageView>);
    const editor = screen.getByRole('textbox');
    fireEvent.change(editor, { target: { value: 'local editing state' } });
    rerender(<ProductCurrentStageView sessionId='same-run' hidden><textarea aria-label='Editor' defaultValue='draft' /></ProductCurrentStageView>);
    expect(editor).not.toBeVisible();
    rerender(<ProductCurrentStageView sessionId='same-run' hidden={false}><textarea aria-label='Editor' defaultValue='draft' /></ProductCurrentStageView>);
    expect(screen.getByRole('textbox')).toBe(editor);
    expect(editor).toHaveValue('local editing state');
  });

  it('chooses the displayed stage for confirmation without starting it or asking for a second stage selection', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, can_relay: true } } });
    const { props } = mount();
    await screen.findByText('Keep user approval');
    fireEvent.click(screen.getByRole('tab', { name: /chat.productStageRelay.stages.prototype/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productProject.selectStage' }));
    expect(props.onRequestStage).toHaveBeenCalledWith('prototype');
    expect(updateDecision).not.toHaveBeenCalled();
  });

  it('clearly leaves key decisions pending during an active stage', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, project: { ...available.project,
      decisions: [{ decision_id: 'key-1', statement: 'Require human approval', status: 'proposed', confirmation_required: true, decision_hash: 'hash-1' }],
    } } } });
    mount();
    expect(await screen.findByRole('heading', { name: 'Require human approval' })).toBeInTheDocument();
    expect(screen.getByText('chat.productProject.confirmAfterFinish')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'chat.productProject.adoptDecision' })).not.toBeInTheDocument();
    expect(updateDecision).not.toHaveBeenCalled();
  });
});

describe('ProductProjectViews human decision confirmation', () => {
  const pending = { ...available, can_relay: true, run_status: 'awaiting-stage-confirmation', project: {
    ...available.project!, can_update_decisions: true,
    decisions: [{ decision_id: 'key-1', decision_question: 'How are high-risk writes approved?', value: { approval: 'human before write', exceptions: 'none' }, status: 'proposed', confirmation_required: true, decision_hash: 'hash-1',
      has_accepted_baseline: true, accepted_baseline_value: 'manual review', decision_content: { scope: 'payments', permission: 'owner only' },
    }],
  } };

  beforeEach(() => {
    getState.mockResolvedValue({ data: { result: pending } });
    updateDecision.mockResolvedValue({ data: { result: { session_id: 'current-run', state_version: 2, decision_id: 'key-1', status: 'accepted', deferred: false } } });
  });

  it('requires an independent click and saves before confirming the exact displayed decision', async () => {
    const { props } = mount();
    const accept = await screen.findByRole('button', { name: 'chat.productProject.adoptDecision' });
    expect(screen.getByRole('heading', { name: 'How are high-risk writes approved?' })).toBeInTheDocument();
    expect(screen.getAllByText('human before write；none')).not.toHaveLength(0);
    expect(screen.getByText('manual review')).toBeInTheDocument();
    expect(screen.getByText('payments；owner only')).toBeInTheDocument();
    expect(updateDecision).not.toHaveBeenCalled();
    fireEvent.click(accept);
    await waitFor(() => expect(updateDecision).toHaveBeenCalledOnce());
    expect(props.beforeProjectMutation).toHaveBeenCalledOnce();
    expect(updateDecision).toHaveBeenCalledWith('current-run', 'key-1', {
      action: 'accept', expected_state_version: 1, expected_decision_hash: 'hash-1', idempotency_key: expect.any(String),
    }, expect.any(Object));
    expect(props.onDecisionChanged).toHaveBeenCalledOnce();
    expect(props.onPreviewChange).not.toHaveBeenCalledWith('current-run');
  });

  it('shows the next pending decision immediately after confirming the current one', async () => {
    const secondDecision = {
      decision_id: 'key-2', decision_question: 'Who can publish the result?', value: 'project owner',
      status: 'proposed', confirmation_required: true, decision_hash: 'hash-2',
    };
    const withTwo = { ...pending, project: { ...pending.project, decisions: [...pending.project.decisions, secondDecision] } };
    const afterConfirmation = { ...withTwo, state_version: 2, project: { ...withTwo.project,
      decisions: [{ ...withTwo.project.decisions[0], status: 'accepted' }, secondDecision],
    } };
    getState
      .mockResolvedValueOnce({ data: { result: withTwo } })
      .mockResolvedValueOnce({ data: { result: withTwo } })
      .mockResolvedValue({ data: { result: afterConfirmation } });
    const { props } = mount();
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productProject.adoptDecision' }));
    expect(await screen.findByRole('heading', { name: 'Who can publish the result?' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'How are high-risk writes approved?' })).not.toBeInTheDocument();
    expect(props.onDecisionChanged).toHaveBeenCalledOnce();
  });

  it('refreshes but refuses confirmation when the decision changed after it was displayed', async () => {
    mount();
    const accept = await screen.findByRole('button', { name: 'chat.productProject.adoptDecision' });
    getState.mockResolvedValue({ data: { result: { ...pending, project: { ...pending.project,
      decisions: [{ ...pending.project.decisions[0], decision_hash: 'changed-hash' }],
    } } } });
    fireEvent.click(accept);
    expect(await screen.findByRole('alert')).toHaveTextContent('chat.productProject.decisionChanged');
    expect(updateDecision).not.toHaveBeenCalled();
  });

  it('retries an uncertain confirmation using the exact same idempotent command', async () => {
    updateDecision.mockRejectedValueOnce(new Error('network unavailable'));
    mount();
    const accept = await screen.findByRole('button', { name: 'chat.productProject.adoptDecision' });
    fireEvent.click(accept);
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    const first = updateDecision.mock.calls[0][2];
    fireEvent.click(accept);
    await waitFor(() => expect(updateDecision).toHaveBeenCalledTimes(2));
    expect(updateDecision.mock.calls[1][2]).toEqual(first);
  });

  it('uses the latest project version after a definite conflict response', async () => {
    const conflict = Object.assign(new Error('version conflict'), { response: { status: 409 } });
    updateDecision.mockRejectedValueOnce(conflict);
    getState
      .mockResolvedValueOnce({ data: { result: pending } })
      .mockResolvedValueOnce({ data: { result: pending } })
      .mockResolvedValue({ data: { result: { ...pending, state_version: 2 } } });
    mount();
    const accept = await screen.findByRole('button', { name: 'chat.productProject.adoptDecision' });
    fireEvent.click(accept);
    expect(await screen.findByRole('alert')).toHaveTextContent('version conflict');
    const first = updateDecision.mock.calls[0][2];
    fireEvent.click(accept);
    await waitFor(() => expect(updateDecision).toHaveBeenCalledTimes(2));
    expect(updateDecision.mock.calls[1][2]).toMatchObject({ expected_state_version: 2 });
    expect(updateDecision.mock.calls[1][2].idempotency_key).not.toBe(first.idempotency_key);
  });

  it('sends defer without approving the decision', async () => {
    updateDecision.mockResolvedValue({ data: { result: { session_id: 'current-run', state_version: 2, decision_id: 'key-1', status: 'proposed', deferred: true } } });
    const deferred = { ...pending, state_version: 2, project: { ...pending.project,
      decisions: [{ ...pending.project.decisions[0], deferred: true }],
    } };
    getState
      .mockResolvedValueOnce({ data: { result: pending } })
      .mockResolvedValueOnce({ data: { result: pending } })
      .mockResolvedValue({ data: { result: deferred } });
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productProject.decideLater' }));
    await waitFor(() => expect(updateDecision).toHaveBeenCalledOnce());
    expect(updateDecision.mock.calls[0][2]).toMatchObject({ action: 'defer', expected_decision_hash: 'hash-1' });
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'How are high-risk writes approved?' })).not.toBeInTheDocument());
  });
});
