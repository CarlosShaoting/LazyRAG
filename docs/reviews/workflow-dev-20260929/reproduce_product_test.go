package store

import (
	"encoding/json"
	"testing"
	"time"
)

// This exercises the production function called for continue, switch-stage AND finish.
func TestReviewStageActionMustNotAcceptUnseenHighRiskDecision(t *testing.T) {
	workspace := map[string]any{
		"workspace_id": "workspace-1",
		"current_run":  map[string]any{"selected_stage": "design", "hard_stop_policy": "explicit-decision"},
		"decisions": []any{map[string]any{
			"decision_id": "D-1", "title": "跨租户数据共享", "status": "proposed",
			"risk": "irreversible", "hard_gates": []any{"cross_tenant"},
		}},
	}
	manifest, _ := json.Marshal(map[string]any{
		"artifact_id": "artifact-1", "version": "1.0",
		"host_artifact": map[string]any{"slot": "design_document", "content_sha256": "digest"},
	})
	if productPendingHardStops(workspace) != 1 {
		t.Fatal("invalid fixture")
	}
	err := productAutoAcceptDecisions(workspace, []Artifact{{SlotID: "stage_manifest", Validity: "effective", Value: manifest}},
		"session-1", "finish-command", `{"request":{"action":"finish"}}`, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if productPendingHardStops(workspace) != 1 {
		raw, _ := json.Marshal(workspace)
		t.Fatalf("finish silently accepted the high-risk decision: %s", raw)
	}
}
