import type { ProductProjectDecision } from '@/modules/chat/utils/request';

type OpenQuestion = {
  id?: string;
  question_id?: string;
  question?: string;
  title?: string;
  description?: string;
};

type DecisionCopy = { title: string; recommendation: string };

const DECISION_COPY: Record<string, DecisionCopy> = {
  'DES-001': {
    title: '产品中的关键信息如何记录和更新？',
    recommendation: '建议统一记录决定、负责人、截止时间和风险，并保留每次修改的来源与时间。',
  },
  'DES-002': {
    title: '谁可以查看、修改和同步会议内容？',
    recommendation: '建议沿用企业现有的身份和权限设置；敏感内容需要明确同意后再同步，并确保不同组织的数据彼此隔离。',
  },
  'DES-003': {
    title: '页面中的名称和状态是否保持一致？',
    recommendation: '建议统一信息分类、名称和状态说法，让不同页面表达一致。',
  },
  'DES-004': {
    title: '从会议记录到结果同步，流程如何衔接？',
    recommendation: '建议完整覆盖记录、确认、同步、修改和拒绝等环节，并让用户随时看清当前进度。',
  },
  'DES-005': {
    title: '怎样让相关人员看清决定、时间和风险？',
    recommendation: '建议使用清楚、统一的表达，并把重要变化及时展示给负责人和相关人员。',
  },
  'PRD-001': {
    title: '需求文档是否完整沿用已确定的方案？',
    recommendation: '建议把已确定的产品方案完整带入需求文档，新增内容不要覆盖之前已经确认的决定。',
  },
  'PRD-002': {
    title: '需求细节是否足以支持评审和验收？',
    recommendation: '建议补充字段规则、验收条件、空白与异常状态，以及必要的通知文案。',
  },
  'PRD-003': {
    title: '权限、隐私和数据隔离要求是否已经写清？',
    recommendation: '建议在需求文档中明确身份确认、跨部门权限、敏感内容保护、同步前确认和不同组织的数据隔离要求。',
  },
  'PROT-001': {
    title: '敏感决定同步前，是否需要逐条确认？',
    recommendation: '建议每项敏感决定都由用户主动勾选后再同步，并保留确认记录，不提供自动写入的入口。',
  },
  'PROT-002': {
    title: '没有权限的人能看到哪些内容？',
    recommendation: '建议隐藏敏感会议的负责人和决定正文，只保留必要的时间与风险提示，并提供单次申请入口。',
  },
  'PROT-003': {
    title: '不同组织之间的数据是否完全隔离？',
    recommendation: '建议将不同组织的数据隔离设为不可更改的安全边界，不提供申请或绕过入口。',
  },
  'PROT-004': {
    title: '原型中的进度状态是否统一？',
    recommendation: '建议在确认列表、同步队列和记录页面使用同一套中文状态，让用户容易理解当前进度。',
  },
  'REV-001': {
    title: '当前版本是否已经可以进入下一阶段？',
    recommendation: '目前仍有必须先解决的问题，建议保留为草稿，处理完成并重新检查后再继续。',
  },
  'REV-002': {
    title: '评审发现是否已经按重要程度整理？',
    recommendation: '建议每项问题都写清位置、依据、影响和最小修改方式，复验时继续记录处理结果。',
  },
  'REV-003': {
    title: '评审是否只给建议、不直接改动产物？',
    recommendation: '建议评审保持只读，由用户决定是否采纳；评审报告本身仅作为待确认结果。',
  },
};

const QUESTION_COPY: Record<string, string> = {
  'Q-001': '首批需要支持哪些会议来源和项目管理系统？这些系统允许同步哪些内容？',
  'Q-002': '敏感会议的决定是否必须逐条确认后才能同步到其他系统？',
  'DEP-001': '还缺少产品方向说明，补齐后才能完成本阶段检查。',
  'EDIT-REVALIDATE': '该版本在交付后有过修改，内容仍可使用，但正式确认前需要重新检查。',
  'PROT-Q-001': '原型还没有在真实的电脑和手机尺寸上完整体验，交互与页面适配仍需确认。',
  'HTML-001': '原型页面缺少清晰的主标题，补充后需要重新检查。',
  'HITL-DES-002': '身份、权限、隐私和数据隔离规则还未确认，暂时只能保留为草稿。',
  'HITL-PRD-003': '需求文档中的权限、隐私和数据隔离要求还未确认，暂时不能作为正式依据。',
  'HITL-PROT-001': '敏感决定同步前逐条确认的方式还未确定，暂时不能作为正式依据。',
  'HITL-PROT-002': '无权限用户可以看到的内容范围还未确定，暂时不能作为正式依据。',
  'HITL-PROT-003': '不同组织之间的数据隔离规则还未确认，暂时不能作为正式依据。',
  'HITL-REV-001': '当前版本仍有必须先解决的问题，完成处理和复验前暂不进入下一阶段。',
};

