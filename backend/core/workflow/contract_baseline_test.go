package plugin

import (
	"path/filepath"
	"runtime"
	"testing"

	workflowcontracts "lazymind/core/workflow/contracts"
)

// This test intentionally lives in the production Runtime package: changes to
// legacy transition/projection behavior must keep the captured v1 stream
// replayable, or explicitly version the public contract first.
func TestLegacyRuntimeCapturedWorkflowV1Baseline(t *testing.T) {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate production contract capture")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", ".."))
	if err := workflowcontracts.ValidateCapturedBaseline(root); err != nil {
		t.Fatal(err)
	}
}
