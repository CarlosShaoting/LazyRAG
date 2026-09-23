package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
)

func productRelayFixture(t *testing.T) *Repository {
	t.Helper()
	r := testRepo(t)
	if err := r.db.AutoMigrate(&orm.WorkflowSession{}, &orm.WorkflowSessionStep{}, &orm.Conversation{},
		&orm.WorkflowSlotRevision{}, &orm.WorkflowHumanArtifact{}, &orm.WorkflowResource{}, &orm.WorkflowRevision{},
		&orm.WorkflowRevisionEntry{}, &orm.WorkflowBlob{}, &orm.ChatHistory{}, &orm.UploadSession{}); err != nil {
		t.Fatal(err)
	}
	createTestConversation(t, r, "conversation", "owner")
	now := time.Now().UTC()
	graph := json.RawMessage(`{"nodes":{},"material_producers":{"workspace_seed":{"kind":"external"},"stage_approval":{"kind":"external"},"requested_stage":{"kind":"external"},"upstream_direction":{"kind":"external"}}}`)
	for _, value := range []any{
		&orm.WorkflowResource{ID: "resource", WorkflowID: "product_solution_delivery", WorkflowRef: "builtin:product_solution_delivery", HeadRevisionID: "published", Status: "active", Version: 2},
		&orm.WorkflowRevision{ID: "published", WorkflowResourceID: "resource", RevisionNo: 2, CompiledGraph: graph, GraphHash: "graph", GraphSchemaVersion: "3", CreatedAt: now},
		&orm.WorkflowSession{ID: "source", ConversationID: "conversation", WorkflowID: "product_solution_delivery", WorkflowRevisionID: "old", CreateUserID: "owner", Status: "completed", StateVersion: 9, CreatedAt: now, UpdatedAt: now},
		&orm.WorkflowSlotRevision{ID: "workspace-r1", SessionID: "source", SlotID: "workspace_state", Slot: "workspace_state", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(`{"workspace_id":"stable-project","private_marker":"internal-only","decisions":[{"status":"proposed"}],"current_run":{"selected_stage":"direction","run_status":"awaiting-stage-confirmation"},"artifacts":[{"artifact_id":"old-output","version":"1.0"}]}`), CreatedAt: now},
		&orm.WorkflowSlotRevision{ID: "manifest-r1", SessionID: "source", SlotID: "stage_manifest", Slot: "stage_manifest", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(`{"title":"方向说明","version":"1.0","status":"draft","eligible_next_stages":["design","review"],"private_manifest":"not-visible"}`), CreatedAt: now},
		&orm.WorkflowSlotRevision{ID: "business-r7", SessionID: "source", SlotID: "direction_document", Slot: "direction_document", Revision: 7, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(`"Exact approved file bytes, not a generated summary"`), CreatedAt: now},
	} {
		if err := r.db.Create(value).Error; err != nil {
			t.Fatal(err)
		}
	}
	return r
}

