package store

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"lazymind/core/common/orm"
)

func productDecisionRequest(t *testing.T, r *Repository, action, key string) ProductDecisionRequest {
	t.Helper()
	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil {
		t.Fatal(err)
	}
	project := summary["project"].(map[string]any)
	decisions := project["decisions"].([]map[string]any)
	if project["can_update_decisions"] != true || len(decisions) != 1 || decisions[0]["confirmation_required"] != true {
		t.Fatalf("decision card unavailable: %#v", project)
	}
	return ProductDecisionRequest{Action: action, IdempotencyKey: key, ExpectedStateVersion: summary["state_version"].(int64), ExpectedDecisionHash: decisions[0]["decision_hash"].(string)}
}

func TestProductDecisionAcceptanceExactSnapshotPersistsWithoutQualityPromotion(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	var row orm.WorkflowSlotRevision
	r.db.First(&row, "id = 'workspace-r1'")
	workspace := productObject(row.ContentSnapshot)
	workspace["artifacts"].([]any)[0].(map[string]any)["status"] = "draft"
	workspace["decisions"] = []any{map[string]any{"decision_id": "D1", "status": "proposed", "decision_question": "是否允许跨租户访问？", "value": map[string]any{"allow": false, "message": "禁止 <cross tenant> & 保留审计"}, "risk": "high", "hard_gates": []any{"cross_tenant"}}}
	encoded, _ := json.Marshal(workspace)
	r.db.Model(&row).Update("content_snapshot", encoded)
	req := productDecisionRequest(t, r, "accept", "accept-exact-decision")
	response, err := r.DecideProductDecision(ctx, "owner", "source", "D1", req)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := r.DecideProductDecision(ctx, "owner", "source", "D1", req)
	if err != nil || string(replay) != string(response) {
		t.Fatalf("approval replay changed: %s %v", replay, err)
	}
	_, updated, _, err := r.productRelayState(ctx, "owner", "source")
	if err != nil {
		t.Fatal(err)
	}
	decision := updated["decisions"].([]any)[0].(map[string]any)
	if decision["status"] != "accepted" || decision["accepted_by"] != "owner" || updated["artifacts"].([]any)[0].(map[string]any)["status"] != "draft" {
		t.Fatalf("decision acceptance fabricated document acceptance: %#v", updated)
	}
	event := updated["approval_events"].([]any)[0].(map[string]any)
	snapshot := event["decision_snapshot_json"].(string)
	if event["decision_hash"] != "sha256:"+requestHash([]byte(snapshot)) || event["decision_hash"] != req.ExpectedDecisionHash || event["artifact_id"] != "direction-v1" || event["version"] != "1.0" || event["workspace_id"] != "stable-project" || event["stage"] != "direction" || event["content_sha256"] == nil {
		t.Fatalf("approval is not bound to exact artifact+decision: %#v", event)
	}
	var decoded map[string]any
	if json.Unmarshal([]byte(snapshot), &decoded) != nil || decoded["decision_question"] != "是否允许跨租户访问？" {
		t.Fatalf("snapshot cannot be validated cross-language: %s", snapshot)
	}
	public, _ := r.ProductRelaySummary(ctx, "owner", "source")
	card := public["project"].(map[string]any)["decisions"].([]map[string]any)[0]
	if card["value"] == nil || card["decision_question"] == nil || card["decision_content"] == nil || card["hard_gates"] == nil {
		t.Fatal("user cannot see signed decision substance")
	}
	next := productRelayTo(t, r, "source", "design", "after-decision", 10)
	seed := productObject(json.RawMessage(productBoundContents(t, r, next)["workspace_seed"]))
	if seed["decisions"].([]any)[0].(map[string]any)["status"] != "accepted" {
		t.Fatal("accepted decision did not reach next same-window stage")
	}
	var conversations, sessions, attempts int64
	r.db.Model(&orm.Conversation{}).Count(&conversations)
	r.db.Model(&orm.WorkflowSession{}).Count(&sessions)
	r.db.Model(&orm.WorkflowSessionStep{}).Count(&attempts)
	if conversations != 1 || sessions != 2 || attempts != 0 {
		t.Fatal("decision confirmation unexpectedly created execution")
	}
}

