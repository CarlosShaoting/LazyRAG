package graphengine

import (
	"encoding/json"
	"fmt"
	"strings"
)

func validateRouteSelectors(graph *CompiledStateGraph) []Diagnostic {
	var diagnostics []Diagnostic
	for id, node := range graph.Nodes {
		selector := node.RouteSelector
		if selector == nil {
			continue
		}
		fail := func(message string) {
			diagnostics = append(diagnostics, nodeDiag("E_ROUTE_SELECTOR_INVALID", "error", "scenario/state.yml.steps."+id+".route_selector", id, message))
		}
		if node.Route != "choice" || strings.TrimSpace(selector.Field) == "" || len(selector.Targets) == 0 {
			fail("route_selector requires route: choice, a nonempty field and targets")
		}
		required := false
		for _, output := range node.RequiredOutputs {
			required = required || output == selector.Material
		}
		if !required || graph.MaterialTypes[selector.Material] != "json" || graph.MaterialCardinalities[selector.Material] != "single" {
			fail("route_selector material must be a required single JSON output of the same Router")
		}
		exits := map[string]bool{}
		for _, edge := range graph.ControlEdges {
			if edge.From == id {
				exits[edge.To] = true
			}
		}
		covered := map[string]bool{}
		for value, target := range selector.Targets {
			if strings.TrimSpace(value) == "" || !exits[target] {
				fail("every selector value must map to a declared outgoing edge")
			}
			covered[target] = true
		}
		for target := range exits {
			if !covered[target] {
				fail("route_selector must cover every outgoing edge")
			}
		}
	}
	return diagnostics
}

// ResolveRouteSelector rejects missing, stale, ambiguous, and unknown decisions.
// It never defaults an invalid product decision to the first outgoing branch.
func ResolveRouteSelector(graph *CompiledStateGraph, from string, materials []MaterialValue) (string, []Witness, error) {
	selector := graph.Nodes[from].RouteSelector
	if selector == nil {
		return "", nil, nil
	}
	var selected *MaterialValue
	for i := range materials {
		candidate := &materials[i]
		if candidate.Valid && candidate.MaterialID == selector.Material {
			if selected != nil && selected.RevisionID != candidate.RevisionID {
				return "", nil, fmt.Errorf("Router %s has multiple selected decision revisions", from)
			}
			selected = candidate
		}
	}
	if selected == nil {
		return "", nil, fmt.Errorf("Router %s has no effective %s decision", from, selector.Material)
	}
	var value any
	if err := json.Unmarshal(selected.Value, &value); err != nil {
		return "", nil, fmt.Errorf("Router %s decision is not valid JSON", from)
	}
	// Host JSON artifacts may be wrapped in value/data/text or a JSON string.
	for i := 0; i < 6; i++ {
		switch current := value.(type) {
		case map[string]any:
			if raw, exists := current[selector.Field]; exists {
				key, isString := raw.(string)
				target := selector.Targets[key]
				if !isString || target == "" {
					return "", nil, fmt.Errorf("Router %s selected an unsupported %s", from, selector.Field)
				}
				return target, []Witness{{MaterialID: selected.MaterialID, RevisionID: selected.RevisionID}}, nil
			}
			var nested any
			for _, key := range []string{"value", "data", "text"} {
				if item, ok := current[key]; ok {
					nested = item
					break
				}
			}
			value = nested
		case string:
			if json.Unmarshal([]byte(current), &value) != nil {
				return "", nil, fmt.Errorf("Router %s decision field %s is missing", from, selector.Field)
			}
		default:
			return "", nil, fmt.Errorf("Router %s decision field %s is missing", from, selector.Field)
		}
	}
	return "", nil, fmt.Errorf("Router %s decision nesting is invalid", from)
}
