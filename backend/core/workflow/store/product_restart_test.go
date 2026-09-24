package store

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
	"time"

	"lazymind/core/common/orm"
)

func seedProductRestartGraph(t *testing.T, r *Repository, materials ...string) {
	t.Helper()
	producers := map[string]map[string]string{}
	cardinalities := map[string]string{}
	for _, material := range materials {
		producers[material] = map[string]string{"kind": "external"}
		if material == "product_materials" {
			cardinalities[material] = "list"
		}
	}
	graph, _ := json.Marshal(map[string]any{
		"schema_version": "3", "graph_hash": "graph", "start_route": "all", "material_producers": producers,
		"material_cardinalities": cardinalities,
		"nodes":                  map[string]any{"route_product_stage": map[string]any{"id": "route_product_stage"}},
		"control_edges":          []map[string]string{{"from": "__start__", "to": "route_product_stage"}},
	})
	if err := r.db.Model(&orm.WorkflowRevision{}).Where("id = ?", "published").Update("compiled_graph", graph).Error; err != nil {
		t.Fatal(err)
	}
}

func productRestartInput(t *testing.T, r *Repository, sessionID, material, command string, content []byte) InputBinding {
	t.Helper()
	resource, _, err := r.ImportInputResource(context.Background(), "owner", material+".json", "application/json", "sha256:"+requestHash(content), content)
	if err != nil {
		t.Fatal(err)
	}
	binding := InputBinding{WorkflowSessionID: sessionID, MaterialID: material, ResourceType: "input_resource",
		ResourceID: resource.ID, ResourceRevision: resource.Revision, ContentHash: resource.ContentHash, CreatedByCommandID: command}
	if err := r.BindInput(context.Background(), "owner", binding); err != nil {
		t.Fatal(err)
	}
	var stored InputBinding
	if err := r.db.Where("workflow_session_id = ? AND material_id = ? AND created_by_command_id = ?", sessionID, material, command).First(&stored).Error; err != nil {
		t.Fatal(err)
	}
	return stored
}

func productRestartResult(t *testing.T, raw json.RawMessage) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func TestProductRestartClonesRev14StyleGoalOnLatestWithoutMutatingSource(t *testing.T) {
	r := productRelayFixture(t)
	seedProductRestartGraph(t, r, "product_goal")
	if err := r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Updates(map[string]any{
		"status": "failed", "origin_host": "codex", "origin_ref": "thread-1", "controller_host": "lazymind",
		"intent_context": `{"goal":"keep me"}`, "trigger_history_id": "history-1",
	}).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ?", "source").Update("validity", "invalidated").Error; err != nil {
		t.Fatal(err)
	}
	goal := productRestartInput(t, r, "source", "product_goal", "original-goal", []byte("用户原始目标，逐字保留"))
	historical := beforeProductRestartSession("historical", "conversation", "owner", "completed")
	if err := r.db.Create(&historical).Error; err != nil {
		t.Fatal(err)
	}
	var before orm.WorkflowSession
	r.db.First(&before, "id = ?", "source")

	req := ProductRestartRequest{IdempotencyKey: "restart-goal", ExpectedStateVersion: 9}
	raw, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", req)
	if err != nil {
		t.Fatal(err)
	}
	result := productRestartResult(t, raw)
	newID, _ := result["session_id"].(string)
	if result["source_session_id"] != "source" || result["restarted"] != true || result["status"] != "waiting" || result["state_version"] != float64(1) || newID == "" {
		t.Fatalf("bad restart response: %#v", result)
	}
	if steps, ok := result["ready_steps"].([]any); !ok || len(steps) != 1 || steps[0] != "route_product_stage" {
		t.Fatalf("bad ready steps: %#v", result["ready_steps"])
	}

	var source, next orm.WorkflowSession
	r.db.First(&source, "id = ?", "source")
	r.db.First(&next, "id = ?", newID)
	var dismissedHistory orm.WorkflowSession
	r.db.First(&dismissedHistory, "id = ?", "historical")
	if !dismissedHistory.Dismissed {
		t.Fatal("terminal conversation history remained non-dismissed")
	}
	if !source.Dismissed || next.WorkflowRevisionID != "published" || next.ConversationID != before.ConversationID ||
		next.OriginHost != before.OriginHost || next.OriginRef != before.OriginRef || next.ControllerHost != before.ControllerHost ||
		next.IntentContext != before.IntentContext || next.TriggerHistoryID != before.TriggerHistoryID {
		t.Fatalf("session contract lost: source=%+v next=%+v", source, next)
	}
	source.Dismissed = before.Dismissed
	if !reflect.DeepEqual(source, before) {
		t.Fatalf("source changed beyond dismissed\nbefore=%+v\nafter=%+v", before, source)
	}
	inputs, err := r.ListInputBindings(context.Background(), "owner", newID)
	if err != nil || len(inputs) != 1 || inputs[0].MaterialID != "product_goal" || inputs[0].ResourceID != goal.ResourceID || inputs[0].ContentHash != goal.ContentHash {
		t.Fatalf("goal was not copied exactly: %#v %v", inputs, err)
	}
	if inputs[0].CreatedByCommandID != productRestartBindingCommand(req.IdempotencyKey, "binding:product_goal") {
		t.Fatalf("restart provenance missing: %#v", inputs[0])
	}
	var attempts int64
	r.db.Model(&orm.WorkflowSessionStep{}).Where("session_id = ?", newID).Count(&attempts)
	if attempts != 0 {
		t.Fatal("restart executed a workflow step")
	}
	replay, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", req)
	if err != nil || string(replay) != string(raw) {
		t.Fatalf("idempotent replay changed: %s %v", replay, err)
	}
	changed := req
	changed.ExpectedStateVersion = 8
	if _, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", changed); !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("changed idempotent request accepted: %v", err)
	}
}

