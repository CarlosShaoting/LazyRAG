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
	paths, err := filepath.Glob(filepath.Join(root, "docs", "plan", "plugin", "contracts", "v1", "golden", "*.json"))
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 8 {
		t.Fatalf("expected 8 golden scenarios, got %d", len(paths))
	}
	for _, path := range paths {
		fixture, err := ReadGolden(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if len(fixture.Events) == 0 {
			t.Fatalf("%s has no durable events", path)
		}
	}
}
