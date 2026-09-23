import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductStageRelay, PRODUCT_STAGE_IDS } from './ProductStageRelay';
import type { ProductStageRelayState } from '@/modules/chat/utils/request';

const { getState, relay } = vi.hoisted(() => ({ getState: vi.fn(), relay: vi.fn() }));
vi.mock('@/modules/chat/utils/request', () => ({
  WorkflowSessionApi: () => ({ getProductStageRelay: getState, relayProductStage: relay }),
}));
vi.mock('@/components/request', () => ({ getLocalizedErrorMessage: (cause: Error) => cause.message }));
vi.mock('react-i18next', () => {
  const t = (key: string, options?: { count?: number }) => options?.count === undefined ? key : `${key}:${options.count}`;
  return { useTranslation: () => ({ t }) };
});

const available: ProductStageRelayState = {
  supported: true, can_relay: true, session_id: 'source-1', state_version: 7,
  can_accept_current_artifact: true,
  current_stage: 'direction', run_status: 'awaiting-stage-confirmation',
  next_stages: [{ id: 'design', label: '产品方案' }],
  actions: ['continue', 'switch-stage', 'finish'], artifacts: [],
};

function mount() {
  const props = {
    sessionId: 'source-1', beforeAction: vi.fn().mockResolvedValue(true),
    onBusyChange: vi.fn(), onSessionReady: vi.fn().mockResolvedValue(undefined),
  };
  render(<ProductStageRelay {...props} />);
  return props;
}

beforeEach(() => {
  vi.clearAllMocks();
  getState.mockResolvedValue({ data: { result: available } });
  relay.mockResolvedValue({ data: { result: { session_id: 'next-1', source_session_id: 'source-1', status: 'waiting' } } });
});