func beforeProductRestartSession(id, conversationID, owner, status string) orm.WorkflowSession {
	now := time.Now().UTC().Add(-time.Hour)
	return orm.WorkflowSession{ID: id, ConversationID: conversationID, WorkflowID: "product_solution_delivery",
		WorkflowRevisionID: "older", CreateUserID: owner, Status: status, StateVersion: 3, CreatedAt: now, UpdatedAt: now}
}

func TestProductRestartKeepsNewestEffectiveSharedInputs(t *testing.T) {
	r := productRelayFixture(t)
	seedProductRestartGraph(t, r, "workspace_seed", "upstream_direction", "product_goal")
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ?", "source").Update("validity", "invalidated")
	productRestartInput(t, r, "source", "workspace_seed", "seed-old", []byte(`{"workspace_id":"obsolete"}`))
	seed := productRestartInput(t, r, "source", "workspace_seed", "seed-new", []byte(`{"workspace_id":"stable-project","workspace_mode":"shared-project"}`))
	productRestartInput(t, r, "source", "upstream_direction", "direction-old", []byte("old direction"))
	direction := productRestartInput(t, r, "source", "upstream_direction", "direction-new", []byte("latest bound direction"))
	productRestartInput(t, r, "source", "internal_only", "legacy", []byte("must not copy"))

	raw, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", ProductRestartRequest{IdempotencyKey: "restart-shared", ExpectedStateVersion: 9})
	if err != nil {
		t.Fatal(err)
	}
	newID := productRestartResult(t, raw)["session_id"].(string)
	inputs, err := r.ListInputBindings(context.Background(), "owner", newID)
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]InputBinding{}
	for _, input := range inputs {
		if _, duplicate := seen[input.MaterialID]; duplicate {
			t.Fatalf("duplicate material copied: %s", input.MaterialID)
		}
		seen[input.MaterialID] = input
		if input.CreatedByCommandID != productRestartBindingCommand("restart-shared", "binding:"+input.MaterialID) {
			t.Fatalf("inconsistent restart provenance: %#v", input)
		}
	}
	if len(seen) != 2 || seen["workspace_seed"].ResourceID != seed.ResourceID || seen["upstream_direction"].ResourceID != direction.ResourceID {
		t.Fatalf("newest bindings not preserved: %#v", seen)
	}
}