const FIELD_VALUE_COPY: Record<string, string> = {
  true: '是',
  false: '否',
  draft: '草稿',
  reviewable: '可评审',
  accepted: '已确认',
  proposed: '待确认',
  missing: '缺失',
  none: '无',
  'manual review': '人工复核',
  'owner only': '仅限负责人',
  payments: '付款相关内容',
};

const GATE_COPY: Record<string, string> = {
  privacy: '敏感内容保护',
  identity: '企业身份确认',
  permission: '访问权限',
  silent_write: '同步前明确确认',
  cross_tenant: '不同组织的数据隔离',
  high_loss_irreversible: '高损失或不可撤销的操作',
};

const LATIN_LETTER = /[A-Za-z]/;
const HAN_CHARACTER = /[\u3400-\u9fff]/;

function rawValue(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (Array.isArray(value)) return value.map(rawValue).filter(Boolean).join('；');
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(rawValue).filter(Boolean).join('；');
  }
  return '';
}

function replaceKnownTerms(value: string): string {
  return value
    .replace(/can_advance\s*=\s*false/gi, '当前暂不能继续')
    .replace(/needs[-_ ]update/gi, '需要更新')
    .replace(/direction[-_ ]brief/gi, '产品方向说明')
    .replace(/cross[-_ ]tenant/gi, '不同组织的数据隔离')
    .replace(/write[-_ ]back/gi, '同步到项目系统')
    .replace(/silent[-_ ]write/gi, '未经确认直接同步')
    .replace(/manual review/gi, '人工复核')
    .replace(/owner only/gi, '仅限负责人')
    .replace(/per[-_ ]item/gi, '逐项')
    .replace(/<h1>/gi, '页面主标题')
    .replace(/\bPRD\b/gi, '需求文档')
    .replace(/\bprototype\b/gi, '交互原型')
    .replace(/\brouter\b/gi, '阶段选择')
    .replace(/\bheavy\b/gi, '深入核验')
    .replace(/\blight\b/gi, '快速梳理')
    .replace(/\bdraft\b/gi, '草稿')
    .replace(/\breviewable\b/gi, '可评审')
    .replace(/\baccepted\b/gi, '已确认')
    .replace(/\bproposed\b/gi, '待确认')
    .replace(/\bmissing\b/gi, '缺失')
    .replace(/\bP0\b/gi, '最高优先级')
    .replace(/\bP1\b/gi, '高优先级')
    .replace(/\bP2\b/gi, '一般优先级')
    .replace(/\bv(?=\d)/gi, '')
    .replace(/\bAI\b/gi, '智能助手')
    .replace(/\bRBAC\b/gi, '分级权限')
    .replace(/\bAPI\b/gi, '接口');
}

function semanticChineseText(value: string): string | null {
  const lower = value.toLowerCase();
  if (lower.includes('behavior') && lower.includes('identity') && lower.includes('privacy')) {
    return DECISION_COPY['DES-002'].recommendation;
  }
  if (lower.includes('domain objects') && lower.includes('lifecycle')) return DECISION_COPY['DES-001'].recommendation;
  if (lower.includes('information architecture') && lower.includes('taxonomy')) return DECISION_COPY['DES-003'].recommendation;
  if (lower.includes('journey') && lower.includes('capture-to-confirm')) return DECISION_COPY['DES-004'].recommendation;
  if (lower.includes('content and communication') && lower.includes('stakeholders')) return DECISION_COPY['DES-005'].recommendation;
  if (lower.includes('meeting sources') && lower.includes('project-management systems')) return QUESTION_COPY['Q-001'];
  if (lower.includes('sensitive meetings') && lower.includes('consent')) return QUESTION_COPY['Q-002'];
  if (lower.includes('desktop') && lower.includes('mobile viewports')) return QUESTION_COPY['PROT-Q-001'];
  if (lower.includes('missing') && lower.includes('direction-brief')) return QUESTION_COPY['DEP-001'];
  return null;
}

