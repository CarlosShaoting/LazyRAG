import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import { DownOutlined, FileTextOutlined } from '@ant-design/icons';
import Markdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getLocalizedErrorMessage } from '@/components/request';
import { downloadStream } from '@/modules/chat/utils/download';
import {
  WorkflowSessionApi,
  type ProductProjectArtifactContent,
  type ProductProjectDecision,
  type ProductDecisionRequest,
  type ProductMarkdownUpdateRequest,
  type ProductStageId,
  type ProductStageRelayState,
} from '@/modules/chat/utils/request';
import { PRODUCT_STAGE_IDS } from './ProductStageRelay';
import MermaidBlock from '../MarkdownViewer/MermaidBlock';
import { MarkdownArtifactEditor } from './MarkdownArtifactEditor';
import {
  isChineseProductUI,
  presentProductDecision,
  presentProductDecisionScope,
  presentProductQuestion,
  presentProductText,
  presentProductVersion,
  uniqueProductQuestions,
} from './productPresentation';
import './ProductProjectViews.scss';
import '../MarkdownViewer/index.scss';

interface ProductProjectViewsProps {
  sessionId: string;
  refreshKey: string;
  stageRunning: boolean;
  disabled?: boolean;
  beforeProjectMutation: () => Promise<boolean>;
  onPreviewChange: (sessionId: string | null) => void;
  onBusyChange: (busy: boolean) => void;
  onRequestStage?: (stage: ProductStageId) => void;
  onDecisionChanged?: () => void;
}

const ARTIFACT_STATUSES = ['draft', 'reviewable', 'accepted', 'needs-update'];
const LOCAL_RASTER_IMAGE = /^data:image\/(?:png|jpe?g|gif|webp);base64,/i;

function decisionValue(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(decisionValue).filter(Boolean).join('；');
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(decisionValue).filter(Boolean).join('；');
  }
  return '';
}

/** Stable, sibling-unique keys prevent stale workflow bodies during async UI reconciliation. */
export function productWorkflowSectionKeys(sessionId: string) {
  return {
    projectViews: `${sessionId}:project-views`,
    currentStage: `${sessionId}:current-stage`,
    stageRelay: `${sessionId}:stage-relay`,
  } as const;
}

/** Run self-contained prototype interactions without giving generated HTML host access. */
export function productPrototypePreviewDocument(content: string): string {
  const document = new DOMParser().parseFromString(content, 'text/html');
  document.querySelectorAll('base, meta[http-equiv]').forEach((element) => element.remove());
  const policy = document.createElement('meta');
  policy.httpEquiv = 'Content-Security-Policy';
  policy.content = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'";
  document.head.prepend(policy);
  return `<!doctype html>\n${document.documentElement.outerHTML}`;
}

/** Shared-view navigation never unmounts the stage editor or drops its local state. */
export function ProductCurrentStageView({ sessionId, hidden, children }: { sessionId: string; hidden: boolean; children: ReactNode }) {
  return <div className='workflow-panel__body' id={`product-current-work-${sessionId}`}
    hidden={hidden} style={hidden ? { display: 'none' } : undefined}>{children}</div>;
}

