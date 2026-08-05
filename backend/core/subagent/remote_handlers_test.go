package subagent

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	"github.com/gorilla/mux"

	"lazymind/core/common/orm"
	"lazymind/core/state"
	"lazymind/core/store"
)

func remoteSubagentFixture(t *testing.T) *orm.DB {
	t.Helper()
	db := newTestDB(t)
	if err := db.AutoMigrate(&orm.WorkflowSessionStep{}); err != nil {
		t.Fatal(err)
	}
	for _, statement := range []string{
		`CREATE TABLE user_selected_models (id TEXT, user_id TEXT, model_type TEXT, share BOOLEAN, user_model_provider_group_model_id TEXT)`,
		`CREATE TABLE user_model_provider_group_models (id TEXT, create_user_id TEXT, deleted_at DATETIME, provider_name TEXT, name TEXT, user_model_provider_group_id TEXT, max_input_tokens TEXT)`,
		`CREATE TABLE user_model_provider_groups (id TEXT, create_user_id TEXT, deleted_at DATETIME, base_url TEXT, api_key TEXT, api_key_ciphertext TEXT)`,
	} {
		if err := db.Exec(statement).Error; err != nil {
			t.Fatal(err)
		}
	}
	now := time.Now().UTC()
	if err := db.Create(&orm.SubAgentTask{ID: "task-remote", ConversationID: "conversation-1",
		AgentType: "workflow_step", Title: "remote", Objective: "run", Mode: "auto", Status: StatusPending,
		WorkspacePath: "/core/path/must-not-be-used", InputSlots: json.RawMessage(`[]`),
		OutputSlots: json.RawMessage(`["report"]`), CreateUserID: "user-1", LastHeartbeat: now,
		CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	expires := now.Add(time.Minute)
	if err := db.Create(&orm.WorkflowSessionStep{ID: "attempt-remote", SessionID: "session-1", StepID: "step-1",
		Attempt: 1, TaskID: "task-remote", Status: "running", Validity: "effective", LeaseToken: "lease-live",
		LeaseExpiresAt: &expires, CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	store.Init(db.DB, db.DB, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })
	t.Setenv("LAZYMIND_WORKFLOW_EXECUTOR_TOKEN", "executor-secret")
	return db
}

func postRemoteTaskEvent(t *testing.T, lease string, event map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(event)
	req := httptest.NewRequest(http.MethodPost, "/internal/subagent/tasks/task-remote/events", bytes.NewReader(body))
	req = mux.SetURLVars(req, map[string]string{"task_id": "task-remote"})
	req.Header.Set("Authorization", "Bearer executor-secret")
	req.Header.Set("X-Workflow-Lease-Token", lease)
	rec := httptest.NewRecorder()
	InternalIngestTaskEvent(rec, req)
	return rec
}

func TestRemoteTaskEventsRequireBoundAttemptLease(t *testing.T) {
	remoteSubagentFixture(t)
	for _, lease := range []string{"", "stale"} {
		rec := postRemoteTaskEvent(t, lease, map[string]any{"type": "progress", "progress": 10})
		if rec.Code != http.StatusConflict && rec.Code != http.StatusUnauthorized {
			t.Fatalf("lease=%q status=%d body=%s", lease, rec.Code, rec.Body.String())
		}
	}
}

func TestRemoteExecutionSpecReturnsTaskParamsAndDurableSteps(t *testing.T) {
	db := remoteSubagentFixture(t)
	if err := db.Model(&orm.SubAgentTask{}).Where("id = ?", "task-remote").Update("params",
		json.RawMessage(`{"operation":"execute"}`)).Error; err != nil {
		t.Fatal(err)
	}
	if err := AppendRemoteStep(context.Background(), db.DB, "task-remote", "text",
		json.RawMessage(`{"content":"checkpoint"}`)); err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodGet, "/internal/subagent/tasks/task-remote/execution-spec", nil)
	req = mux.SetURLVars(req, map[string]string{"task_id": "task-remote"})
	req.Header.Set("Authorization", "Bearer executor-secret")
	req.Header.Set("X-Workflow-Lease-Token", "lease-live")
	rec := httptest.NewRecorder()
	InternalGetExecutionSpec(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	data := getData(rec.Body.Bytes())
	params := data["params"].(map[string]any)
	steps := data["steps"].([]any)
	if params["operation"] != "execute" || len(steps) != 1 {
		t.Fatalf("data=%#v", data)
	}
	if _, exposed := data["workspace_path"]; exposed {
		t.Fatalf("Core workspace must not be exposed: %#v", data)
	}
}

func TestRemoteTaskEventsPersistStreamStateAndInvalidatePanel(t *testing.T) {
	db := remoteSubagentFixture(t)
	previousHooks := EventHooks
	EventHooks = &eventHooks{}
	t.Cleanup(func() { EventHooks = previousHooks })
	updates := []string{}
	EventHooks.RegisterConversationEventHook(func(_ context.Context, _ state.Store, convID, _ string,
		eventType string, payload map[string]any) {
		if convID == "conversation-1" && eventType == "workflow_runtime_updated" {
			updates = append(updates, payload["change"].(string))
		}
	})

	events := []map[string]any{
		{"type": "task_start"},
		{"type": "text", "text": "hello"},
		{"type": "think", "think": "reason"},
		{"type": "tool_calls", "tool_calls": []map[string]any{{"id": "1", "name": "read"}}},
		{"type": "tool_results", "tool_results": []map[string]any{{"id": "1", "result": "ok"}}},
		{"type": "progress", "progress": 42, "current_phase": "working"},
		{"type": "artifact", "slot": "report", "content_type": "text", "seq": 1,
			"value": map[string]any{"text": "result"}},
	}
	for _, event := range events {
		rec := postRemoteTaskEvent(t, "lease-live", event)
		if rec.Code != http.StatusOK {
			t.Fatalf("event=%v status=%d body=%s", event["type"], rec.Code, rec.Body.String())
		}
	}
	steps, err := LoadSteps(context.Background(), db.DB, "task-remote")
	if err != nil || len(steps) != 4 {
		t.Fatalf("steps=%#v err=%v", steps, err)
	}
	for i, role := range []string{"text", "think", "assistant", "tool"} {
		if steps[i].Seq != i || steps[i].Role != role {
			t.Fatalf("step[%d]=%#v", i, steps[i])
		}
	}
	task, _ := GetTask(context.Background(), db.DB, "task-remote")
	if task.Status != StatusRunning || task.ProgressPct != 42 || task.CurrentPhase != "working" {
		t.Fatalf("task=%#v", task)
	}
	artifacts, _ := LoadArtifacts(context.Background(), db.DB, "task-remote")
	if len(artifacts) != 1 || artifacts[0].Slot != "report" {
		t.Fatalf("artifacts=%#v", artifacts)
	}
	wantUpdates := []string{"task_start", "progress", "artifact"}
	if !reflect.DeepEqual(updates, wantUpdates) {
		t.Fatalf("updates=%v want=%v", updates, wantUpdates)
	}
}

func TestAppendRemoteStepAllocatesMonotonicSequence(t *testing.T) {
	db := remoteSubagentFixture(t)
	for _, role := range []string{"text", "think", "tool"} {
		if err := AppendRemoteStep(context.Background(), db.DB, "task-remote", role,
			json.RawMessage(`{"content":"x"}`)); err != nil {
			t.Fatal(err)
		}
	}
	steps, _ := LoadSteps(context.Background(), db.DB, "task-remote")
	for i := range steps {
		if steps[i].Seq != i {
			t.Fatalf("steps=%#v", steps)
		}
	}
}
