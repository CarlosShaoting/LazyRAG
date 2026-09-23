package graphengine

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProductWorkflowHasExactlyTwoBoundRoutersAndAllEntrypoints(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "workflows", "product_solution_delivery")
	workflow, err := os.ReadFile(filepath.Join(root, "workflow.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	state, err := os.ReadFile(filepath.Join(root, "scenario", "state.yml"))
	if err != nil {
		t.Fatal(err)
	}
	compiled := Compile(string(workflow), string(state), "", ProfilePublish)
	if !compiled.Valid {
		t.Fatalf("product workflow: %+v", compiled.Diagnostics)
	}
	count := 0
	for _, node := range compiled.Graph.Nodes {
		if node.Route == "choice" {
			count++
			if node.RouteSelector == nil {
				t.Fatalf("unbound Router: %s", node.ID)
			}
		}
	}
	if count != 2 {
		t.Fatalf("expected two Routers, got %d", count)
	}
	for stage, target := range map[string]string{
		"direction": "build_direction_outline", "competitive": "analyze_competitive_position", "design": "route_design_scope",
		"prd": "build_prd_outline", "prototype": "build_interactive_prototype", "review": "build_review_outline", "handoff": "build_handoff_outline",
	} {
		payload, _ := json.Marshal(map[string]string{"selected_stage": stage})
		decision := DecideRoute(compiled.Graph, "route_product_stage", []MaterialValue{{MaterialID: "routing_record", RevisionID: "route-1", Valid: true, Value: payload}})
		if len(decision.Activated) != 1 || decision.Activated[0] != target || len(decision.Pruned) != 6 {
			t.Fatalf("%s: %+v", stage, decision)
		}
	}
	for _, effort := range []string{"light", "heavy"} {
		payload, _ := json.Marshal(map[string]string{"overall_effort": effort})
		decision := DecideRoute(compiled.Graph, "route_design_scope", []MaterialValue{{MaterialID: "design_routing_record", RevisionID: "design-route-1", Valid: true, Value: payload}})
		if len(decision.Activated) != 1 || decision.Activated[0] != "collect_design_"+effort+"_evidence" {
			t.Fatalf("%s: %+v", effort, decision)
		}
	}
}

const selectorWorkflow = `
id: selector-test
slots:
  - {id: route_record, type: json, cardinality: single}
steps:
  - {id: route}
  - {id: design}
  - {id: prototype}
`

const selectorState = `
transitions:
  __start__: [{to: route}]
  route:
    - {to: design, when: user wants a design}
    - {to: prototype, when: user wants a prototype}
  design: [{to: __end__}]
  prototype: [{to: __end__}]
steps:
  route:
    route: choice
    route_selector:
      material: route_record
      field: selected_stage
      targets: {design: design, prototype: prototype}
    outputs: [{material: route_record}]
  design: {}
  prototype: {}
`

func TestRouteSelectorImmediatelyPrunesUnselectedStage(t *testing.T) {
	compiled := Compile(selectorWorkflow, selectorState, "", ProfilePublish)
	if !compiled.Valid {
		t.Fatalf("compile: %+v", compiled.Diagnostics)
	}
	for _, payload := range []string{
		`{"selected_stage":"prototype"}`,
		`{"data":{"selected_stage":"prototype"}}`,
		`{"value":"{\"selected_stage\":\"prototype\"}"}`,
	} {
		materials := []MaterialValue{{MaterialID: "route_record", RevisionID: "route-v2", Valid: true, Value: json.RawMessage(payload)}}
		decision := DecideRoute(compiled.Graph, "route", materials)
		if len(decision.Activated) != 1 || decision.Activated[0] != "prototype" || len(decision.Pruned) != 1 || decision.Pruned[0] != "design" {
			t.Fatalf("decision must follow the persisted prototype selection: %+v", decision)
		}
		if len(decision.Witnesses) != 1 || decision.Witnesses[0].RevisionID != "route-v2" {
			t.Fatalf("route must retain its exact decision revision: %+v", decision)
		}
		changed := SelectRouteTarget(compiled.Graph, "route", "design", decision)
		if len(changed.Activated) != 1 || changed.Activated[0] != "prototype" {
			t.Fatal("executor must not override the saved Router decision")
		}
		projection := Project(compiled.Graph, RuntimeSnapshot{
			Attempts:  []AttemptFact{{StepID: "route", Status: "succeeded", Validity: "effective"}},
			Materials: materials,
		})
		if projection.Nodes["prototype"].Readiness != "ready" || projection.Nodes["design"].Branch != "pruned" {
			t.Fatalf("only prototype can become ready: %+v", projection.Nodes)
		}
	}
}

func TestRouteSelectorMissingInvalidOrConflictingDecisionsNeverRun(t *testing.T) {
	compiled := Compile(selectorWorkflow, selectorState, "", ProfilePublish)
	for _, payload := range []string{`null`, `{}`, `{"selected_stage":"unknown"}`, `{"selected_stage":7}`, `"not-json"`} {
		materials := []MaterialValue{{MaterialID: "route_record", RevisionID: "r1", Valid: true, Value: json.RawMessage(payload)}}
		if _, _, err := ResolveRouteSelector(compiled.Graph, "route", materials); err == nil {
			t.Fatalf("expected rejection: %s", payload)
		}
		if route := DecideRoute(compiled.Graph, "route", materials); len(route.Activated) != 0 {
			t.Fatalf("invalid decision cannot authorize a branch: %+v", route)
		}
	}
	materials := []MaterialValue{
		{MaterialID: "route_record", RevisionID: "r1", Valid: true, Value: json.RawMessage(`{"selected_stage":"design"}`)},
		{MaterialID: "route_record", RevisionID: "r2", Valid: true, Value: json.RawMessage(`{"selected_stage":"prototype"}`)},
	}
	if _, _, err := ResolveRouteSelector(compiled.Graph, "route", materials); err == nil {
		t.Fatal("conflicting effective revisions must be rejected")
	}
	materials[0].Valid = false
	if target, _, err := ResolveRouteSelector(compiled.Graph, "route", materials); err != nil || target != "prototype" {
		t.Fatalf("rewound stale decision must not override r2: %s %v", target, err)
	}
}

func TestCompileRejectsUnboundOrIncompleteRouteSelector(t *testing.T) {
	for _, state := range []string{
		strings.Replace(selectorState, "route: choice", "route: all", 1),
		strings.Replace(selectorState, "material: route_record\n", "material: missing\n", 1),
		strings.Replace(selectorState, "prototype: prototype}", "prototype: missing}", 1),
		strings.Replace(selectorState, ", prototype: prototype}", "}", 1),
		strings.Replace(selectorState, "field: selected_stage", "field: ''", 1),
		strings.Replace(selectorState, "outputs: [{material: route_record}]", "outputs: [{material: route_record, required: false}]", 1),
	} {
		result := Compile(selectorWorkflow, state, "", ProfilePublish)
		if result.Valid {
			t.Fatalf("unsafe selector must not publish: %s", state)
		}
	}
}
