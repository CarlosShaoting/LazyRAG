package store

import (
	"encoding/json"
	"lazymind/core/common/orm"
	"testing"
	"time"
)

func reviewWorkspace() map[string]any {
	return map[string]any{
		"workspace_id": "workspace",
		"current_run":  map[string]any{"selected_stage": "design", "run_status": "awaiting-stage-confirmation", "hard_stop_policy": "explicit-decision"},
		"decisions":    []any{map[string]any{"decision_id": "D1", "title": "跨租户共享", "value": "share across tenants", "risk": "irreversible", "status": "proposed"}},
	}
}

func TestProductNavigationNeverApprovesDecisions(t *testing.T) {
	for _, tc := range []struct {
		action, stage string
		blocked       bool
	}{
		{"finish", "", false}, {"switch-stage", "design", false},
		{"switch-stage", "prd", true}, {"continue", "prd", true},
	} {
		t.Run(tc.action+tc.stage, func(t *testing.T) {
			workspace := reviewWorkspace()
			before, _ := json.Marshal(workspace)
			err := productRelayDecisionGate(workspace, tc.action, tc.stage)
			if (err != nil) != tc.blocked {
				t.Fatalf("unexpected gate: %v", err)
			}
			after, _ := json.Marshal(workspace)
			if string(before) != string(after) {
				t.Fatal("navigation mutated decisions")
			}
			decision := productCurrentDecisions(workspace)[0]
			decision["deferred"] = true
			if err := productRelayDecisionGate(workspace, tc.action, tc.stage); err != nil {
				t.Fatal(err)
			}
			if decision["status"] != "proposed" {
				t.Fatal("deferral accepted the decision")
			}
		})
	}
}

func seedReviewProduct(t *testing.T) *Repository {
	t.Helper()
	repo := testRepo(t)
	if err := repo.db.AutoMigrate(&orm.WorkflowSlotRevision{}, &orm.WorkflowHumanArtifact{}, &orm.SubAgentArtifact{}); err != nil {
		t.Fatal(err)
	}
	createTestConversation(t, repo, "conversation", "owner")
	now := time.Now().UTC()
	session := orm.WorkflowSession{ID: "session", WorkflowID: "product_solution_delivery", ConversationID: "conversation", Status: "completed", StateVersion: 1, CreateUserID: "owner", CreatedAt: now, UpdatedAt: now}
	if err := repo.db.Create(&session).Error; err != nil {
		t.Fatal(err)
	}
	content := "Product decision content"
	values := map[string]any{
		"workspace_state": reviewWorkspace(),
		"design_document": map[string]any{"text": content},
		"stage_manifest":  map[string]any{"artifact_id": "artifact", "version": "1.0", "stage": "design", "status": "reviewable", "host_artifact": map[string]any{"slot": "design_document", "content_sha256": requestHash([]byte(content))}},
	}
	for slot, value := range values {
		raw, _ := json.Marshal(value)
		row := orm.WorkflowSlotRevision{ID: slot, SessionID: "session", SlotID: slot, Slot: slot, Revision: 1, Selected: true, ContentSnapshot: raw, Validity: "effective", ChangeSource: "human", CreatedAt: now}
		if err := repo.db.Create(&row).Error; err != nil {
			t.Fatal(err)
		}
	}
	return repo
}

func TestProductFinishPersistsProposedDecisionAndIsIdempotent(t *testing.T) {
	repo := seedReviewProduct(t)
	req := ProductRelayRequest{Action: "finish", ExpectedStateVersion: 1, IdempotencyKey: "finish-once"}
	first, err := repo.RelayProductStage(t.Context(), "owner", "session", req)
	if err != nil {
		t.Fatal(err)
	}
	second, err := repo.RelayProductStage(t.Context(), "owner", "session", req)
	if err != nil || string(first) != string(second) {
		t.Fatalf("retry: %s %v", second, err)
	}
	_, workspace, _, err := repo.productRelayState(t.Context(), "owner", "session")
	if err != nil {
		t.Fatal(err)
	}
	decision := productCurrentDecisions(workspace)[0]
	if decision["status"] != "proposed" || decision["accepted_by"] != nil {
		t.Fatalf("implicit approval: %#v", decision)
	}
}

func TestProductDecisionExplicitApprovalChecksHashAndRestoresAfterRefresh(t *testing.T) {
	repo := seedReviewProduct(t)
	_, digest := productDecisionSnapshot(productCurrentDecisions(reviewWorkspace())[0])
	req := ProductDecisionRequest{Action: "accept", ExpectedStateVersion: 1, ExpectedDecisionHash: "sha256:stale", IdempotencyKey: "accept-once"}
	if _, err := repo.DecideProductDecision(t.Context(), "owner", "session", "D1", req); err == nil {
		t.Fatal("accepted stale hash")
	}
	req.ExpectedDecisionHash = digest
	if _, err := repo.DecideProductDecision(t.Context(), "other-user", "session", "D1", req); err == nil {
		t.Fatal("accepted for another owner")
	}
	first, err := repo.DecideProductDecision(t.Context(), "owner", "session", "D1", req)
	if err != nil {
		t.Fatal(err)
	}
	second, err := repo.DecideProductDecision(t.Context(), "owner", "session", "D1", req)
	if err != nil || string(first) != string(second) {
		t.Fatalf("retry: %s %v", second, err)
	}
	_, workspace, _, err := repo.productRelayState(t.Context(), "owner", "session")
	if err != nil {
		t.Fatal(err)
	}
	decision := productCurrentDecisions(workspace)[0]
	if decision["status"] != "accepted" || decision["accepted_by"] != "owner" {
		t.Fatalf("lost explicit approval: %#v", decision)
	}
	// A later proposal retains the accepted baseline, but must be reviewed anew.
	changed := reviewWorkspace()
	productCurrentDecisions(changed)[0]["value"] = "a different proposal"
	if err := repo.restoreProductDecisionEvents(t.Context(), "owner", orm.WorkflowSession{ID: "session"}, changed); err != nil {
		t.Fatal(err)
	}
	candidate := productDecisionCandidate(productCurrentDecisions(changed)[0])
	if candidate["status"] != "proposed" || candidate["value"] != "a different proposal" {
		t.Fatalf("new content was auto-approved: %#v", candidate)
	}
}

func TestProductLegacyAutoApprovalIsReopened(t *testing.T) {
	workspace := reviewWorkspace()
	decision := productCurrentDecisions(workspace)[0]
	decision["status"], decision["accepted_by"], decision["acceptance_ref"] = "accepted", "product-workflow-default", "old-command"
	productReopenAutomaticDecisions(workspace)
	if productPendingHardStops(workspace) != 1 || decision["accepted_by"] != nil {
		t.Fatalf("still trusted auto acceptance: %#v", decision)
	}
}