func TestProductRestartPreservesEveryDistinctListMaterial(t *testing.T) {
	r := productRelayFixture(t)
	seedProductRestartGraph(t, r, "product_materials")
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ?", "source").Update("validity", "invalidated")
	want := map[string]string{}
	var first InputBinding
	for index, content := range []string{"访谈记录 A", "表格数据 B", "用户附件 C"} {
		binding := productRestartInput(t, r, "source", "product_materials", "material-"+string(rune('a'+index)), []byte(content))
		want[binding.ContentHash] = content
		if index == 0 {
			first = binding
		}
	}
	if err := r.BindInput(context.Background(), "owner", InputBinding{WorkflowSessionID: "source", MaterialID: "product_materials",
		ResourceType: first.ResourceType, ResourceID: first.ResourceID, ResourceRevision: first.ResourceRevision,
		ContentHash: first.ContentHash, CreatedByCommandID: "same-resource-again"}); err != nil {
		t.Fatal(err)
	}
	raw, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", ProductRestartRequest{IdempotencyKey: "restart-list", ExpectedStateVersion: 9})
	if err != nil {
		t.Fatal(err)
	}
	newID := productRestartResult(t, raw)["session_id"].(string)
	inputs, err := r.ListInputBindings(context.Background(), "owner", newID)
	if err != nil || len(inputs) != 3 {
		t.Fatalf("list material was truncated or duplicated: %#v %v", inputs, err)
	}
	for _, input := range inputs {
		resource, getErr := r.GetInputResource(context.Background(), "owner", input.ResourceID)
		if getErr != nil || string(resource.Content) != want[input.ContentHash] || resource.ContentHash != input.ContentHash || resource.Revision != input.ResourceRevision {
			t.Fatalf("list identity/bytes changed: input=%#v resource=%#v err=%v", input, resource, getErr)
		}
	}
}

