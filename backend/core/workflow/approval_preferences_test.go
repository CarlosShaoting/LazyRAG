package workflow

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/mux"

	"lazymind/core/common/orm"
	"lazymind/core/store"
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

func TestSetWorkflowApprovalPreferencePersistsForFutureProjections(t *testing.T) {
	db := newTestDB(t)
	if err := db.AutoMigrate(
		&orm.WorkflowApprovalPreference{},
		&orm.WorkflowRevision{},
	); err != nil {
		t.Fatalf("migrate approval preference handler tables: %v", err)
	}
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	graph := &graphengine.CompiledStateGraph{
		SchemaVersion: graphengine.SchemaVersion,
		GraphHash:     "approval-preference-graph",
		StartRoute:    "review",
		Nodes: map[string]graphengine.CompiledNode{
			"review": {ID: "review", Mode: "human"},
			"next":   {ID: "next", Mode: "human"},
		},
		ControlEdges: []graphengine.CompiledEdge{
			{From: "__start__", To: "review"},
			{From: "review", To: "next"},
			{From: "next", To: "__end__"},
		},
	}
	if err := db.Create(&orm.WorkflowRevision{
		ID: "approval-revision", WorkflowResourceID: "approval-resource", RevisionNo: 1,
		CompiledGraph: graph.JSON(), GraphHash: graph.GraphHash,
		GraphSchemaVersion: graph.SchemaVersion, CreatedAt: time.Now().UTC(),
	}).Error; err != nil {
		t.Fatalf("create workflow revision: %v", err)
	}
	if _, err := CreateSession(context.Background(), db.DB, CreateSessionInput{
		SessionID: "approval-session", ConversationID: "approval-conversation",
		WorkflowID: "approval-workflow", WorkflowRevisionID: "approval-revision",
		GraphHash: graph.GraphHash, GraphSchemaVersion: graph.SchemaVersion,
		CreateUserID: "user-a",
	}); err != nil {
		t.Fatalf("create workflow session: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/workflow-sessions/approval-session:approval-preference", strings.NewReader(`{
		"step_id":"review","scope":"step","approval_required":false
	}`))
	req = mux.SetURLVars(req, map[string]string{"session_id": "approval-session"})
	req.Header.Set("X-User-Id", "user-a")
	rec := httptest.NewRecorder()
	SetWorkflowApprovalPreference(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("set approval preference status=%d body=%s", rec.Code, rec.Body.String())
	}

	var stored orm.WorkflowApprovalPreference
	if err := db.Where(
		"user_id = ? AND workflow_id = ? AND step_id = ?",
		"user-a", "approval-workflow", "review",
	).First(&stored).Error; err != nil {
		t.Fatalf("load stored approval preference: %v", err)
	}
	if stored.ApprovalRequired {
		t.Fatal("stored approval preference must permanently disable this checkpoint")
	}

	future := graphengine.Project(graph, graphengine.RuntimeSnapshot{})
	future = applyApprovalPreferences(db.DB, "user-a", "approval-workflow", future)
	if future.Nodes["review"].RequiresApproval {
		t.Fatal("a future projection for the same user and workflow must skip review approval")
	}
	if !future.Nodes["next"].RequiresApproval {
		t.Fatal("step-scoped preference must not disable a different checkpoint")
	}
}
