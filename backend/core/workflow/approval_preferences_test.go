package workflow

import (
	"testing"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/workflow/graphengine"
)

func TestApplyApprovalPreferencesOverridesOnlyStoredSteps(t *testing.T) {
	db := newTestDB(t)
	if err := db.AutoMigrate(&orm.WorkflowApprovalPreference{}); err != nil {
		t.Fatalf("migrate approval preferences: %v", err)
	}
	now := time.Now().UTC()
	if err := db.Create(&orm.WorkflowApprovalPreference{
		UserID: "user-a", WorkflowID: "workflow-a", StepID: "review-a",
		ApprovalRequired: false, CreatedAt: now, UpdatedAt: now,
	}).Error; err != nil {
		t.Fatalf("create approval preference: %v", err)
	}
	projection := graphengine.Projection{Nodes: map[string]graphengine.NodeProjection{
		"review-a": {ID: "review-a", RequiresApproval: true},
		"review-b": {ID: "review-b", RequiresApproval: true},
	}}

	got := applyApprovalPreferences(db.DB, "user-a", "workflow-a", projection)

	if got.Nodes["review-a"].RequiresApproval {
		t.Fatal("stored step should no longer require approval")
	}
	if !got.Nodes["review-b"].RequiresApproval {
		t.Fatal("missing preference must inherit the workflow default")
	}
}

func TestDescendantStepIDsExcludesCurrentAndEnd(t *testing.T) {
	graph := &graphengine.CompiledStateGraph{
		Nodes: map[string]graphengine.CompiledNode{
			"current": {}, "branch-a": {}, "branch-b": {}, "last": {},
		},
		ControlEdges: []graphengine.CompiledEdge{
			{From: "current", To: "branch-a"},
			{From: "current", To: "branch-b"},
			{From: "branch-a", To: "last"},
			{From: "branch-b", To: "last"},
			{From: "last", To: "__end__"},
		},
	}

	got := descendantStepIDs(graph, "current")
	want := []string{"branch-a", "branch-b", "last"}
	if len(got) != len(want) {
		t.Fatalf("descendants = %v, want %v", got, want)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("descendants = %v, want %v", got, want)
		}
	}
}
