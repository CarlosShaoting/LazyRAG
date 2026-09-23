import { describe, expect, it } from 'vitest';

import {
  buildChineseDesignRoutingSummary,
  filterWorkflowTabs,
  filterFallbackWorkflowSlots,
  filterWorkflowSlotIdsByConditions,
  hydrateWorkflowUI,
  workflowMaterialEquals,
  workflowTabAllowsDownload,
  type SlotRevision,
} from './workflowPanel';

describe('fallback artifact visibility', () => {
  const slots = ['direction_document', 'workspace_state', 'stage_manifest', 'routing_record', 'direction_task']
    .map((slot_id) => ({ slot_id, selected: true } as SlotRevision));

  it('keeps exposed metadata even when the UI layout is unavailable', () => {
    const ui = hydrateWorkflowUI({ slots: [
      { id: 'direction_document', exposed: true },
      { id: 'workspace_state', exposed: false },
      { id: 'stage_manifest', exposed: false },
    ] });
    expect(ui.exposed_slot_ids).toEqual(['direction_document']);
    expect(filterFallbackWorkflowSlots('product_solution_delivery', slots, ui).map((slot) => slot.slot_id))
      .toEqual(['direction_document']);
  });

  it('fails closed for product internal records when the complete config is missing', () => {
    expect(filterFallbackWorkflowSlots('product_solution_delivery', slots, {}).map((slot) => slot.slot_id))
      .toEqual(['direction_document']);
    expect(filterFallbackWorkflowSlots('product-solution-delivery', slots, {}).map((slot) => slot.slot_id))
      .toEqual(['direction_document']);
  });

  it('honors an empty visibility list and preserves unrelated workflow fallbacks', () => {
    expect(filterFallbackWorkflowSlots('other', slots, { exposed_slot_ids: [] })).toEqual([]);
    expect(filterFallbackWorkflowSlots('other', slots, {})).toBe(slots);
  });
});

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

describe('workflowMaterialEquals', () => {
  it('matches text artifact wrappers case-insensitively', () => {
    const slots = [{
      slot_id: 'effort-id', revision: 1, selected: true,
      slot: 'design_effort_route', created_at: '2026-09-08T00:00:00Z',
      artifact_value: { text: ' Heavy ' },
    }] as SlotRevision[];

    expect(workflowMaterialEquals(slots, 'design_effort_route', 'heavy')).toBe(true);
    expect(workflowMaterialEquals(slots, 'design_effort_route', 'light')).toBe(false);
  });

  it('ignores unselected historical values and fails closed when the material is absent', () => {
    const slots = [{
      slot_id: 'old-effort-id', revision: 1, selected: false,
      slot: 'design_effort_route', created_at: '2026-09-08T00:00:00Z',
      artifact_value: { text: 'light' },
    }] as SlotRevision[];

    expect(workflowMaterialEquals(slots, 'design_effort_route', 'light')).toBe(false);
    expect(workflowMaterialEquals([], 'design_effort_route', 'heavy')).toBe(false);
  });

  it('matches a nested field in a structured routing record', () => {
    const slots = [{
      slot_id: 'routing-record-id', revision: 1, selected: true,
      slot: 'design_routing_record', created_at: '2026-09-08T00:00:00Z',
      artifact_value: { data: { overall_effort: 'heavy' } },
    }] as SlotRevision[];

    expect(workflowMaterialEquals(
      slots, 'design_routing_record', 'heavy', 'data.overall_effort',
    )).toBe(true);
  });

  it('keeps only the evidence slot selected by the Router material', () => {
    const slots = [{
      slot_id: 'effort-id', revision: 1, selected: true,
      slot: 'design_effort_route', created_at: '2026-09-08T00:00:00Z',
      artifact_value: { text: 'heavy' },
    }] as SlotRevision[];
    const conditions = [
      { slot: 'design_light_evidence', material: 'design_effort_route', equals: 'light' },
      { slot: 'design_heavy_evidence', material: 'design_effort_route', equals: 'heavy' },
    ];

    expect(filterWorkflowSlotIdsByConditions([
      'design_routing_summary', 'design_light_evidence', 'design_heavy_evidence',
    ], slots, conditions)).toEqual([
      'design_routing_summary', 'design_heavy_evidence',
    ]);
  });
});

describe('buildChineseDesignRoutingSummary', () => {
  it('renders the structured Router decision entirely in Chinese', () => {
    const summary = buildChineseDesignRoutingSummary({ data: {
      overall_effort: 'heavy',
      product_goal_basis: '企业会议决策助手',
      primary_domains: ['domain_state', 'behavior_policy_trust'],
      decisions: [
        { effort: 'heavy', hard_gates: ['privacy', 'cross_tenant'] },
        { effort: 'heavy', hard_gates: ['permission'] },
      ],
    } });

    expect(summary).toContain('## 产品方案内部路由');
    expect(summary).toContain('研究路径：** 重型');
    expect(summary).toContain('重型 2 项、轻量 0 项');
    expect(summary).toContain('隐私数据、跨租户隔离、权限控制');
    expect(summary).not.toContain('Handoff');
    expect(summary).not.toContain('Design Routing Summary');
  });
});
