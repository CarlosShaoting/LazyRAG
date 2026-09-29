import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { OrdinaryTaskItem, OrdinaryTaskTimeline } from '../TaskCenter/taskTimeline';
import './ProductTaskProgress.scss';

// Internal product work remains executable but does not become a user-facing step.
const internalSteps = new Set(['route_product_stage', 'build_design_outline', 'finalize_product_delivery']);
export function ProductTaskProgress({ timeline, status, title, label, details }: {
  timeline: OrdinaryTaskTimeline; status: string; title: (item: OrdinaryTaskItem) => string;
  label: (item: OrdinaryTaskItem) => string; details: (item: OrdinaryTaskItem) => ReactNode;
}) {
  const { i18n } = useTranslation();
  const zh = !i18n.language?.startsWith('en');
  const items = timeline.items.filter(item => !internalSteps.has(item.step?.step_id ?? item.ordinary?.workflow_step_id ?? ''));
  return <article className="product-task-progress ordinary-task-card" aria-label={zh ? '产品任务执行记录' : 'Product task history'}>
    <header><strong>{zh ? '产品任务' : 'Product task'}</strong><span>{status}</span></header>
    <p role="status">{zh ? `已完成 ${items.filter(item => item.state === 'complete').length} / ${items.length} 个步骤` : `${items.filter(item => item.state === 'complete').length} / ${items.length} steps completed`}</p>
    {items.length === 0 && <p>{zh ? '暂无可展示的阶段结果。' : 'No stage results yet.'}</p>}
    <ol aria-label={zh ? '累计执行步骤' : 'Accumulated steps'}>
      {items.map(item => <li key={item.id}>
        <details>
          <summary><strong>{title(item)}</strong><span>{label(item)}</span></summary>
          {details(item)}
        </details>
      </li>)}
    </ol>
  </article>;
}
