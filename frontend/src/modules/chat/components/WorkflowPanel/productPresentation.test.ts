import { describe, expect, it } from 'vitest';
import {
  isChineseProductUI,
  presentProductDecision,
  presentProductDecisionScope,
  presentProductQuestion,
  presentProductText,
  presentProductVersion,
  uniqueProductQuestions,
} from './productPresentation';

describe('product workflow Chinese presentation', () => {
  it('turns the legacy English safety decision into clear Chinese copy', () => {
    const decision = {
      decision_id: 'DES-002',
      value: 'Behavior, policy and trust rules cover identity binding, cross-department permission checks, sensitive-content privacy handling, explicit consent before any write-back to the project system, and cross-tenant isolation.',
      hard_gates: ['privacy', 'identity', 'permission', 'silent_write', 'cross_tenant'],
    };

    const copy = presentProductDecision(decision, 1, true);
    expect(copy.title).toBe('谁可以查看、修改和同步会议内容？');
    expect(copy.recommendation).toContain('敏感内容需要明确同意后再同步');
    expect(`${copy.title}${copy.recommendation}`).not.toMatch(/[A-Za-z]/);
    expect(presentProductDecisionScope(decision, true)).toBe('敏感内容保护、企业身份确认、访问权限、同步前明确确认、不同组织的数据隔离');
  });

  it('never leaks unknown English text into the Chinese card', () => {
    expect(presentProductText('Unmapped model-authored sentence', '这项内容还需要确认。', true))
      .toBe('这项内容还需要确认。');
    expect(presentProductText('对象维持 draft，存在 P0 问题，can_advance=false。', '需要确认。', true))
      .toBe('对象维持 草稿，存在 最高优先级 问题，当前暂不能继续。');
  });

  it('maps and deduplicates repeated questions from several stage summaries', () => {
    const questions = uniqueProductQuestions([
      { question_id: 'Q-001', question: 'Old English wording' },
      { question_id: 'Q-001', question: 'New English wording' },
      { question_id: 'HTML-001', question: 'missing <h1>' },
    ]);
    expect(questions).toHaveLength(2);
    expect(presentProductQuestion(questions[0], 0, true)).toContain('首批需要支持哪些会议来源');
    expect(presentProductQuestion(questions[1], 1, true)).toBe('原型页面缺少清晰的主标题，补充后需要重新检查。');
    expect(questions.map((question, index) => presentProductQuestion(question, index, true)).join(''))
      .not.toMatch(/[A-Za-z]/);
  });

  it('uses Chinese version labels and keeps English locale behavior intact', () => {
    expect(presentProductVersion('working-r3', true)).toBe('编辑中的第 3 版');
    expect(presentProductVersion('v1.2', true)).toBe('1.2');
    expect(presentProductVersion('v1.2', false)).toBe('v1.2');
    expect(isChineseProductUI('zh-CN', 'ignored')).toBe(true);
    expect(isChineseProductUI('en-US', 'Product workspace')).toBe(false);
  });
});