func TestProductStageRelayRequiresExplicitHardStopDisposition(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	var row orm.WorkflowSlotRevision
	if err := r.db.First(&row, "id = 'workspace-r1'").Error; err != nil {
		t.Fatal(err)
	}
	workspace := productObject(row.ContentSnapshot)
	workspace["current_run"].(map[string]any)["hard_stop_policy"] = "explicit-decision"
	encoded, _ := json.Marshal(workspace)
	if err := r.db.Model(&row).Update("content_snapshot", encoded).Error; err != nil {
		t.Fatal(err)
	}

	summary, err := r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil || summary["pending_hard_stops"] != 1 || summary["can_accept_current_artifact"] != false || len(summary["actions"].([]string)) != 1 || summary["actions"].([]string)[0] != "finish" {
		t.Fatalf("pending risk did not pause stage relay: %#v %v", summary, err)
	}
	_, err = r.RelayProductStage(ctx, "owner", "source", ProductRelayRequest{
		Action: "continue", SelectedStage: "design", IdempotencyKey: "risk-unconfirmed", ExpectedStateVersion: 9,
	})
	if err == nil || err.Error() != "PRODUCT_RISK_CONFIRMATION_REQUIRED" {
		t.Fatalf("unconfirmed risk crossed the stage boundary: %v", err)
	}

	request := productDecisionRequest(t, r, "defer", "risk-deferred")
	if _, err := r.DecideProductDecision(ctx, "owner", "source", "D1", request); err != nil {
		t.Fatal(err)
	}
	summary, err = r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil || summary["pending_hard_stops"] != nil || len(summary["actions"].([]string)) != 3 {
		t.Fatalf("explicit deferral did not release draft relay: %#v %v", summary, err)
	}
	if _, err := r.RelayProductStage(ctx, "owner", "source", ProductRelayRequest{
		Action: "continue", SelectedStage: "design", IdempotencyKey: "risk-after-deferral", ExpectedStateVersion: 10,
	}); err != nil {
		t.Fatal(err)
	}
}

func TestProductDecisionDeferralPreservesAcceptedBaselineAndApprovesOnlyPendingRevision(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	var row orm.WorkflowSlotRevision
	r.db.First(&row, "id = 'workspace-r1'")
	workspace := productObject(row.ContentSnapshot)
	workspace["decisions"] = []any{map[string]any{"decision_id": "D1", "status": "accepted", "value": "old baseline", "accepted_by": "owner", "acceptance_ref": "history:old", "pending_revisions": []any{map[string]any{"decision_id": "D1", "value": "new proposed baseline", "risk": "high", "status": "proposed", "reopens": "D1"}}}}
	encoded, _ := json.Marshal(workspace)
	r.db.Model(&row).Update("content_snapshot", encoded)
	req := productDecisionRequest(t, r, "defer", "defer-proposal")
	if _, err := r.DecideProductDecision(ctx, "owner", "source", "D1", req); err != nil {
		t.Fatal(err)
	}
	_, saved, _, _ := r.productRelayState(ctx, "owner", "source")
	baseline := saved["decisions"].([]any)[0].(map[string]any)
	if baseline["status"] != "accepted" || baseline["value"] != "old baseline" || baseline["pending_revisions"].([]any)[0].(map[string]any)["deferred"] != true {
		t.Fatalf("deferral rewrote an accepted baseline: %#v", baseline)
	}
	accept := productDecisionRequest(t, r, "accept", "accept-proposal")
	if _, err := r.DecideProductDecision(ctx, "owner", "source", "D1", accept); err != nil {
		t.Fatal(err)
	}
	_, saved, _, _ = r.productRelayState(ctx, "owner", "source")
	decision := saved["decisions"].([]any)[0].(map[string]any)
	if decision["status"] != "accepted" || decision["value"] != "new proposed baseline" || decision["pending_revisions"] != nil || len(saved["decision_history"].([]any)) != 1 {
		t.Fatalf("explicit revision acceptance did not preserve history: %#v", saved)
	}
}