/** Keep dynamic workflow copy readable in Chinese, including legacy English records. */
export function presentProductText(value: unknown, fallback: string, chinese: boolean): string {
  const raw = rawValue(value);
  if (!raw) return fallback;
  if (!chinese) return raw;
  const exact = FIELD_VALUE_COPY[raw.toLowerCase()];
  if (exact) return exact;
  const semantic = semanticChineseText(raw);
  if (semantic) return semantic;
  const replaced = replaceKnownTerms(raw)
    .replace(/[“"][^”"]*[A-Za-z][^”"]*[”"]/g, '“这项方案”')
    .replace(/\b(?:DES|PRD|PROT|REV|HITL|DEP|EDIT|HTML)[-_][A-Za-z0-9_-]+\b/gi, '')
    .replace(/\b[A-Za-z][A-Za-z0-9._/-]*\b/g, '')
    .replace(/\s+([，。；：！？])/g, '$1')
    .replace(/[，；：]\s*[，；：]/g, '，')
    .replace(/\(\s*\)|（\s*）|“\s*”/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  return HAN_CHARACTER.test(replaced) && !LATIN_LETTER.test(replaced) ? replaced : fallback;
}

function rawDecisionTitle(decision: ProductProjectDecision): string {
  return decision.decision_question || decision.question || decision.title || decision.summary
    || decision.statement || decision.decision || '';
}

function rawDecisionRecommendation(decision: ProductProjectDecision): string {
  const title = rawDecisionTitle(decision);
  const candidates = [rawValue(decision.value), decision.statement, decision.decision, decision.summary, decision.rationale];
  return candidates.find((value) => typeof value === 'string' && value.trim() && value.trim() !== title)?.trim() || '';
}

export function presentProductDecision(
  decision: ProductProjectDecision,
  index: number,
  chinese: boolean,
): DecisionCopy {
  const id = String(decision.decision_id || decision.id || '').trim().toUpperCase();
  if (chinese && DECISION_COPY[id]) return DECISION_COPY[id];
  const titleFallback = chinese ? `请确认第 ${index + 1} 项方案是否符合预期` : `Decision ${index + 1}`;
  const recommendationFallback = chinese ? '建议确认这项方案是否符合预期，再继续下一步。' : '';
  return {
    title: presentProductText(rawDecisionTitle(decision), titleFallback, chinese),
    recommendation: presentProductText(rawDecisionRecommendation(decision), recommendationFallback, chinese),
  };
}

export function presentProductDecisionScope(decision: ProductProjectDecision, chinese: boolean): string {
  if (!chinese) return rawValue(decision.decision_content);
  const gates = Array.isArray(decision.hard_gates)
    ? Array.from(new Set(decision.hard_gates.map((gate) => GATE_COPY[gate]).filter(Boolean)))
    : [];
  return gates.length ? gates.join('、') : '';
}

export function presentProductQuestion(question: OpenQuestion, index: number, chinese: boolean): string {
  const id = String(question.question_id || question.id || '').trim().toUpperCase();
  if (chinese && QUESTION_COPY[id]) return QUESTION_COPY[id];
  return presentProductText(
    question.question || question.title || question.description,
    chinese ? `第 ${index + 1} 项信息还需要补充。` : `Question ${index + 1}`,
    chinese,
  );
}

/** The same question may be copied into several stage manifests; show it only once. */
export function uniqueProductQuestions<T extends OpenQuestion>(questions: T[]): T[] {
  const result = new Map<string, T>();
  questions.forEach((question, index) => {
    const id = String(question.question_id || question.id || '').trim().toUpperCase();
    const source = rawValue(question.question || question.title || question.description).toLowerCase();
    result.set(id || source || `question-${index}`, question);
  });
  return Array.from(result.values());
}

export function presentProductVersion(version: unknown, chinese: boolean): string {
  const raw = rawValue(version);
  if (!raw) return chinese ? '当前版本' : '';
  if (!chinese) return raw;
  const working = raw.match(/^working-r(\d+)$/i);
  if (working) return `编辑中的第 ${working[1]} 版`;
  const localized = raw.replace(/^v(?=\d)/i, '');
  return LATIN_LETTER.test(localized) ? '当前版本' : localized;
}

export function isChineseProductUI(language: string | undefined, translatedTitle: string): boolean {
  return Boolean(language?.toLowerCase().startsWith('zh') || translatedTitle.startsWith('产品工作区'));
}
