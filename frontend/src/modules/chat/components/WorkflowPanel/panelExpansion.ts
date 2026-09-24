import type { WorkflowUI } from '@/modules/chat/store/workflowPanel';

export function parsePersistedPanelExpanded(stored: string | null): boolean | null {
  if (stored === 'true') return true;
  if (stored === 'false') return false;
  return null;
}

export function resolveInitialPanelExpanded(
  persistedChoice: boolean | null,
  defaultMode?: WorkflowUI['default_panel_mode'],
): boolean {
  if (persistedChoice !== null) return persistedChoice;
  return defaultMode === 'expanded';
}
