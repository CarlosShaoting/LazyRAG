import type { WorkflowUI } from '@/modules/chat/store/workflowPanel';
import type { SlotFooterAction } from './slotEditingContext';

// Presentation only: the reports and their validation still exist in the session.
export function productPresentation(ui: WorkflowUI): WorkflowUI {
  return { ...ui, tabs: ui.tabs?.map(tab => {
    const slots = tab.slots.filter(slot => !slot.id.endsWith('_outline_report'));
    return slots.length === tab.slots.length ? tab : {
      ...tab, slots, layout: 'list' as const, composite_layout: undefined,
    };
  }).filter(tab => tab.slots.length > 0) };
}

// Keep every format and owner callback, including its save/disabled behavior.
export function productDownloadActions(
  actions: Map<string, SlotFooterAction>,
  title: (key: string) => string,
  execute: (action: SlotFooterAction, callback: () => void) => void,
): Map<string, SlotFooterAction> {
  const downloads = [...actions].filter(([, action]) => action.icon === 'download')
    .sort(([a], [b]) => a.localeCompare(b));
  if (downloads.length < 2) return actions;
  const result = new Map(actions);
  downloads.forEach(([key]) => result.delete(key));
  const [, first] = downloads.find(([, action]) => !action.disabled) ?? downloads[0];
  result.set('product:download', {
    ...first, flushBeforeAction: false, selectedMenuKey: undefined,
    disabled: downloads.every(([, action]) => action.disabled),
    onClick: () => execute(first, first.onClick),
    menu: downloads.flatMap(([key, action]) => (action.menu ?? [{ key: 'default', label: action.label, onClick: action.onClick }])
      .map(option => ({ ...option, key: `${key}:${option.key}`,
        label: `${title(key)} · ${typeof option.label === 'string' ? option.label : action.label}`,
        disabled: action.disabled,
        onClick: () => { if (!action.disabled) execute(action, option.onClick); },
      }))),
  });
  return result;
}
