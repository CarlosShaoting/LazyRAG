package runtime

import "testing"

func TestPreparationAndCommandsAreIdempotent(t *testing.T) {
	f := NewFacade()
	p := Preparation{ID: "p1", WorkflowID: "wf", Actor: "u"}
	first, err := f.Prepare("workflow.v1", p)
	if err != nil {
		t.Fatal(err)
	}
	second, _ := f.Prepare("workflow.v1", Preparation{ID: "p1", WorkflowID: "other"})
	if first.ID != second.ID || first.WorkflowID != second.WorkflowID || first.Actor != second.Actor {
		t.Fatal("preparation replay changed result")
	}
	a := f.Command("c1", map[string]any{"state_version": 2})
	b := f.Command("c1", map[string]any{"state_version": 3})
	if a.Result["state_version"] != b.Result["state_version"] {
		t.Fatal("command replay changed result")
	}
}

func TestSnapshotAndEventReplayRebuildProjection(t *testing.T) {
	f := NewFacade()
	f.Append("s", "workflow.snapshot", "s", map[string]any{"status": "running"})
	f.Append("s", "step.patch", "draft", map[string]any{"status": "succeeded"})
	f.Append("s", "workflow.patch", "s", map[string]any{"status": "completed"})
	replayed := f.Replay("s", 1)
	if len(replayed) != 2 || replayed[0].Cursor != 2 || replayed[1].Type != "workflow.patch" {
		t.Fatalf("unexpected replay: %#v", replayed)
	}
}

func TestContractVersionIsChecked(t *testing.T) {
	_, err := NewFacade().Prepare("workflow.v2", Preparation{ID: "p"})
	if err != ErrVersionUnsupported {
		t.Fatalf("unexpected error: %v", err)
	}
}
