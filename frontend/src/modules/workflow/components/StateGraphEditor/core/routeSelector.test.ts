import { describe, expect, it } from 'vitest';
import { parseYaml } from './parser';
import { serializeModel } from './serializer';

describe('deterministic route selector persistence', () => {
  it('preserves both product routers when the visual editor saves label/layout changes', () => {
    const model = parseYaml(`
transitions:
  __start__: [{to: route_product_stage}]
  route_product_stage: [{to: route_design_scope}, {to: prototype}]
  route_design_scope: [{to: light}, {to: heavy}]
steps:
  - id: route_product_stage
    route: choice
    route_selector:
      material: routing_record
      field: selected_stage
      targets: {design: route_design_scope, prototype: prototype}
  - id: route_design_scope
    route: choice
    route_selector:
      material: design_routing_record
      field: effort_route
      targets: {light: light, heavy: heavy}
`)!;
    const originalSelectors = model.nodes.map((node) => node.routeSelector);
    model.nodes[0].label = 'Choose product stage';
    model.layout.route_product_stage = { x: 20, y: 80 };
    const saved = parseYaml(serializeModel(model, true))!;
    expect(saved.nodes.map((node) => node.routeSelector)).toEqual(originalSelectors);
    expect(saved.nodes[0].label).toBe('Choose product stage');
    expect(saved.layout.route_product_stage).toMatchObject({ x: 20, y: 80 });
  });

  it('preserves stop-on-success and failure-only tool policies independently', () => {
    const model = parseYaml(`
steps:
  - id: write_prd_document
    tools: [generate, revise, publish]
    terminal_tools: [publish]
    fail_fast_tools: [generate, revise]
`)!;

    expect(model.nodes[0].terminalTools).toEqual(['publish']);
    expect(model.nodes[0].failFastTools).toEqual(['generate', 'revise']);

    const saved = parseYaml(serializeModel(model))!;
    expect(saved.nodes[0].terminalTools).toEqual(['publish']);
    expect(saved.nodes[0].failFastTools).toEqual(['generate', 'revise']);
  });

  it('preserves the complete execution policy including publisher fallback', () => {
    const model = parseYaml(`
steps:
  - id: collect_evidence
    tools: [publish_unavailable]
    terminal_tools: [publish_unavailable]
    fail_fast_tools: [publish_unavailable]
    execution:
      max_rounds: 6
      timeout_seconds: 150
      hard_repeat_limit: 3
      tool_call_limits: {publish_unavailable: 1}
      publisher_fallback_tool: publish_unavailable
      disable_artifact_reads: true
      compact_summary: true
`)!;
    const expected = {
      max_rounds: 6,
      timeout_seconds: 150,
      hard_repeat_limit: 3,
      tool_call_limits: { publish_unavailable: 1 },
      publisher_fallback_tool: 'publish_unavailable',
      disable_artifact_reads: true,
      compact_summary: true,
    };

    expect(model.nodes[0].executionPolicy).toEqual(expected);
    model.nodes[0].label = 'Collect evidence';
    const saved = parseYaml(serializeModel(model))!;
    expect(saved.nodes[0].executionPolicy).toEqual(expected);
    expect(saved.nodes[0].label).toBe('Collect evidence');
  });
});
