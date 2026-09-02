import { describe, expect, it } from 'vitest';

import type {
  SlotRevision,
  TabDef,
  WorkflowSessionStep,
} from '@/modules/chat/store/workflowPanel';
import {
  resolveWorkflowTabStepId,
  workflowSlotMatchesTabScope,
} from './workflowTabScope';

const steps = [
  { step_id: 'generate_image' },
  { step_id: 'enhance_image' },
] as WorkflowSessionStep[];

const firstFrame = {
  slot: 'generated_first_frame',
  step_id: 'generate_image',
  selected: true,
} as SlotRevision;

describe('workflow tab artifact scope', () => {
  it('keeps a normal step tab scoped to its producer', () => {
    const tab = {
      id: 'enhance_image',
      label: 'Enhance',
      slots: [],
    } as TabDef;

    expect(resolveWorkflowTabStepId(tab, steps)).toBe('enhance_image');
    expect(workflowSlotMatchesTabScope(tab, steps, firstFrame)).toBe(false);
  });

  it('lets a selected-scope composite join generate inputs with enhance outputs', () => {
    const tab = {
      id: 'enhance_image',
      slot_scope: 'selected',
      label: 'Enhance',
      slots: [],
    } as TabDef;

    expect(resolveWorkflowTabStepId(tab, steps)).toBeUndefined();
    expect(workflowSlotMatchesTabScope(tab, steps, firstFrame)).toBe(true);
    expect(workflowSlotMatchesTabScope(tab, steps, {
      ...firstFrame,
      selected: false,
    })).toBe(false);
  });
});