func TestProductRelayPreservesVersionsAndRequiresDistinctUserAction(t *testing.T) {
	r := productRelayFixture(t)
	ctx := context.Background()
	summary, err := r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil {
		t.Fatal(err)
	}
	public, _ := json.Marshal(summary)
	if summary["can_relay"] != true || strings.Contains(string(public), "internal-only") || strings.Contains(string(public), "not-visible") {
		t.Fatalf("bad summary: %s", public)
	}
	req := ProductRelayRequest{Action: "continue", SelectedStage: "design", IdempotencyKey: "relay-one", ExpectedStateVersion: 9}
	response, err := r.RelayProductStage(ctx, "owner", "source", req)
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	_ = json.Unmarshal(response, &result)
	nextID := result["session_id"].(string)
	var next, source orm.WorkflowSession
	r.db.First(&next, "id = ?", nextID)
	r.db.First(&source, "id = ?", "source")
	if next.WorkflowRevisionID != "published" || source.WorkflowRevisionID != "old" || !source.Dismissed || next.Status != "active" {
		t.Fatalf("sessions: next=%+v old=%+v", next, source)
	}
	refreshed, err := r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil || refreshed["can_relay"] != false || refreshed["next_session_id"] != nextID {
		t.Fatalf("source reload must expose the existing successor: %#v %v", refreshed, err)
	}
	var attempts int64
	r.db.Model(&orm.WorkflowSessionStep{}).Count(&attempts)
	if attempts != 0 {
		t.Fatal("relay automatically ran a stage")
	}
	inputs, err := r.ListInputBindings(ctx, "owner", nextID)
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]InputResource{}
	for _, input := range inputs {
		resource, err := r.GetInputResource(ctx, "owner", input.ResourceID)
		if err != nil {
			t.Fatal(err)
		}
		seen[input.MaterialID] = resource
	}
	if string(seen["upstream_direction"].Content) != "Exact approved file bytes, not a generated summary" {
		t.Fatalf("bytes changed: %s", seen["upstream_direction"].Content)
	}
	seed := productObject(seen["workspace_seed"].Content)
	if seed["workspace_id"] != "stable-project" || seed["current_run"].(map[string]any)["run_status"] != "routing" {
		t.Fatalf("lost Workspace: %#v", seed)
	}
	lineage := seed["host_artifact_bindings"].([]any)[0].(map[string]any)
	if lineage["revision_id"] != "business-r7" || lineage["revision"] != float64(7) {
		t.Fatalf("lost exact revision: %#v", lineage)
	}
	approval := productObject(seen["stage_approval"].Content)
	if approval["reference"] != "workflow-command:relay-one" || approval["source"] != "user-interface" || approval["approved_by"] != "owner" {
		t.Fatalf("missing sourced approval: %#v", approval)
	}
	if seed["decisions"].([]any)[0].(map[string]any)["status"] != "proposed" {
		t.Fatal("continue fabricated decision acceptance")
	}
	replay, err := r.RelayProductStage(ctx, "owner", "source", req)
	if err != nil || string(replay) != string(response) {
		t.Fatalf("replay changed: %s %v", replay, err)
	}
	req.SelectedStage = "review"
	if _, err := r.RelayProductStage(ctx, "owner", "source", req); !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("changed payload should conflict: %v", err)
	}
	var old orm.WorkflowSlotRevision
	r.db.First(&old, "id = ?", "business-r7")
	if !old.Selected || old.Revision != 7 {
		t.Fatal("source artifact mutated")
	}
}

func TestProductRelayReadsNativeDataCaptionArtifacts(t *testing.T) {
	r := productRelayFixture(t)
	for _, id := range []string{"workspace-r1", "manifest-r1"} {
		var revision orm.WorkflowSlotRevision
		if err := r.db.First(&revision, "id = ?", id).Error; err != nil {
			t.Fatal(err)
		}
		wrapped, _ := json.Marshal(map[string]any{"data": json.RawMessage(revision.ContentSnapshot), "caption": "内部状态"})
		if err := r.db.Model(&revision).Update("content_snapshot", wrapped).Error; err != nil {
			t.Fatal(err)
		}
	}
	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["can_relay"] != true || summary["current_stage"] != "direction" {
		t.Fatalf("native envelope was not decoded: %#v %v", summary, err)
	}
	if len(summary["next_stages"].([]map[string]string)) != 2 {
		t.Fatal("native manifest lost recommended stages")
	}
	if _, err := r.RelayProductStage(context.Background(), "owner", "source", ProductRelayRequest{
		Action: "continue", SelectedStage: "design", IdempotencyKey: "native-relay", ExpectedStateVersion: 9,
	}); err != nil {
		t.Fatal(err)
	}
}

