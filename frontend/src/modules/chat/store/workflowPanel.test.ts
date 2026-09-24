import { describe, expect, it } from 'vitest';

import {
  filterWorkflowTabs,
  hydrateWorkflowUI,
  workflowTabAllowsDownload,
} from './workflowPanel';

describe('hydrateWorkflowUI', () => {
  it('hydrates tab slot references with root slot list metadata', () => {
    const ui = hydrateWorkflowUI({
      slots: [
        {
          id: 'material_images',
          label: 'Reference Materials',
          type: 'image',
          cardinality: 'list',
          ordered: true,
        },
      ],
      ui: {
        slots: {
          material_images: { widgetType: 'image-grid', maxHeight: 320 },
        },
        tabs: [{
          id: 'materials',
          label: 'Materials',
          layout: 'grid',
          slots: [{ id: 'material_images', label: '素材图片' }],
        }],
      },
    });

    expect(ui.tabs?.[0].slots[0]).toEqual({
      id: 'material_images',
      label: '素材图片',
      type: 'image',
      cardinality: 'list',
      ordered: true,
      widget: { widgetType: 'image-grid', maxHeight: 320 },
    });
  });

  it('keeps a standalone UI payload usable', () => {
    const ui = { tabs: [{ id: 'result', label: 'Result', slots: [] }] };
    expect(hydrateWorkflowUI({ ui })).toBe(ui);
  });

  it('preserves declarative tab actions while hydrating slots', () => {
    const action = {
      id: 'export_deck',
      type: 'export' as const,
      provider: 'html-presentation',
      inputs: { pages: 'deck_pages' },
      formats: ['pdf'],
      alignment: 'sort_order' as const,
    };
    const ui = hydrateWorkflowUI({
      slots: [{ id: 'deck_pages', type: 'text', cardinality: 'list', ordered: true }],
      ui: {
        slots: { deck_pages: { widgetType: 'html-slide' } },
        tabs: [{ id: 'deck', slots: [{ id: 'deck_pages' }], actions: [action] }],
      },
    });

    expect(ui.tabs?.[0].actions).toEqual([action]);
    expect(ui.tabs?.[0].slots[0].widget?.widgetType).toBe('html-slide');
  });
});

