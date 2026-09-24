import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import { CheckCircleFilled, DownOutlined, ExclamationCircleFilled } from '@ant-design/icons';
import { getLocalizedErrorMessage } from '@/components/request';
import {
  WorkflowSessionApi,
  type ProductStageId,
  type ProductStageRelayRequest,
  type ProductStageRelayState,
} from '@/modules/chat/utils/request';
import './ProductStageRelay.scss';

export const PRODUCT_STAGE_IDS: ProductStageId[] = [
  'direction', 'competitive', 'design', 'prd', 'prototype', 'review', 'handoff',
];

export function isProductWorkflow(workflowId: string): boolean {
  return workflowId === 'product_solution_delivery' || workflowId === 'product-solution-delivery';
}

interface ProductStageRelayProps {
  sessionId: string;
  refreshKey?: string | number;
  disabled?: boolean;
  beforeAction: () => Promise<boolean>;
  onBusyChange: (busy: boolean) => void;
  onSessionReady: (sessionId: string, start: boolean) => Promise<void>;
  preferredStage?: { stage: ProductStageId; requestId: number };
}

/** Explicit stage approval. Only the server reads or carries the internal Workspace. */
export function ProductStageRelay({
  sessionId, refreshKey, disabled, beforeAction, onBusyChange, onSessionReady, preferredStage,
}: ProductStageRelayProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<ProductStageRelayState | null>(null);
  const [stage, setStage] = useState<ProductStageId | ''>('');
  const [context, setContext] = useState('');
  const [acceptArtifact, setAcceptArtifact] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const section = useRef<HTMLElement>(null);
  // Reuse the exact command after an uncertain response; never create a second run on retry.
  const command = useRef<{ fingerprint: string; payload: ProductStageRelayRequest } | null>(null);

  const readState = useCallback(async () => {
    const response = await WorkflowSessionApi().getProductStageRelay(sessionId, { silentError: true } as never);
    const next = response.data.result;
    if (!next || typeof next.can_relay !== 'boolean') throw new Error(t('chat.productStageRelay.loadFailed'));
    return next;
  }, [sessionId, t]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const next = await readState();
      command.current = null;
      setState(next);
      setStage((previous) => previous || next.next_stages?.find((item) => PRODUCT_STAGE_IDS.includes(item.id))?.id || '');
    } catch (cause) {
      setError(getLocalizedErrorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, [readState]);

  useEffect(() => { void refresh(); }, [refresh, refreshKey]);

  useEffect(() => {
    if (!preferredStage || !PRODUCT_STAGE_IDS.includes(preferredStage.stage)) return;
    setStage(preferredStage.stage);
    setAcceptArtifact(false);
    section.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
  }, [preferredStage?.stage, preferredStage?.requestId]);

  async function submit(finish = false) {
    if (inFlight.current || disabled || !state?.can_relay || (!finish && !stage)) return;
    inFlight.current = true;
    setPending(true);
    onBusyChange(true);
    setError('');
    try {
      if (!await beforeAction()) return;
      const fingerprint = JSON.stringify([finish, stage, context.trim(), !finish && acceptArtifact]);
      if (command.current?.fingerprint !== fingerprint) {
        // Saving a document can change the source version. Authorize its latest saved revision.
        const latest = await readState();
        setState(latest);
        if (!latest.can_relay) return;
        if (!finish && acceptArtifact && !latest.can_accept_current_artifact) {
          setAcceptArtifact(false);
          throw new Error(t('chat.productStageRelay.acceptUnavailable'));
        }
        const action = finish ? 'finish'
          : latest.next_stages.some((item) => item.id === stage) ? 'continue' : 'switch-stage';
        if (!latest.actions.includes(action)) throw new Error(t('chat.productStageRelay.unavailable'));
        command.current = {
          fingerprint,
          payload: {
            action,
            ...(finish ? {} : { selected_stage: stage as ProductStageId }),
            idempotency_key: uuidv4(),
            expected_state_version: latest.state_version,
            ...(!finish && context.trim() ? { request_context: context.trim() } : {}),
            ...(!finish && acceptArtifact ? { accept_current_artifact: true } : {}),
          },
        };
      }
      const response = await WorkflowSessionApi().relayProductStage(
        sessionId, command.current.payload, { silentError: true } as never,
      );
      const result = response.data.result;
      if (!result?.session_id) throw new Error(t('chat.productStageRelay.actionFailed'));
      if (finish) {
        setState((previous) => previous ? { ...previous, can_relay: false, run_status: 'completed', actions: [] } : previous);
      } else {
        await onSessionReady(result.session_id, true);
      }
    } catch (cause) {
      const message = getLocalizedErrorMessage(cause);
      // A received error response means this command was handled definitively.
      // Discard its old version and reload before the user tries again. For a
      // network interruption, preserve the exact command for an idempotent retry.
      if (cause && typeof cause === 'object' && 'response' in cause) {
        command.current = null;
        try {
          setState(await readState());
        } catch {
          // Keep the original action error; the visible refresh button remains available.
        }
      }
      setError(message);
    } finally {
      inFlight.current = false;
      setPending(false);
      onBusyChange(false);
    }
  }

  async function openPreparedSession() {
    if (!state?.next_session_id || inFlight.current || disabled) return;
    inFlight.current = true;
    setPending(true);
    onBusyChange(true);
    setError('');
    try {
      await onSessionReady(state.next_session_id, false);
    } catch (cause) {
      setError(getLocalizedErrorMessage(cause));
    } finally {
      inFlight.current = false;
      setPending(false);
      onBusyChange(false);
    }
  }

  if (state && !state.supported) return null;
  const blocked = pending || disabled || loading;
  const finished = state?.run_status === 'completed' && !state.next_session_id;
  const stageLabel = stage ? t(`chat.productStageRelay.stages.${stage}`) : '';
  const recommendedStage = state?.next_stages.find((item) => PRODUCT_STAGE_IDS.includes(item.id))?.id;
  const hasAcceptedArtifact = state?.artifacts?.some((artifact) => artifact.status === 'accepted');
  const currentArtifact = state?.artifacts?.[0];
  const pendingDecisionCount = state?.project?.decisions?.filter(
    (decision) => decision.status !== 'accepted' && decision.confirmation_required && !decision.deferred,
  ).length ?? 0;
  const riskBlocked = (state?.pending_hard_stops ?? 0) > 0;

  function reviewRequiredItems() {
    document.getElementById(`product-project-${sessionId}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }

  return (
    <section ref={section} className='product-stage-relay' aria-label={t('chat.productStageRelay.title')} aria-busy={pending || loading}>
      {state && <div className='product-stage-relay__completion'>
        <CheckCircleFilled aria-hidden='true' />
        <div>
          <div className='product-stage-relay__completion-title'>
            <strong>{t(finished ? 'chat.productStageRelay.finished' : 'chat.productStageRelay.stageCompleted', {
              stage: state?.current_stage ? t(`chat.productStageRelay.stages.${state.current_stage}`) : '',
            })}</strong>
            {currentArtifact && <span>{['draft', 'reviewable', 'accepted', 'needs-update'].includes(currentArtifact.status)
              ? t(`chat.productStageRelay.artifactStatuses.${currentArtifact.status}`) : t('chat.productStageRelay.artifactStatuses.draft')}</span>}
          </div>
          <p>{t('chat.productStageRelay.savedHint')}</p>
          {currentArtifact && <small>{t('chat.productStageRelay.artifactSummary', {
            title: currentArtifact.title, version: currentArtifact.version,
            status: ['draft', 'reviewable', 'accepted', 'needs-update'].includes(currentArtifact.status)
              ? t(`chat.productStageRelay.artifactStatuses.${currentArtifact.status}`) : t('chat.productStageRelay.artifactStatuses.draft'),
          })}</small>}
        </div>
      </div>}
      {loading && <p role='status'>{t('chat.productStageRelay.loading')}</p>}
      {error && <p className='product-stage-relay__error' role='alert'>{error}</p>}
      {state?.can_relay && (
        <>
          {riskBlocked && (
            <div className='product-stage-relay__attention' role='alert'>
              <ExclamationCircleFilled aria-hidden='true' />
              <div>
                <strong>{t('chat.productStageRelay.hardStopTitle', { count: state.pending_hard_stops })}</strong>
                <p>{t('chat.productStageRelay.hardStopHint')}</p>
              </div>
              <button type='button' disabled={blocked} onClick={reviewRequiredItems}>
                {t('chat.productStageRelay.reviewRequired')}
              </button>
            </div>
          )}
          {!riskBlocked && !state.can_accept_current_artifact && !hasAcceptedArtifact && (
            <div className='product-stage-relay__attention'>
              <ExclamationCircleFilled aria-hidden='true' />
              <div>
                <strong>{t(pendingDecisionCount > 0
                  ? 'chat.productStageRelay.pendingDecisionsTitle'
                  : 'chat.productStageRelay.draftVersionTitle', { count: pendingDecisionCount })}</strong>
                <p>{t(pendingDecisionCount > 0
                  ? 'chat.productStageRelay.pendingDecisionsHint'
                  : 'chat.productStageRelay.draftVersionHint')}</p>
              </div>
              {pendingDecisionCount > 0 && (
                <button type='button' disabled={blocked} onClick={reviewRequiredItems}>
                  {t('chat.productStageRelay.continueReview', { count: pendingDecisionCount })}
                </button>
              )}
            </div>
          )}
          {!riskBlocked && state.can_accept_current_artifact && (
            <div className='product-stage-relay__accept-block'>
              <label className='product-stage-relay__accept'>
                <input type='checkbox' checked={acceptArtifact} disabled={blocked}
                  onChange={(event) => setAcceptArtifact(event.target.checked)} />
                <span>{t('chat.productStageRelay.acceptArtifact')}</span>
              </label>
              <p>{t('chat.productStageRelay.acceptHint')}</p>
            </div>
          )}
          <label className='product-stage-relay__field'>
            <span>{t('chat.productStageRelay.stageLabel')}</span>
            <select value={stage} onChange={(event) => setStage(event.target.value as ProductStageId)} disabled={blocked}>
              <option value='' disabled>{t('chat.productStageRelay.chooseStage')}</option>
              {PRODUCT_STAGE_IDS.map((id) => <option key={id} value={id}>{t(`chat.productStageRelay.stages.${id}`)}
                {id === recommendedStage ? t('chat.productStageRelay.recommendedStage') : ''}</option>)}
            </select>
            {stage && <small>{t(`chat.productStageRelay.stageHints.${stage}`)}</small>}
          </label>
          <details className='product-stage-relay__requirements'>
            <summary><span>{t('chat.productStageRelay.contextLabel')}</span><span>{t('chat.productStageRelay.expandRequirements')} <DownOutlined aria-hidden='true' /></span></summary>
            <textarea value={context} maxLength={8000} rows={3} disabled={blocked}
              aria-label={t('chat.productStageRelay.contextLabel')}
              onChange={(event) => setContext(event.target.value)} placeholder={t('chat.productStageRelay.contextPlaceholder')} />
          </details>
          <div className='product-stage-relay__actions'>
            <button type='button' className='workflow-panel__action-btn workflow-panel__action-btn--primary'
              disabled={blocked || riskBlocked || !stage ||
                !state.actions.some((action) => action === 'continue' || action === 'switch-stage')}
              onClick={() => void submit()}>
              {pending ? t('chat.productStageRelay.submitting') : t('chat.productStageRelay.startStage', { stage: stageLabel })}
            </button>
            <button type='button' className='workflow-panel__action-btn workflow-panel__action-btn--secondary'
              disabled={blocked || !state.actions.includes('finish')} onClick={() => void submit(true)}>
              {t('chat.productStageRelay.pauseHere')}
            </button>
          </div>
        </>
      )}
      {state?.next_session_id && (
        <button type='button' className='workflow-panel__action-btn workflow-panel__action-btn--primary'
          disabled={blocked} onClick={() => void openPreparedSession()}>{t('chat.productStageRelay.openPrepared')}</button>
      )}
      {!loading && !finished && !state?.can_relay && !state?.next_session_id && (
        <p>{t('chat.productStageRelay.unavailable')}</p>
      )}
      {error && <button type='button' className='workflow-panel__action-btn workflow-panel__action-btn--secondary'
        disabled={blocked} onClick={() => void refresh()}>{t('chat.productStageRelay.refresh')}</button>}
    </section>
  );
}