func TestProductRelayCarriesEveryDistinctListMaterial(t *testing.T) {
	r := productRelayFixture(t)
	var revision orm.WorkflowRevision
	if err := r.db.First(&revision, "id = ?", "published").Error; err != nil {
		t.Fatal(err)
	}
	var graph map[string]any
	_ = json.Unmarshal(revision.CompiledGraph, &graph)
	producers := graph["material_producers"].(map[string]any)
	producers["product_materials"] = map[string]any{"kind": "external"}
	graph["material_cardinalities"] = map[string]any{"product_materials": "list"}
	encoded, _ := json.Marshal(graph)
	r.db.Model(&revision).Update("compiled_graph", encoded)
	want := map[string]string{}
	for index, content := range []string{"素材一", "素材二", "素材三"} {
		binding := productRestartInput(t, r, "source", "product_materials", fmt.Sprintf("relay-list-%d", index), []byte(content))
		want[binding.ContentHash] = content
	}
	raw, err := r.RelayProductStage(context.Background(), "owner", "source", ProductRelayRequest{
		Action: "continue", SelectedStage: "design", IdempotencyKey: "relay-list", ExpectedStateVersion: 9,
	})
	if err != nil {
		t.Fatal(err)
	}
	newID := productRestartResult(t, raw)["session_id"].(string)
	inputs, err := r.ListInputBindings(context.Background(), "owner", newID)
	if err != nil {
		t.Fatal(err)
	}
	count := 0
	for _, input := range inputs {
		if input.MaterialID != "product_materials" {
			continue
		}
		count++
		resource, getErr := r.GetInputResource(context.Background(), "owner", input.ResourceID)
		if getErr != nil || string(resource.Content) != want[input.ContentHash] {
			t.Fatalf("relay list item changed: input=%#v resource=%#v err=%v", input, resource, getErr)
		}
	}
	if count != 3 {
		t.Fatalf("relay kept %d/3 product materials: %#v", count, inputs)
	}
}

func TestProductRelayRejectsUnsafeOrUnapprovedTransitions(t *testing.T) {
	for _, test := range []struct {
		name, owner, action, stage string
		version                    int64
		setup                      func(*Repository)
	}{
		{"wrong-owner", "other", "continue", "design", 9, nil},
		{"stale-version", "owner", "continue", "design", 8, nil},
		{"unrecommended-continue", "owner", "continue", "handoff", 9, nil},
		{"unsupported-stage", "owner", "switch-stage", "bad", 9, nil},
		{"unfinished", "owner", "continue", "design", 9, func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = 'source'").Update("status", "waiting")
		}},
		{"missing-workspace", "owner", "continue", "design", 9, func(r *Repository) {
			r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Update("validity", "invalidated")
		}},
		{"other-active", "owner", "continue", "design", 9, func(r *Repository) {
			r.db.Create(&orm.WorkflowSession{ID: "active", ConversationID: "conversation", WorkflowID: "other", CreateUserID: "owner", Status: "active"})
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			r := productRelayFixture(t)
			if test.setup != nil {
				test.setup(r)
			}
			_, err := r.RelayProductStage(context.Background(), test.owner, "source", ProductRelayRequest{Action: test.action, SelectedStage: test.stage, ExpectedStateVersion: test.version, IdempotencyKey: "reject"})
			if err == nil {
				t.Fatal("unsafe relay accepted")
			}
			var count int64
			r.db.Model(&Command{}).Count(&count)
			if count != 0 {
				t.Fatal("rejected request persisted approval")
			}
		})
	}
}

func TestProductRelayFinishAndConcurrentReplay(t *testing.T) {
	r := productRelayFixture(t)
	req := ProductRelayRequest{Action: "finish", ExpectedStateVersion: 9, IdempotencyKey: "finish-once"}
	var wg sync.WaitGroup
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := r.RelayProductStage(context.Background(), "owner", "source", req); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	var sessions, commands int64
	r.db.Model(&orm.WorkflowSession{}).Count(&sessions)
	r.db.Model(&Command{}).Count(&commands)
	if sessions != 1 || commands != 1 {
		t.Fatalf("not idempotent: sessions=%d commands=%d", sessions, commands)
	}
	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["can_relay"] != false || summary["run_status"] != "completed" {
		t.Fatalf("finish: %#v %v", summary, err)
	}
}