func TestProductRestartPromotesFresherWorkspaceAndExactHumanArtifact(t *testing.T) {
	r := productRelayFixture(t)
	seedProductRestartGraph(t, r, "workspace_seed", "upstream_direction")
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
	productRestartInput(t, r, "source", "workspace_seed", "seed", []byte(`{"workspace_id":"old-workspace"}`))
	productRestartInput(t, r, "source", "upstream_direction", "direction", []byte("older generated bytes"))

	newer := time.Now().UTC().Add(time.Minute)
	workspace := json.RawMessage(`{"workspace_id":"edited-workspace","workspace_mode":"shared-project","custom":{"verbatim":"保留"},"artifacts":[{"artifact_id":"direction-v1","artifact_type":"direction-brief","title":"方向","version":"1.0","status":"accepted","accepted_by":"owner","acceptance_ref":"approval-old","checks":{"old":true},"host_artifact":{"slot":"direction_document","source_session_id":"prior-session","content_sha256":"stale-digest"}}]}`)
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "workspace-r1").Updates(map[string]any{"content_snapshot": workspace, "created_at": newer}).Error; err != nil {
		t.Fatal(err)
	}
	humanID := "human-direction"
	exact := []byte("用户编辑内容\n保留空格  与换行\n")
	value, _ := json.Marshal(map[string]any{"content_base64": json.RawMessage(`"55So5oi357yW6L6R5YaF5a65CuS/neS/neS/nemXtOihjAo="`), "name": "direction.md"})
	// Use a JSON string artifact here so productArtifactBytes must return the
	// exact UTF-8 payload rather than a regenerated summary.
	encoded, _ := json.Marshal(string(exact))
	if err := r.db.Create(&orm.WorkflowHumanArtifact{ID: humanID, SessionID: "source", Slot: "direction_document", ContentType: "text/markdown", Value: encoded, CreatedAt: newer}).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "business-r7").Updates(map[string]any{
		"human_artifact_id": humanID, "content_snapshot": value, "change_source": "human", "producer_attempt_id": "", "created_at": newer,
	}).Error; err != nil {
		t.Fatal(err)
	}

	raw, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", ProductRestartRequest{IdempotencyKey: "restart-edited", ExpectedStateVersion: 9})
	if err != nil {
		t.Fatal(err)
	}
	newID := productRestartResult(t, raw)["session_id"].(string)
	inputs, _ := r.ListInputBindings(context.Background(), "owner", newID)
	resources := map[string]InputResource{}
	for _, input := range inputs {
		resource, getErr := r.GetInputResource(context.Background(), "owner", input.ResourceID)
		if getErr != nil {
			t.Fatal(getErr)
		}
		resources[input.MaterialID] = resource
	}
	if !reflect.DeepEqual(resources["upstream_direction"].Content, exact) {
		t.Fatalf("human bytes changed: %q", resources["upstream_direction"].Content)
	}
	seedObject := productObject(resources["workspace_seed"].Content)
	if seedObject["workspace_id"] != "edited-workspace" || seedObject["custom"].(map[string]any)["verbatim"] != "保留" {
		t.Fatalf("new workspace state was lost: %#v", seedObject)
	}
	lineage := seedObject["host_artifact_bindings"].([]any)[0].(map[string]any)
	if lineage["material_id"] != "upstream_direction" || lineage["slot_id"] != "direction_document" ||
		lineage["source_session_id"] != "source" || lineage["revision_id"] != "business-r7" ||
		lineage["content_hash"] != resources["upstream_direction"].ContentHash || lineage["resource_id"] != resources["upstream_direction"].ID {
		t.Fatalf("bad product lineage: %#v", lineage)
	}
	registered := seedObject["artifacts"].([]any)
	previous, draft := registered[0].(map[string]any), registered[1].(map[string]any)
	if previous["status"] != "superseded" || draft["status"] != "draft" || draft["implementation_readiness"] != "blocked" ||
		draft["accepted_by"] != nil || draft["acceptance_ref"] != nil || len(draft["checks"].(map[string]any)) != 0 ||
		draft["host_artifact"].(map[string]any)["source_session_id"] != "source" {
		t.Fatalf("human edit inherited accepted metadata: previous=%#v draft=%#v", previous, draft)
	}
}

func TestProductRestartDoesNotResurrectSelectedTombstone(t *testing.T) {
	r := productRelayFixture(t)
	seedProductRestartGraph(t, r, "workspace_seed", "upstream_direction")
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
	workspace := json.RawMessage(`{"workspace_id":"stable-project","artifacts":[{"artifact_id":"direction-v1","status":"accepted","accepted_by":"owner","host_artifact":{"slot":"direction_document","source_session_id":"source","content_sha256":"old"}}],"host_artifact_bindings":[{"material_id":"upstream_direction","slot_id":"direction_document","source_session_id":"source","revision_id":"old","revision":1,"content_hash":"old","resource_id":"old"}]}`)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "workspace-r1").Update("content_snapshot", workspace)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "manifest-r1").Update("validity", "invalidated")
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "business-r7").Update("validity", "deleted")
	productRestartInput(t, r, "source", "upstream_direction", "old-upstream", []byte("deleted content"))
	raw, err := r.RestartProductWorkflowOnLatest(context.Background(), "owner", "source", ProductRestartRequest{IdempotencyKey: "restart-tombstone", ExpectedStateVersion: 9})
	if err != nil {
		t.Fatal(err)
	}
	newID := productRestartResult(t, raw)["session_id"].(string)
	inputs, err := r.ListInputBindings(context.Background(), "owner", newID)
	if err != nil {
		t.Fatal(err)
	}
	var seed InputResource
	for _, input := range inputs {
		if input.MaterialID == "upstream_direction" {
			t.Fatalf("selected tombstone resurrected an old binding: %#v", inputs)
		}
		if input.MaterialID == "workspace_seed" {
			seed, _ = r.GetInputResource(context.Background(), "owner", input.ResourceID)
		}
	}
	seedObject := productObject(seed.Content)
	if seedObject == nil || len(seedObject["host_artifact_bindings"].([]any)) != 0 || seedObject["artifacts"].([]any)[0].(map[string]any)["status"] != "superseded" {
		t.Fatalf("selected tombstone resurrected an old binding: %#v %v", inputs, err)
	}
}