/** Business views of one product project. Execution sessions remain an internal detail. */
export function ProductProjectViews({
  sessionId, refreshKey, stageRunning, disabled, beforeProjectMutation, onPreviewChange, onBusyChange, onRequestStage,
  onDecisionChanged,
}: ProductProjectViewsProps) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const [summary, setSummary] = useState<{ sessionId: string; state: ProductStageRelayState } | null>(null);
  const [selected, setSelected] = useState<ProductStageId | null>(null);
  const [selectedFormat, setSelectedFormat] = useState<'html' | 'markdown'>('html');
  const [markdownMode, setMarkdownMode] = useState<'edit' | 'preview'>('edit');
  const [preview, setPreview] = useState<{ sessionId: string; artifact: ProductProjectArtifactContent } | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState('');
  const [previewError, setPreviewError] = useState('');
  const [refreshCount, setRefreshCount] = useState(0);
  const [changingView, setChangingView] = useState(false);
  const changing = useRef(false);
  const operationRef = useRef(0);
  const mounted = useRef(true);
  const decisionCommands = useRef(new Map<string, ProductDecisionRequest>());
  const markdownCommands = useRef(new Map<string, ProductMarkdownUpdateRequest>());
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const state = summary?.sessionId === sessionId ? summary.state : null;
  const project = state?.project;
  const artifact = project?.artifacts.find((item) => item.stage === selected);
  const currentPreview = preview?.sessionId === sessionId && preview.artifact.stage === selected ? preview.artifact : null;
  const chineseUI = isChineseProductUI(i18n?.resolvedLanguage || i18n?.language, t('chat.productProject.title'));

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    setSelected(null);
    setSelectedFormat('html');
    setMarkdownMode('edit');
    setPreview(null);
    setPreviewError('');
    decisionCommands.current.clear();
    markdownCommands.current.clear();
    operationRef.current += 1;
    changing.current = false;
    setChangingView(false);
    onPreviewChange(null);
  }, [sessionId, onPreviewChange]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    WorkflowSessionApi().getProductStageRelay(sessionId, { silentError: true } as never)
      .then((response) => {
        if (cancelled) return;
        const next = response.data.result;
        if (!next || typeof next.supported !== 'boolean') throw new Error(t('chat.productProject.loadFailed'));
        setSummary({ sessionId, state: next });
      })
      .catch((cause) => { if (!cancelled) setError(getLocalizedErrorMessage(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, refreshKey, refreshCount, t]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setPreviewError('');
    if (!selected || !artifact?.available) {
      setPreviewLoading(false);
      return () => { cancelled = true; };
    }
    setPreviewLoading(true);
    WorkflowSessionApi().getProductProjectArtifact(sessionId, selected, { silentError: true } as never, selectedFormat)
      .then((response) => {
        if (cancelled) return;
        const result = response.data.result;
        if (!result || result.stage !== selected || typeof result.content !== 'string') {
          throw new Error(t('chat.productProject.previewFailed'));
        }
        setPreview({ sessionId, artifact: result });
      })
      .catch((cause) => { if (!cancelled) setPreviewError(getLocalizedErrorMessage(cause)); })
      .finally(() => { if (!cancelled) setPreviewLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, selected, selectedFormat, artifact?.available, artifact?.revision_id, artifact?.version, artifact?.stale, refreshCount, t]);

  async function prepareToLeaveMarkdown(): Promise<boolean> {
    if (selectedFormat !== 'markdown' || markdownMode !== 'edit' || !currentPreview?.editable) return true;
    return beforeProjectMutation();
  }

  async function selectView(stage: ProductStageId) {
    const next = stage === state?.current_stage ? null : stage;
    if (disabled || changing.current || next === selected) return;
    if (!await prepareToLeaveMarkdown()) return;
    setPreviewError('');
    if (next !== selected) {
      setSelectedFormat('html');
      setMarkdownMode('edit');
    }
    setSelected(next);
    onPreviewChange(next ? sessionId : null);
  }

  async function switchFormat(format: 'html' | 'markdown') {
    if (blocked || format === selectedFormat) return;
    if (!await prepareToLeaveMarkdown()) return;
    setMarkdownMode('edit');
    setSelectedFormat(format);
  }

  async function switchMarkdownMode(mode: 'edit' | 'preview') {
    if (mode === markdownMode) return;
    if (mode === 'preview' && !await prepareToLeaveMarkdown()) return;
    setMarkdownMode(mode);
  }

  async function saveMarkdown(markdown: string, baseRevision: number) {
    const current = currentPreview;
    if (!selected || !current || current.content_format !== 'markdown' || !current.revision_id || current.revision !== baseRevision) {
      throw new Error(t('chat.productProject.markdownChanged'));
    }
    const fingerprint = JSON.stringify([sessionId, selected, current.revision_id, baseRevision, markdown]);
    let payload = markdownCommands.current.get(fingerprint);
    if (!payload) {
      payload = {
        base_revision_id: current.revision_id,
        base_revision: baseRevision,
        markdown,
        idempotency_key: uuidv4(),
      };
      markdownCommands.current.set(fingerprint, payload);
    }
    try {
      const response = await WorkflowSessionApi().updateProductProjectMarkdown(
        sessionId, selected, payload, { silentError: true } as never,
      );
      const result = response.data.result;
      if (!result || result.session_id !== sessionId || result.stage !== selected || result.markdown !== markdown) {
        throw new Error(t('chat.productProject.markdownSaveFailed'));
      }
      markdownCommands.current.delete(fingerprint);
      setPreview({ sessionId, artifact: {
        ...current,
        content: result.markdown,
        source_session_id: result.session_id,
        revision_id: result.revision_id,
        revision: result.revision,
        slot_id: result.slot_id,
        slot_key: result.slot_id,
        version: `working-r${result.revision}`,
        status: 'draft',
        stale: true,
        editable: true,
        html_sync_required: result.html_sync_required,
      } });
      return { markdown: result.markdown, revision: result.revision };
    } catch (cause) {
      if (cause && typeof cause === 'object' && 'response' in cause) markdownCommands.current.delete(fingerprint);
      throw cause;
    }
  }

  async function confirmDecision(decision: ProductProjectDecision, action: 'accept' | 'defer') {
    const decisionId = decision.decision_id || decision.id;
    if (disabled || loading || changing.current || !project?.can_update_decisions || !decisionId || !decision.decision_hash) return;
    const sourceSession = sessionId;
    changing.current = true;
    const operation = ++operationRef.current;
    setChangingView(true);
    onBusyChange(true);
    setError('');
    let fingerprint = '';
    try {
      if (!await beforeProjectMutation() || !mounted.current || sessionRef.current !== sourceSession) return;
      fingerprint = JSON.stringify([sessionId, decisionId, decision.decision_hash, action]);
      let payload = decisionCommands.current.get(fingerprint);
      if (!payload) {
        const response = await WorkflowSessionApi().getProductStageRelay(sessionId, { silentError: true } as never);
        if (!mounted.current || sessionRef.current !== sourceSession) return;
        const latest = response.data.result;
        setSummary({ sessionId, state: latest });
        const current = latest?.project?.decisions.find((item) => (item.decision_id || item.id) === decisionId);
        if (!latest?.project?.can_update_decisions || current?.decision_hash !== decision.decision_hash || current.status === 'accepted') {
          throw new Error(t('chat.productProject.decisionChanged'));
        }
        payload = {
          action, expected_state_version: latest.state_version,
          expected_decision_hash: decision.decision_hash, idempotency_key: uuidv4(),
        };
        decisionCommands.current.set(fingerprint, payload);
      }
      const response = await WorkflowSessionApi().updateProductDecision(sessionId, decisionId, payload, { silentError: true } as never);
      if (!mounted.current || sessionRef.current !== sourceSession) return;
      const result = response.data.result;
      if (result?.session_id !== sessionId || result.decision_id !== decisionId) throw new Error(t('chat.productProject.decisionFailed'));
      setSummary((previous) => previous?.sessionId === sessionId && previous.state.project ? {
        ...previous, state: { ...previous.state, state_version: result.state_version, project: {
          ...previous.state.project, decisions: previous.state.project.decisions.map((item) => (item.decision_id || item.id) === decisionId
            ? { ...item, status: result.status, deferred: result.deferred } : item),
        } },
      } : previous);
      decisionCommands.current.delete(fingerprint);
      setRefreshCount((value) => value + 1);
      onDecisionChanged?.();
    } catch (cause) {
      // A server response is definitive, so the next click must use the latest
      // project version. Network failures keep the same idempotent command.
      if (fingerprint && cause && typeof cause === 'object' && 'response' in cause) {
        decisionCommands.current.delete(fingerprint);
      }
      if (mounted.current && sessionRef.current === sourceSession) setError(getLocalizedErrorMessage(cause));
    } finally {
      if (operationRef.current === operation) {
        changing.current = false;
        if (mounted.current && sessionRef.current === sourceSession) { setChangingView(false); onBusyChange(false); }
      }
    }
  }

  if (state && !state.supported) return null;
  const decisions = project?.decisions?.filter((item) => item.title || item.summary || item.statement || item.decision || item.decision_question || item.question || item.value !== undefined) ?? [];
  const questions = uniqueProductQuestions(project?.open_questions.filter((item) => item.question || item.title || item.description) ?? []);
  const pendingDecisions = decisions
    .filter((item) => item.status !== 'accepted' && item.confirmation_required && !item.deferred)
    .sort((left, right) => Number(Boolean(left.deferred)) - Number(Boolean(right.deferred)));
  const primaryDecision = pendingDecisions[0];
  const primaryIndex = primaryDecision ? decisions.indexOf(primaryDecision) : -1;
  const primaryCopy = primaryDecision ? presentProductDecision(primaryDecision, Math.max(primaryIndex, 0), chineseUI) : null;
  const blocked = Boolean(disabled || changingView);
  const selectedStatus = artifact?.status && ARTIFACT_STATUSES.includes(artifact.status) ? artifact.status : 'draft';
  const primaryCanAct = Boolean(
    primaryDecision && project?.can_update_decisions && (primaryDecision.decision_id || primaryDecision.id)
    && primaryDecision.decision_hash && primaryDecision.status !== 'accepted',
  );

  return (
    <section id={`product-project-${sessionId}`} className={`product-project${selected ? ' product-project--previewing' : ''}`} aria-label={t('chat.productProject.title')}>
      <div className='product-project__overview'>
        <div className='product-project__heading'>
          <strong>{t('chat.productProject.title')}</strong>
          <button type='button' onClick={async () => {
            if (await prepareToLeaveMarkdown()) setRefreshCount((value) => value + 1);
          }} disabled={loading || blocked}>
            {t('chat.productProject.refresh')}
          </button>
        </div>
        <p>{t('chat.productProject.sharedHint')}</p>
        {stageRunning && <p className='product-project__notice'>{t('chat.productProject.runningHint')}</p>}
        {loading && !state && <p role='status'>{t('chat.productProject.loading')}</p>}
        {error && <p role='alert' className='product-project__error'>{error}</p>}
        <div className='product-project__views' role='tablist' aria-label={t('chat.productProject.views')}>
          {PRODUCT_STAGE_IDS.map((stage) => {
            const item = project?.artifacts.find((candidate) => candidate.stage === stage);
            const status = item?.status && ARTIFACT_STATUSES.includes(item.status) ? item.status : 'draft';
            const current = stage === state?.current_stage;
            const active = selected ? selected === stage : current;
            return (
              <button key={stage} type='button' role='tab' id={`${id}-${stage}`}
                aria-controls={current && !selected ? `product-current-work-${sessionId}` : `${id}-panel`}
                aria-selected={active} disabled={blocked} onClick={() => void selectView(stage)}>
                <span>{t(`chat.productStageRelay.stages.${stage}`)}</span>
                <small>{item ? `${presentProductVersion(item.version, chineseUI)} · ${t(`chat.productStageRelay.artifactStatuses.${status}`)}`
                  : current && stageRunning ? t('chat.productProject.inProgress') : t('chat.productProject.notCreated')}</small>
                {item?.stale && <small className='product-project__notice'>{t('chat.productProject.staleBadge')}</small>}
              </button>
            );
          })}
        </div>
        {primaryDecision && (
          <section className='product-project__attention' aria-label={t('chat.productProject.attentionTitle')}>
            <div className='product-project__attention-heading'>
              <strong>{t('chat.productProject.attentionTitle')}</strong>
              <span>{t('chat.productProject.attentionCount', { count: pendingDecisions.length })}</span>
            </div>
            <div className='product-project__featured-decision'>
              <span className='product-project__decision-icon' aria-hidden='true'><FileTextOutlined /></span>
              <div className='product-project__decision-main'>
                <h4>{primaryCopy?.title}</h4>
                {primaryCopy?.recommendation && <div className='product-project__recommendation'>
                  <strong>{t('chat.productProject.recommendation')}</strong>
                  <p>{primaryCopy.recommendation}</p>
                </div>}
                <p>{t(project?.can_update_decisions ? 'chat.productProject.unconfirmedHint' : 'chat.productProject.confirmAfterFinish')}</p>
                {primaryCanAct && (
                  <div className='product-project__decision-actions'>
                    <button type='button' className='product-project__primary-action' disabled={blocked || loading}
                      onClick={() => void confirmDecision(primaryDecision, 'accept')}>{t('chat.productProject.adoptDecision')}</button>
                    {state?.can_relay && state.current_stage && onRequestStage && (
                      <button type='button' disabled={blocked || loading}
                        onClick={() => onRequestStage(state.current_stage)}>{t('chat.productProject.adjustDecision')}</button>
                    )}
                    <button type='button' className='product-project__text-action' disabled={blocked || loading}
                      onClick={() => void confirmDecision(primaryDecision, 'defer')}>{t('chat.productProject.decideLater')}</button>
                  </div>
                )}
              </div>
            </div>
            <details className='product-project__context'>
              <summary>
                <span>{t('chat.productProject.contextSummary', { decisions: decisions.length, questions: questions.length })}</span>
                <DownOutlined aria-hidden='true' />
              </summary>
              <div className='product-project__context-content'>
                {decisions.length > 0 && <><h4>{t('chat.productProject.decisions')}</h4><ul>{decisions.map((item, index) => (
                  <li className='product-project__decision' key={item.id || item.decision_id || index}>
                    <strong>{presentProductDecision(item, index, chineseUI).title}</strong>
                    {item.status && <small>{t(item.status === 'accepted' ? 'chat.productProject.acceptedDecision' : 'chat.productProject.pendingDecision')}</small>}
                    <p>{presentProductDecision(item, index, chineseUI).recommendation}</p>
                    {item.has_accepted_baseline && decisionValue(item.accepted_baseline_value) && <p><strong>{t('chat.productProject.acceptedBaselineLabel')}</strong>{presentProductText(item.accepted_baseline_value, t('chat.productProject.previousVersionNeedsReview'), chineseUI)}</p>}
                    {presentProductDecisionScope(item, chineseUI) && <p><strong>{t('chat.productProject.scopeLabel')}</strong>{presentProductDecisionScope(item, chineseUI)}</p>}
                    {item.deferred && <p>{t('chat.productProject.decisionDeferred')}</p>}
                  </li>
                ))}</ul></>}
                {questions.length > 0 && <><h4>{t('chat.productProject.questions')}</h4><ul>{questions.map((item, index) => (
                  <li key={item.id || item.question_id || index}>{presentProductQuestion(item, index, chineseUI)}</li>
                ))}</ul></>}
              </div>
            </details>
          </section>
        )}
        {!primaryDecision && (decisions.length > 0 || questions.length > 0) && (
          <details className='product-project__context product-project__context--standalone'>
            <summary><span>{t('chat.productProject.contextSummary', { decisions: decisions.length, questions: questions.length })}</span><DownOutlined aria-hidden='true' /></summary>
            <div className='product-project__context-content'>
              {decisions.length > 0 && <><h4>{t('chat.productProject.decisions')}</h4><ul>{decisions.map((item, index) => (
                <li className='product-project__decision' key={item.id || item.decision_id || index}>
                  <strong>{presentProductDecision(item, index, chineseUI).title}</strong>
                  {item.status && <small>{t(item.status === 'accepted' ? 'chat.productProject.acceptedDecision' : 'chat.productProject.pendingDecision')}</small>}
                  <p>{presentProductDecision(item, index, chineseUI).recommendation}</p>
                  {item.has_accepted_baseline && decisionValue(item.accepted_baseline_value) && <p><strong>{t('chat.productProject.acceptedBaselineLabel')}</strong>{presentProductText(item.accepted_baseline_value, t('chat.productProject.previousVersionNeedsReview'), chineseUI)}</p>}
                  {presentProductDecisionScope(item, chineseUI) && <p><strong>{t('chat.productProject.scopeLabel')}</strong>{presentProductDecisionScope(item, chineseUI)}</p>}
                </li>
              ))}</ul></>}
              {questions.length > 0 && <><h4>{t('chat.productProject.questions')}</h4><ul>{questions.map((item, index) => (
                <li key={item.id || item.question_id || index}>{presentProductQuestion(item, index, chineseUI)}</li>
              ))}</ul></>}
            </div>
          </details>
        )}
      </div>
      {selected && (
        <div id={`${id}-panel`} role='tabpanel' aria-labelledby={`${id}-${selected}`} className='product-project__preview' aria-busy={previewLoading}>
          <h3>{presentProductText(artifact?.title, t(`chat.productStageRelay.stages.${selected}`), chineseUI)}</h3>
          <p>{artifact ? t('chat.productProject.versionSummary', { version: presentProductVersion(artifact.version, chineseUI), status: t(`chat.productStageRelay.artifactStatuses.${selectedStatus}`) }) : t('chat.productProject.emptyHint')}</p>
          {artifact && <p>{selectedFormat === 'markdown' && currentPreview?.editable !== false
            ? t('chat.productProject.editableHint') : t('chat.productProject.readOnlyHint')}</p>}
          {state?.can_relay && onRequestStage && <button type='button' disabled={blocked}
            onClick={() => onRequestStage(selected)}>{t('chat.productProject.selectStage')}</button>}
          {artifact?.stale && <p className='product-project__notice' role='status'>{t('chat.productProject.staleHint')}</p>}
          {artifact && !artifact.available && <p className='product-project__notice'>{t('chat.productProject.unavailable')}</p>}
          {previewLoading && <p role='status'>{t('chat.productProject.previewLoading')}</p>}
          {previewError && <p role='alert' className='product-project__error'>{previewError}</p>}
          {artifact?.available_formats && artifact.available_formats.length > 1 && (
            <div className='product-project__format-switch' role='tablist' aria-label={t('chat.productProject.formatLabel')}>
              <button type='button' role='tab' aria-selected={selectedFormat === 'html'}
                disabled={blocked || selectedFormat === 'html'} onClick={() => void switchFormat('html')}>
                {t('chat.productProject.htmlView')}
              </button>
              <button type='button' role='tab' aria-selected={selectedFormat === 'markdown'}
                disabled={blocked || selectedFormat === 'markdown'} onClick={() => void switchFormat('markdown')}>
                {t('chat.productProject.markdownView')}
              </button>
            </div>
          )}
          {selectedFormat === 'markdown' && currentPreview?.content_format === 'markdown' && currentPreview.editable !== false && (
            <div className='product-project__markdown-mode' role='group' aria-label={t('chat.productProject.markdownModeLabel')}>
              <button type='button' aria-pressed={markdownMode === 'edit'} disabled={blocked}
                onClick={() => void switchMarkdownMode('edit')}>{t('chat.productProject.markdownEdit')}</button>
              <button type='button' aria-pressed={markdownMode === 'preview'} disabled={blocked}
                onClick={() => void switchMarkdownMode('preview')}>{t('chat.productProject.markdownPreview')}</button>
            </div>
          )}
          {currentPreview?.html_sync_required && <p className='product-project__notice' role='status'>{t('chat.productProject.prototypeSyncRequired')}</p>}
          {currentPreview && <button type='button' onClick={() => {
            const format = currentPreview.content_format;
            const extension = format === 'html' ? 'html' : format === 'markdown' ? 'md' : 'txt';
            const mimeType = format === 'html' ? 'text/html' : format === 'markdown' ? 'text/markdown' : 'text/plain';
            const version = (currentPreview.version || 'draft').replace(/[^a-zA-Z0-9.-]/g, '-').slice(0, 24);
            downloadStream(new Blob([currentPreview.content], { type: `${mimeType};charset=utf-8` }), `${selected}-${version}.${extension}`);
          }}>{t('chat.productProject.downloadView')}</button>}
          {currentPreview && (
            currentPreview.content_format === 'html'
              ? <iframe title={t('chat.productProject.prototypeTitle')} className='product-project__prototype' sandbox='allow-scripts'
                referrerPolicy='no-referrer' srcDoc={productPrototypePreviewDocument(currentPreview.content)} />
              : currentPreview.content_format === 'markdown' && selectedFormat === 'markdown' && markdownMode === 'edit' && currentPreview.editable !== false
                ? <div className='product-project__editor'><MarkdownArtifactEditor
                  markdown={currentPreview.content}
                  sourceRevision={currentPreview.revision}
                  editingKey={`product-project:${sessionId}:${selected}:markdown`}
                  onSave={saveMarkdown}
                  onRefresh={() => setRefreshCount((value) => value + 1)}
                  onDownload={() => downloadStream(
                    new Blob([currentPreview.content], { type: 'text/markdown;charset=utf-8' }),
                    `${selected}-${(currentPreview.version || 'draft').replace(/[^a-zA-Z0-9.-]/g, '-').slice(0, 24)}.md`,
                  )}
                /></div>
              : currentPreview.content_format === 'markdown'
                ? <div className='product-project__document'><Markdown remarkPlugins={[remarkGfm]} skipHtml
                  urlTransform={(url) => LOCAL_RASTER_IMAGE.test(url) ? url : defaultUrlTransform(url)}
                  components={{
                    code: ({ className, children, ...props }) => {
                      const code = String(children ?? '').replace(/\n$/, '');
                      return /(?:^|\s)language-mermaid(?:\s|$)/.test(className || '')
                        ? <MermaidBlock code={code} />
                        : <code className={className} {...props}>{children}</code>;
                    },
                    // Merely opening a project view must not send its content through remote image URLs.
                    img: ({ src, alt }) => src && LOCAL_RASTER_IMAGE.test(src)
                      ? <img src={src} alt={alt || ''} /> : <span>{t('chat.productProject.remoteImage', { alt: alt || '' })}</span>,
                    a: ({ href, children }) => href && /^https?:\/\//i.test(href)
                      ? <a href={href} target='_blank' rel='noopener noreferrer'>{children}</a> : <span>{children}</span>,
                  }}>{currentPreview.content}</Markdown></div>
                : <pre className='product-project__text'>{currentPreview.content}</pre>
          )}
        </div>
      )}
      {!selected && previewError && <p role='alert' className='product-project__error'>{previewError}</p>}
    </section>
  );
}
