import { describe, expect, it } from 'vitest';
import { presentWorkflowStepLabel, presentWorkflowTabLabel } from './workflowStepPresentation';

describe('workflow rollback step presentation', () => {
  it('shows friendly Chinese names for product workflow steps', () => {
    const labels = [
      'route_product_stage',
      'build_direction_outline',
      'write_direction_document',
      'build_prd_outline',
      'write_prd_document',
      'build_interactive_prototype',
      'finalize_product_delivery',
    ].map((stepId, index) => presentWorkflowStepLabel(
      stepId,
      'product_solution_delivery',
      undefined,
      index,
      true,
    ));

    expect(labels).toEqual([
      '选择产品阶段',
      '生成产品方向大纲',
      '撰写产品方向文档',
      '生成需求文档大纲',
      '撰写需求文档',
      '制作交互原型',
      '完成产品交付',
    ]);
    expect(labels.join('')).not.toMatch(/[A-Za-z_]/);
  });

  it('uses a Chinese configured label or a safe Chinese fallback', () => {
    expect(presentWorkflowStepLabel('custom_step', 'custom', '准备材料', 0, true)).toBe('准备材料');
    expect(presentWorkflowStepLabel('custom_step', 'custom', 'Collect materials', 2, true)).toBe('已完成步骤 3');
  });

  it('keeps the configured label or step id in a non-Chinese interface', () => {
    expect(presentWorkflowStepLabel('collect', 'custom', 'Collect materials', 0, false)).toBe('Collect materials');
    expect(presentWorkflowStepLabel('collect', 'custom', undefined, 0, false)).toBe('collect');
  });

  it('uses Chinese product workflow tab labels without changing other locales', () => {
    expect(presentWorkflowTabLabel('PRD 大纲', 'product_solution_delivery', true)).toBe('需求文档大纲');
    expect(presentWorkflowTabLabel('PRD', 'product_solution_delivery', true)).toBe('需求文档');
    expect(presentWorkflowTabLabel('PRD', 'product_solution_delivery', false)).toBe('PRD');
  });
});