func TestProductRestartRejectsUnsafeRequests(t *testing.T) {
	tests := []struct {
		name, owner, want string
		version           int64
		setup             func(*Repository)
	}{
		{name: "wrong-owner", owner: "other", version: 9, want: "PERMISSION_DENIED"},
		{name: "stale-version", owner: "owner", version: 8, want: "STATE_VERSION_CONFLICT"},
		{name: "already-current", owner: "owner", version: 9, want: "PRODUCT_WORKFLOW_ALREADY_CURRENT", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("plugin_revision_id", "published")
		}},
		{name: "active", owner: "owner", version: 9, want: "PRODUCT_RESTART_NOT_ALLOWED", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "active")
		}},
		{name: "completed", owner: "owner", version: 9, want: "PRODUCT_RESTART_NOT_ALLOWED", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "completed")
		}},
		{name: "stopped", owner: "owner", version: 9, want: "PRODUCT_RESTART_NOT_ALLOWED", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "stopped")
		}},
		{name: "other-active", owner: "owner", version: 9, want: "WORKFLOW_SESSION_CONFLICT", setup: func(r *Repository) {
			session := beforeProductRestartSession("active-other", "conversation", "owner", "active")
			r.db.Create(&session)
		}},
		{name: "invalid-selected-workspace", owner: "owner", version: 9, want: "PRODUCT_RESTART_INPUT_INVALID", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "workspace-r1").Update("content_snapshot", json.RawMessage(`"not-an-object"`))
		}},
		{name: "invalid-workspace-seed", owner: "owner", version: 9, want: "PRODUCT_RESTART_INPUT_INVALID", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "workspace-r1").Update("validity", "invalidated")
			productRestartInput(t, r, "source", "workspace_seed", "bad-seed", []byte("not-json"))
		}},
		{name: "unsupported", owner: "owner", version: 9, want: "PRODUCT_RESTART_UNSUPPORTED", setup: func(r *Repository) {
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("plugin_id", "writer")
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r := productRelayFixture(t)
			seedProductRestartGraph(t, r, "workspace_seed", "upstream_direction")
			r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
			if test.setup != nil {
				test.setup(r)
			}
			var beforeCount int64
			r.db.Model(&orm.WorkflowSession{}).Count(&beforeCount)
			_, err := r.RestartProductWorkflowOnLatest(context.Background(), test.owner, "source", ProductRestartRequest{IdempotencyKey: "reject-" + test.name, ExpectedStateVersion: test.version})
			if err == nil || err.Error() != test.want {
				t.Fatalf("got %v want %s", err, test.want)
			}
			var sessions int64
			r.db.Model(&orm.WorkflowSession{}).Count(&sessions)
			if sessions != beforeCount {
				t.Fatal("rejected restart created a session")
			}
		})
	}
}

func TestProductRelaySummaryAdvertisesSafeRestartOnlyForFailedOldRevision(t *testing.T) {
	r := productRelayFixture(t)
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("status", "failed")
	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["update_available"] != true || summary["can_restart_on_latest"] != true {
		t.Fatalf("old failed session missing restart signal: %#v %v", summary, err)
	}
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", "source").Update("plugin_revision_id", "published")
	summary, err = r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["update_available"] != false || summary["can_restart_on_latest"] != false {
		t.Fatalf("current revision exposed restart: %#v %v", summary, err)
	}
}