describe('filterWorkflowTabs', () => {
  it('defers conditional tabs until the declared planning material is ready', () => {
    const tabs = [
      { id: 'planning', label: 'Planning', slots: [] },
      {
        id: 'direction', label: 'Direction', slots: [],
        hide_when_material: 'skip_direction',
      },
    ];

    expect(filterWorkflowTabs(tabs, [], 'execution_plan').map((tab) => tab.id)).toEqual([
      'planning',
    ]);

    const slots = [{
      slot_id: 'plan-id',
      revision: 1,
      selected: true,
      slot: 'execution_plan',
      created_at: '2026-08-22T00:00:00Z',
    }];
    expect(filterWorkflowTabs(tabs, slots, 'execution_plan').map((tab) => tab.id)).toEqual([
      'planning', 'direction',
    ]);
  });

  it('hides only tabs whose opt-in material has a selected revision', () => {
    const tabs = [
      { id: 'always', label: 'Always', slots: [] },
      {
        id: 'direction', label: 'Direction', slots: [],
        hide_when_material: 'skip_direction',
      },
      {
        id: 'design', label: 'Design', slots: [],
        hide_when_material: 'skip_design',
      },
    ];
    const slots = [{
      slot_id: 'skip-direction-id',
      revision: 1,
      selected: true,
      slot: 'skip_direction',
      created_at: '2026-08-21T00:00:00Z',
    }];

    expect(filterWorkflowTabs(tabs, slots).map((tab) => tab.id)).toEqual([
      'always', 'design',
    ]);
  });

  it('ignores unselected historical skip revisions', () => {
    const tabs = [{
      id: 'direction', label: 'Direction', slots: [],
      hide_when_material: 'skip_direction',
    }];
    const slots = [{
      slot_id: 'skip-direction-id',
      revision: 1,
      selected: false,
      slot: 'skip_direction',
      created_at: '2026-08-21T00:00:00Z',
    }];

    expect(filterWorkflowTabs(tabs, slots)).toEqual(tabs);
  });

  it('reveals a previously skipped tab when the runtime actually enters it', () => {
    const tabs = [
      { id: 'analysis', step_id: 'analyze', label: '分析', slots: [] },
      {
        id: 'materials', step_id: 'collect', label: '素材收集', slots: [],
        hide_when_material: 'skip_materials',
      },
      { id: 'outline', step_id: 'outline', label: '大纲', slots: [] },
    ];
    const slots = [
      {
        slot_id: 'plan-id', revision: 1, selected: true,
        slot: 'execution_plan', created_at: '2026-09-10T00:00:00Z',
      },
      {
        slot_id: 'skip-id', revision: 1, selected: true,
        slot: 'skip_materials', created_at: '2026-09-10T00:00:00Z',
      },
    ];

    expect(filterWorkflowTabs(
      tabs,
      slots,
      'execution_plan',
      {
        steps: [{
          id: 'attempt-collect', session_id: 'session-1', step_id: 'collect',
          attempt: 2, task_id: 'task-collect', status: 'running', validity: 'effective',
          created_at: '2026-09-10T00:01:00Z', updated_at: '2026-09-10T00:01:30Z',
        }],
      },
    ).map((tab) => tab.id)).toEqual(['analysis', 'materials', 'outline']);
  });

  it('reveals a newly entered tab from the runtime projection before its attempt arrives', () => {
    const tabs = [
      { id: 'analysis', step_id: 'analyze', label: '分析', slots: [] },
      {
        id: 'materials', step_id: 'collect', label: '素材收集', slots: [],
        hide_when_material: 'skip_materials',
      },
      { id: 'outline', step_id: 'outline', label: '大纲', slots: [] },
    ];
    const slots = [{
      slot_id: 'skip-id', revision: 1, selected: true,
      slot: 'skip_materials', created_at: '2026-09-10T00:00:00Z',
    }];

    expect(filterWorkflowTabs(tabs, slots, undefined, {
      projection: { current: ['collect'] },
    }).map((tab) => tab.id)).toEqual(['analysis', 'materials', 'outline']);
  });

  it('keeps a dynamically added completed step while later skipped steps stay hidden', () => {
    const tabs = [
      { id: 'analysis', step_id: 'analyze', label: '分析', slots: [] },
      {
        id: 'materials', step_id: 'collect', label: '素材收集', slots: [],
        hide_when_material: 'skip_materials',
      },
      {
        id: 'background', step_id: 'background', label: '底图生成', slots: [],
        hide_when_material: 'skip_background',
      },
      { id: 'outline', step_id: 'outline', label: '大纲', slots: [] },
    ];
    const slots = [
      {
        slot_id: 'plan-id', revision: 1, selected: true,
        slot: 'execution_plan', created_at: '2026-09-10T00:00:00Z',
      },
      {
        slot_id: 'skip-materials-id', revision: 1, selected: true,
        slot: 'skip_materials', created_at: '2026-09-10T00:00:00Z',
      },
      {
        slot_id: 'skip-background-id', revision: 1, selected: true,
        slot: 'skip_background', created_at: '2026-09-10T00:00:00Z',
      },
    ];

    expect(filterWorkflowTabs(
      tabs,
      slots,
      'execution_plan',
      {
        steps: [{
          id: 'attempt-collect', session_id: 'session-1', step_id: 'collect',
          attempt: 2, task_id: 'task-collect', status: 'succeeded', validity: 'effective',
          created_at: '2026-09-10T00:01:00Z', updated_at: '2026-09-10T00:02:00Z',
        }],
        projection: { past: ['collect'], current: ['outline'] },
      },
    ).map((tab) => tab.id)).toEqual(['analysis', 'materials', 'outline']);
  });

  it('does not revive a conditional tab from stale execution history alone', () => {
    const tabs = [{
      id: 'materials', step_id: 'collect', label: '素材收集', slots: [],
      hide_when_material: 'skip_materials',
    }];
    const slots = [{
      slot_id: 'skip-id', revision: 1, selected: true,
      slot: 'skip_materials', created_at: '2026-09-10T00:00:00Z',
    }];

    expect(filterWorkflowTabs(tabs, slots, undefined, {
      steps: [{
        id: 'attempt-stale', session_id: 'session-1', step_id: 'collect',
        attempt: 1, task_id: 'task-stale', status: 'succeeded', validity: 'stale',
        created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-10T00:01:00Z',
      }],
    })).toEqual([]);
  });
});

describe('workflowTabAllowsDownload', () => {
  it('uses the explicit tab policy before the last-tab fallback', () => {
    const tab = { id: 'delivery', label: 'Delivery', slots: [], allow_download: true };
    expect(workflowTabAllowsDownload(tab, 1, 3)).toBe(true);
    expect(workflowTabAllowsDownload({ ...tab, allow_download: false }, 2, 3)).toBe(false);
  });

  it('keeps downloads on the final tab for existing workflow packages', () => {
    const tab = { id: 'result', label: 'Result', slots: [] };
    expect(workflowTabAllowsDownload(tab, 0, 2)).toBe(false);
    expect(workflowTabAllowsDownload(tab, 1, 2)).toBe(true);
  });
});
