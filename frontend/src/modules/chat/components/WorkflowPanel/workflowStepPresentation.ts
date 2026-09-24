const PRODUCT_STEP_LABELS: Record<string, string> = {
  route_product_stage: '选择产品阶段',
  build_direction_outline: '生成产品方向大纲',
  write_direction_document: '撰写产品方向文档',
  analyze_competitive_position: '分析竞品与生态位',
  route_design_scope: '确定产品方案范围',
  collect_design_light_evidence: '快速补充方案依据',
  collect_design_heavy_evidence: '深入补充方案依据',
  build_design_outline: '生成产品方案大纲',
  write_design_document: '撰写产品方案',
  build_prd_outline: '生成需求文档大纲',
  write_prd_document: '撰写需求文档',
  build_interactive_prototype: '制作交互原型',
  build_review_outline: '生成方案评审大纲',
  write_review_document: '撰写方案评审',
  build_handoff_outline: '生成研发交付大纲',
  write_handoff_document: '准备研发交付文档',
  finalize_product_delivery: '完成产品交付',
};

const LATIN_LETTER = /[A-Za-z]/;
const HAN_CHARACTER = /[\u3400-\u9fff]/;

function isProductWorkflow(workflowId: string): boolean {
  return workflowId === 'product_solution_delivery' || workflowId === 'product-solution-delivery';
}

/** Keep internal step ids out of the Chinese rollback controls. */
export function presentWorkflowStepLabel(
  stepId: string,
  workflowId: string,
  configuredLabel: string | undefined,
  index: number,
  chinese: boolean,
): string {
  if (!chinese) return configuredLabel?.trim() || stepId;
  if (isProductWorkflow(workflowId) && PRODUCT_STEP_LABELS[stepId]) {
    return PRODUCT_STEP_LABELS[stepId];
  }

  const label = configuredLabel
    ?.trim()
    .replace(/\bPRD\b/gi, '需求文档')
    .replace(/\bRouter\b/gi, '阶段选择');
  if (label && HAN_CHARACTER.test(label) && !LATIN_LETTER.test(label)) return label;
  return `已完成步骤 ${index + 1}`;
}

/** Product workflow tab labels are business-facing and should not expose English abbreviations. */
export function presentWorkflowTabLabel(
  label: string,
  workflowId: string,
  chinese: boolean,
): string {
  if (!chinese || !isProductWorkflow(workflowId)) return label;
  const localized = label
    .replace(/\bPRD\s*大纲/gi, '需求文档大纲')
    .replace(/\bPRD\b/gi, '需求文档')
    .replace(/\bRouter\b/gi, '阶段选择');
  return LATIN_LETTER.test(localized) ? '当前步骤' : localized;
}