func TestProductDecisionRejectsStaleCardsEditedContentAndWrongOwner(t *testing.T) {
	for _, name := range []string{"wrong-owner", "stale-state", "stale-decision", "edited-content", "active-stage"} {
		t.Run(name, func(t *testing.T) {
			r := productProjectFixture(t)
			req := productDecisionRequest(t, r, "accept", "rejected-approval")
			owner, want := "owner", ""
			switch name {
			case "wrong-owner":
				owner = "other-owner"
			case "stale-state":
				req.ExpectedStateVersion, want = 8, "STATE_VERSION_CONFLICT"
			case "stale-decision":
				req.ExpectedDecisionHash, want = "sha256:wrong", "PRODUCT_DECISION_CHANGED"
			case "edited-content":
				value, _ := json.Marshal(map[string]any{"text": "changed after card was displayed"})
				if _, err := r.PatchArtifact(context.Background(), "owner", "business-r7", 7, "text/markdown", value, nil, "edit-before-approve"); err != nil {
					t.Fatal(err)
				}
				// The UI refreshes state after flushing edits; the unchanged decision
				// hash still must not authorize newly edited, unassessed content.
				req.ExpectedStateVersion = 10
				want = "PRODUCT_ARTIFACT_CHANGED"
			case "active-stage":
				r.db.Model(&orm.WorkflowSession{}).Where("id = 'source'").Update("status", "active")
				want = "PRODUCT_STAGE_NOT_READY"
			}
			_, err := r.DecideProductDecision(context.Background(), owner, "source", "D1", req)
			if err == nil || (want != "" && err.Error() != want) || (name == "wrong-owner" && !errors.Is(err, ErrPermissionDenied)) {
				t.Fatalf("unexpected rejection: %v", err)
			}
			var count int64
			r.db.Model(&Command{}).Count(&count)
			if count != 0 {
				t.Fatal("rejected approval was persisted")
			}
		})
	}
}

func TestProductDecisionSurvivesSameSessionAgentRefinalization(t *testing.T) {
	for _, name := range []string{"unchanged", "changed-proposal", "changed-with-copied-acceptance-ref"} {
		t.Run(name, func(t *testing.T) {
			changed := name != "unchanged"
			r := productProjectFixture(t)
			ctx := context.Background()
			var old orm.WorkflowSlotRevision
			r.db.First(&old, "id = 'workspace-r1'")
			original := productObject(old.ContentSnapshot)
			req := productDecisionRequest(t, r, "accept", "durable-human-decision")
			if _, err := r.DecideProductDecision(ctx, "owner", "source", "D1", req); err != nil {
				t.Fatal(err)
			}
			// Simulate an agent finalizer replayed from the old immutable seed.
			if changed {
				original["decisions"].([]any)[0].(map[string]any)["decision"] = "Changed model proposal"
			}
			if name == "changed-with-copied-acceptance-ref" {
				decision := original["decisions"].([]any)[0].(map[string]any)
				decision["status"], decision["accepted_by"], decision["acceptance_ref"] = "accepted", "owner", "workflow-command:durable-human-decision:decision:D1"
			}
			encoded, _ := json.Marshal(original)
			r.db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = 'source' AND slot_id = 'workspace_state'").Update("selected", false)
			if err := r.db.Create(&orm.WorkflowSlotRevision{ID: "agent-refinalized", SessionID: "source", SlotID: "workspace_state", Slot: "workspace_state", Revision: 3, Selected: true, Validity: "effective", ChangeSource: "agent", ContentSnapshot: encoded}).Error; err != nil {
				t.Fatal(err)
			}
			_, recovered, _, err := r.productRelayState(ctx, "owner", "source")
			if err != nil {
				t.Fatal(err)
			}
			baseline := recovered["decisions"].([]any)[0].(map[string]any)
			if baseline["status"] != "accepted" || baseline["decision"] != "目标用户" || len(recovered["approval_events"].([]any)) != 1 {
				t.Fatalf("human decision was lost: %#v", recovered)
			}
			pending, _ := baseline["pending_revisions"].([]any)
			if changed && (len(pending) != 1 || pending[0].(map[string]any)["decision"] != "Changed model proposal") {
				t.Fatalf("new proposal was discarded: %#v", baseline)
			}
			if !changed && len(pending) != 0 {
				t.Fatalf("unchanged content incorrectly reopened: %#v", baseline)
			}
			// Read-side merge must not edit or rewrite the agent's actual revision.
			var untouched orm.WorkflowSlotRevision
			r.db.First(&untouched, "id = 'agent-refinalized'")
			if string(untouched.ContentSnapshot) != string(encoded) {
				t.Fatal("read-side projection wrote user data")
			}
			// Removing the originating command proof prevents promotion from a
			// copied/fabricated event in a human-shaped historical snapshot.
			r.db.Where("command_id = 'durable-human-decision'").Delete(&Command{})
			_, unproven, _, err := r.productRelayState(ctx, "owner", "source")
			if err != nil {
				t.Fatal(err)
			}
			if name != "changed-with-copied-acceptance-ref" && unproven["decisions"].([]any)[0].(map[string]any)["status"] == "accepted" {
				t.Fatal("unproven historical event promoted a decision")
			}
		})
	}
}