describe('ProductStageRelay', () => {
  it('offers all seven entries and requires a click before starting a stage', async () => {
    const props = mount();
    const select = await screen.findByRole('combobox');
    expect([...select.querySelectorAll('option')].map((option) => option.value).filter(Boolean)).toEqual(PRODUCT_STAGE_IDS);
    expect(relay).not.toHaveBeenCalled();
    expect(props.onSessionReady).not.toHaveBeenCalled();
    fireEvent.change(select, { target: { value: 'prototype' } });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  演示审批流程  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'chat.productStageRelay.startStage' }));
    await waitFor(() => expect(props.onSessionReady).toHaveBeenCalledWith('next-1', true));
    expect(relay).toHaveBeenCalledWith('source-1', expect.objectContaining({
      action: 'switch-stage', selected_stage: 'prototype', expected_state_version: 7,
      request_context: '演示审批流程', idempotency_key: expect.any(String),
    }), expect.any(Object));
  });

  it('carries the latest saved version without inventing a sample preference', async () => {
    const props = mount();
    await screen.findByRole('combobox');
    getState.mockResolvedValue({ data: { result: { ...available, state_version: 8 } } });
    fireEvent.click(screen.getByRole('button', { name: 'chat.productStageRelay.startStage' }));
    await waitFor(() => expect(relay).toHaveBeenCalledTimes(1));
    expect(props.beforeAction).toHaveBeenCalledTimes(1);
    expect(relay.mock.calls[0][1]).toMatchObject({ action: 'continue', selected_stage: 'design', expected_state_version: 8 });
    expect(relay.mock.calls[0][1]).not.toHaveProperty('request_context');
    expect(relay.mock.calls[0][1]).not.toHaveProperty('accept_current_artifact');
  });

  it('accepts the current version only when independently checked', async () => {
    mount();
    const checkbox = await screen.findByRole('checkbox');
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button', { name: 'chat.productStageRelay.startStage' }));
    await waitFor(() => expect(relay).toHaveBeenCalledTimes(1));
    expect(relay.mock.calls[0][1]).toMatchObject({ action: 'continue', accept_current_artifact: true });
  });

  it('does not allow accepting an artifact that still lacks required dependencies', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, can_accept_current_artifact: false } } });
    mount();
    await screen.findByText('chat.productStageRelay.draftVersionTitle:0');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByText('chat.productStageRelay.draftVersionHint')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /chat.productStageRelay.continueReview/ })).not.toBeInTheDocument();
    const continueButton = screen.getByRole('button', { name: 'chat.productStageRelay.startStage' });
    expect(continueButton).toBeEnabled();
    fireEvent.click(continueButton);
    await waitFor(() => expect(relay).toHaveBeenCalledOnce());
    expect(relay.mock.calls[0][1]).not.toHaveProperty('accept_current_artifact');
  });

  it('pauses stage switching until a high-risk decision is explicitly handled', async () => {
    getState.mockResolvedValue({ data: { result: {
      ...available, can_accept_current_artifact: true,
      pending_hard_stops: 1, actions: ['finish'],
    } } });
    mount();
    expect(await screen.findByText('chat.productStageRelay.hardStopTitle:1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.productStageRelay.startStage' })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.productStageRelay.pauseHere' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'chat.productStageRelay.reviewRequired' })).toBeEnabled();
    expect(relay).not.toHaveBeenCalled();
  });

  it('refreshes the remaining confirmation count when the shared project changes', async () => {
    const oldState = { ...available, can_accept_current_artifact: false, project: {
      workspace_id: 'project-1', conversation_id: 'conversation-1', current_session_id: 'source-1', artifacts: [], open_questions: [],
      decisions: [
        { decision_id: 'decision-1', status: 'proposed', confirmation_required: true },
        { decision_id: 'decision-2', status: 'proposed', confirmation_required: true },
      ],
    } };
    const newState = { ...oldState, state_version: 8, project: { ...oldState.project,
      decisions: [
        { decision_id: 'decision-1', status: 'accepted', confirmation_required: true },
        { decision_id: 'decision-2', status: 'proposed', confirmation_required: true },
      ],
    } };
    getState.mockResolvedValueOnce({ data: { result: oldState } }).mockResolvedValue({ data: { result: newState } });
    const props = {
      sessionId: 'source-1', refreshKey: 0, beforeAction: vi.fn().mockResolvedValue(true),
      onBusyChange: vi.fn(), onSessionReady: vi.fn().mockResolvedValue(undefined),
    };
    const { rerender } = render(<ProductStageRelay {...props} />);
    expect(await screen.findByText('chat.productStageRelay.pendingDecisionsTitle:2')).toBeInTheDocument();
    rerender(<ProductStageRelay {...props} refreshKey={1} />);
    expect(await screen.findByText('chat.productStageRelay.pendingDecisionsTitle:1')).toBeInTheDocument();
    expect(getState).toHaveBeenCalledTimes(2);
  });

  it('retries an uncertain response with the identical approval command', async () => {
    relay.mockRejectedValueOnce(new Error('network unavailable'));
    mount();
    const button = await screen.findByRole('button', { name: 'chat.productStageRelay.startStage' });
    fireEvent.click(button);
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    const first = relay.mock.calls[0][1];
    fireEvent.click(button);
    await waitFor(() => expect(relay).toHaveBeenCalledTimes(2));
    expect(relay.mock.calls[1][1]).toEqual(first);
    expect(getState).toHaveBeenCalledTimes(2);
  });

  it('reloads and creates a fresh command after a definite conflict response', async () => {
    const conflict = Object.assign(new Error('version conflict'), { response: { status: 409 } });
    relay.mockRejectedValueOnce(conflict);
    getState
      .mockResolvedValueOnce({ data: { result: available } })
      .mockResolvedValueOnce({ data: { result: available } })
      .mockResolvedValue({ data: { result: { ...available, state_version: 8 } } });
    mount();
    const button = await screen.findByRole('button', { name: 'chat.productStageRelay.startStage' });
    fireEvent.click(button);
    expect(await screen.findByRole('alert')).toHaveTextContent('version conflict');
    const first = relay.mock.calls[0][1];
    fireEvent.click(button);
    await waitFor(() => expect(relay).toHaveBeenCalledTimes(2));
    expect(relay.mock.calls[1][1]).toMatchObject({ expected_state_version: 8 });
    expect(relay.mock.calls[1][1].idempotency_key).not.toBe(first.idempotency_key);
  });

  it('guards duplicate clicks and does not create a run when finishing', async () => {
    let resolve!: (value: unknown) => void;
    relay.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const props = mount();
    const finish = await screen.findByRole('button', { name: 'chat.productStageRelay.pauseHere' });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(finish);
    fireEvent.click(finish);
    await waitFor(() => expect(relay).toHaveBeenCalledTimes(1));
    expect(relay.mock.calls[0][1]).toMatchObject({ action: 'finish' });
    expect(relay.mock.calls[0][1]).not.toHaveProperty('selected_stage');
    expect(relay.mock.calls[0][1]).not.toHaveProperty('accept_current_artifact');
    resolve({ data: { result: { session_id: 'source-1', status: 'completed' } } });
    await screen.findByText('chat.productStageRelay.finished');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(props.onSessionReady).not.toHaveBeenCalled();
    expect(screen.getByText('chat.productStageRelay.savedHint')).toBeInTheDocument();
  });

  it('opens an existing successor without granting a second start', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, can_relay: false, next_session_id: 'next-1' } } });
    const props = mount();
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productStageRelay.openPrepared' }));
    await waitFor(() => expect(props.onSessionReady).toHaveBeenCalledWith('next-1', false));
    expect(relay).not.toHaveBeenCalled();
  });

  it('does not relay if saving the current artifact fails', async () => {
    const props = mount();
    props.beforeAction.mockResolvedValue(false);
    fireEvent.click(await screen.findByRole('button', { name: 'chat.productStageRelay.startStage' }));
    await waitFor(() => expect(props.onBusyChange).toHaveBeenLastCalledWith(false));
    expect(relay).not.toHaveBeenCalled();
    expect(props.onSessionReady).not.toHaveBeenCalled();
  });

  it('does not expose stage mutation when the server has not authorized a relay boundary', async () => {
    getState.mockResolvedValue({ data: { result: { ...available, can_relay: false, actions: [], run_status: 'executing' } } });
    mount();
    await screen.findByText('chat.productStageRelay.unavailable');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(relay).not.toHaveBeenCalled();
  });

  it('preselects the requested shared view but still requires explicit stage confirmation', async () => {
    render(<ProductStageRelay sessionId='source-1' beforeAction={vi.fn().mockResolvedValue(true)}
      onBusyChange={vi.fn()} onSessionReady={vi.fn()} preferredStage={{ stage: 'prototype', requestId: 1 }} />);
    expect(await screen.findByRole('combobox')).toHaveValue('prototype');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(relay).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'chat.productStageRelay.startStage' }));
    await waitFor(() => expect(relay).toHaveBeenCalledOnce());
    expect(relay.mock.calls[0][1]).toMatchObject({ selected_stage: 'prototype', action: 'switch-stage' });
  });
});