func TestProductRelayAcceptanceIsExplicitExactAndDoesNotAcceptDecisions(t *testing.T) {
	r := productRelayFixture(t)
	digest := requestHash([]byte("Exact approved file bytes, not a generated summary"))
	manifest := map[string]any{"artifact_id": "direction-v1", "title": "方向说明", "version": "1.0", "status": "reviewable", "eligible_next_stages": []string{"design"}, "host_artifact": map[string]any{"slot": "direction_document", "source_session_id": "source", "content_sha256": digest}}
	manifestJSON, _ := json.Marshal(manifest)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'manifest-r1'").Update("content_snapshot", manifestJSON)
	workspace := map[string]any{"workspace_id": "stable-project", "current_run": map[string]any{"run_status": "awaiting-stage-confirmation", "selected_stage": "direction"}, "decisions": []any{map[string]any{"status": "proposed", "risk": "high"}}, "artifacts": []any{manifest}}
	workspaceJSON, _ := json.Marshal(workspace)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Update("content_snapshot", workspaceJSON)
	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["can_accept_current_artifact"] != true {
		t.Fatalf("acceptance unavailable: %#v %v", summary, err)
	}
	response, err := r.RelayProductStage(context.Background(), "owner", "source", ProductRelayRequest{Action: "continue", SelectedStage: "design", ExpectedStateVersion: 9, IdempotencyKey: "explicit-accept", AcceptCurrentArtifact: true})
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	json.Unmarshal(response, &result)
	bindings, _ := r.ListInputBindings(context.Background(), "owner", result["session_id"].(string))
	for _, binding := range bindings {
		if binding.MaterialID != "workspace_seed" {
			continue
		}
		resource, _ := r.GetInputResource(context.Background(), "owner", binding.ResourceID)
		seed := productObject(resource.Content)
		artifact := seed["artifacts"].([]any)[0].(map[string]any)
		if artifact["status"] != "accepted" || artifact["host_artifact"].(map[string]any)["revision_id"] != "business-r7" {
			t.Fatalf("wrong acceptance: %#v", artifact)
		}
		if seed["decisions"].([]any)[0].(map[string]any)["status"] != "proposed" {
			t.Fatal("artifact acceptance also accepted risky decisions")
		}
		if len(seed["approvals"].([]any)) != 2 {
			t.Fatal("stage and artifact approvals not distinct")
		}
	}
	old, _ := r.ReadArtifact(context.Background(), "owner", "manifest-r1")
	if productObject(old.Value)["status"] != "reviewable" {
		t.Fatal("historical manifest rewritten")
	}
	var sourceWorkspace orm.WorkflowSlotRevision
	if err := r.db.Where("session_id = 'source' AND slot_id = 'workspace_state' AND selected = true").First(&sourceWorkspace).Error; err != nil {
		t.Fatal(err)
	}
	persisted := productObject(sourceWorkspace.ContentSnapshot)
	persistedArtifact := persisted["artifacts"].([]any)[0].(map[string]any)
	if persistedArtifact["status"] != "accepted" || len(persisted["approvals"].([]any)) != 2 {
		t.Fatalf("source Workspace and successor seed diverged after acceptance: %#v", persisted)
	}
}

func TestProductRelayTransactionFailureRollsBackApprovalAndInputs(t *testing.T) {
	r := productRelayFixture(t)
	if err := r.db.Callback().Create().Before("gorm:create").Register("reject-product-successor", func(tx *gorm.DB) {
		if session, ok := tx.Statement.Dest.(*orm.WorkflowSession); ok && session.ID != "source" {
			tx.AddError(errors.New("simulated successor storage failure"))
		}
	}); err != nil {
		t.Fatal(err)
	}
	_, err := r.RelayProductStage(context.Background(), "owner", "source", ProductRelayRequest{Action: "continue", SelectedStage: "design", ExpectedStateVersion: 9, IdempotencyKey: "rollback"})
	if err == nil {
		t.Fatal("expected transactional failure")
	}
	var source orm.WorkflowSession
	r.db.First(&source, "id = 'source'")
	if source.StateVersion != 9 || source.Dismissed {
		t.Fatal("source changed despite rollback")
	}
	var resources, commands, workspaces int64
	r.db.Model(&InputResource{}).Count(&resources)
	r.db.Model(&Command{}).Count(&commands)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("slot_id = 'workspace_state'").Count(&workspaces)
	if resources != 0 || commands != 0 || workspaces != 1 {
		t.Fatalf("partial transaction: resources=%d commands=%d workspaces=%d", resources, commands, workspaces)
	}
}
