package contracts

import (
	"path/filepath"
	"runtime"
	"testing"
)

func TestGoReadsAllGoldenFixtures(t *testing.T) {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate fixture test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", "..", ".."))
	manifest, err := ReadBaselineManifest(filepath.Join(root, "docs", "plan", "plugin", "contracts", "v1", "baseline-manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	paths, err := filepath.Glob(filepath.Join(root, "docs", "plan", "plugin", "contracts", "v1", "golden", "*.json"))
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != len(manifest.RequiredScenarios)+1 {
		t.Fatalf("expected required scenarios plus handoff wait fixture, got %d", len(paths))
	}
	seen := map[string]bool{}
	for _, path := range paths {
		fixture, err := ReadGolden(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if len(fixture.Events) == 0 {
			t.Fatalf("%s has no durable events", path)
		}
		seen[fixture.Scenario] = true
	}
	for _, scenario := range manifest.RequiredScenarios {
		if !seen[scenario] {
			t.Fatalf("missing required scenario %s", scenario)
		}
	}
}

func TestProductionBindingRejectsMissingSymbol(t *testing.T) {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate fixture test")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", "..", ".."))
	err := requireSymbol(root, "backend/core/workflow/eventloop_test.go", `func\s+TestDefinitelyMissingWorkflowScenario\s*\(`)
	if err == nil {
		t.Fatal("missing production symbol must fail contract binding")
	}
}
