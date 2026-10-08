// Run from backend/core: go run ../../docs/reviews/workflow-dev-20260929/compile_workflows.go
package main

import (
	"fmt"
	"os"
	"path/filepath"

	"lazymind/core/workflow/graphengine"
)

func main() {
	failed := false
	for _, id := range []string{"product_solution_delivery", "ppt-workflow", "image-workflow-v2"} {
		root := filepath.Join("..", "..", "workflows", id)
		workflow, err := os.ReadFile(filepath.Join(root, "workflow.yaml"))
		if err != nil {
			panic(err)
		}
		state, err := os.ReadFile(filepath.Join(root, "scenario", "state.yml"))
		if err != nil {
			panic(err)
		}
		result := graphengine.Compile(string(workflow), string(state), "", graphengine.ProfilePublish)
		fmt.Printf("%s: valid=%v diagnostics=%+v\n", id, result.Valid, result.Diagnostics)
		failed = failed || !result.Valid
	}
	if failed {
		os.Exit(1)
	}
}
