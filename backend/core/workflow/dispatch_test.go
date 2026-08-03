package workflow

import (
	"context"
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/subagent"
	"lazymind/core/workflow/attempt"
	"lazymind/core/workflow/executor"
	"lazymind/core/workflow/legacydispatch"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func dispatchDB(t *testing.T, expanded bool) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(filepath.Join(t.TempDir(), "dispatch.db")), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	models := []any{&orm.WorkflowSessionStep{}, &orm.WorkflowRunOutbox{}, &orm.SubAgentTask{}}
	if expanded {
		models = append(models, &orm.WorkflowOutbox{}, &orm.WorkflowEvent{})
	}
	if err := db.AutoMigrate(models...); err != nil {
		t.Fatal(err)
	}
	return db
}

func seedDispatchStep(t *testing.T, db *gorm.DB, id string) {
	t.Helper()
	now := time.Now().UTC()
	if err := db.Create(&orm.SubAgentTask{ID: "task-" + id, ConversationID: "conversation", AgentType: "workflow_step", Title: "step", Objective: "make report", Mode: "manual", Status: "pending", InputSlots: json.RawMessage(`[]`), OutputSlots: json.RawMessage(`["report"]`), CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Create(&orm.WorkflowSessionStep{ID: id, SessionID: "session", StepID: "step", Attempt: 1, TaskID: "task-" + id, Status: StepStatusPending, Validity: "effective", ProgressJSON: "{}", ResultJSON: "{}", CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
}

func requestFor(id string) subagent.RunRequest {
	return subagent.RunRequest{TaskID: "task-" + id, AgentType: "workflow_step", WorkspacePath: "/host/private", DBDSN: "secret", LLMConfig: map[string]any{"api_key": "secret"}, Params: map[string]any{"operation": "execute", "objective": "make report"}}
}

func TestQueuedDispatchDefaultsOnOnlyWithSchemaAndServiceCapability(t *testing.T) {
	t.Setenv(QueuedDispatchEnv, "")
	if !QueuedDispatchEnabled(dispatchDB(t, true)) {
		t.Fatal("expanded schema must default to queued dispatch")
	}
	if QueuedDispatchEnabled(dispatchDB(t, false)) {
		t.Fatal("old schema must remain on compatibility dispatch")
	}
	t.Setenv(QueuedDispatchEnv, "false")
	if QueuedDispatchEnabled(dispatchDB(t, true)) {
		t.Fatal("dispatch rollback flag ignored")
	}
}

func TestCanonicalQueueContainsNeutralContextAndIsolatesLegacyWorker(t *testing.T) {
	t.Setenv(QueuedDispatchEnv, "")
	db := dispatchDB(t, true)
	seedDispatchStep(t, db, "a1")
	if err := enqueueWorkflowAttemptRunner(context.Background(), db, requestFor("a1")); err != nil {
		t.Fatal(err)
	}
	var row orm.WorkflowOutbox
	if err := db.First(&row, "attempt_id = ?", "a1").Error; err != nil {
		t.Fatal(err)
	}
	var value executor.AttemptContext
	if err := json.Unmarshal(row.PayloadJSON, &value); err != nil {
		t.Fatal(err)
	}
	if value.AttemptID != "a1" || value.Operation != "execute" {
		t.Fatalf("context=%#v", value)
	}
	text := string(row.PayloadJSON)
	for _, secret := range []string{"/host/private", "api_key", "secret", "llm_config", "db_dsn"} {
		if strings.Contains(text, secret) {
			t.Fatalf("host private value leaked: %s", text)
		}
	}
	var legacy int64
	db.Model(&orm.WorkflowRunOutbox{}).Count(&legacy)
	if legacy != 0 {
		t.Fatalf("legacy outbox count=%d", legacy)
	}
	before := legacydispatch.Calls()
	dispatchWorkflowAttemptRunner(db, nil, "task-a1")
	if legacydispatch.Calls() != before {
		t.Fatal("canonical runtime invoked legacy worker")
	}
}

func TestAlgorithmOutageLeavesQueuedAndRestartCanClaim(t *testing.T) {
	t.Setenv(QueuedDispatchEnv, "")
	db := dispatchDB(t, true)
	seedDispatchStep(t, db, "a2")
	if err := enqueueWorkflowAttemptRunner(context.Background(), db, requestFor("a2")); err != nil {
		t.Fatal(err)
	}
	// No algorithm process is contacted. A fresh service instance after restart
	// claims the same durable Attempt.
	var queued orm.WorkflowSessionStep
	if err := db.First(&queued, "id = ?", "a2").Error; err != nil || queued.Status != "queued" {
		t.Fatalf("queued=%#v err=%v", queued, err)
	}
	restarted := attempt.New(db, attempt.Config{LeaseDuration: time.Minute})
	claim, err := restarted.Claim(context.Background(), "executor-after-restart")
	if err != nil {
		t.Fatal(err)
	}
	if claim.AttemptID != "a2" || claim.FencingGeneration != 1 {
		t.Fatalf("claim=%#v", claim)
	}
}

func TestRollbackIsDispatchFlagOnlyAndDoesNotMigrateQueuedData(t *testing.T) {
	t.Setenv(QueuedDispatchEnv, "")
	db := dispatchDB(t, true)
	seedDispatchStep(t, db, "canonical")
	if err := enqueueWorkflowAttemptRunner(context.Background(), db, requestFor("canonical")); err != nil {
		t.Fatal(err)
	}
	t.Setenv(QueuedDispatchEnv, "false")
	seedDispatchStep(t, db, "legacy")
	if err := enqueueWorkflowAttemptRunner(context.Background(), db, requestFor("legacy")); err != nil {
		t.Fatal(err)
	}
	var canonical orm.WorkflowOutbox
	if err := db.First(&canonical, "attempt_id = ?", "canonical").Error; err != nil || canonical.Status != "pending" {
		t.Fatalf("canonical=%#v err=%v", canonical, err)
	}
	var legacy orm.WorkflowRunOutbox
	if err := db.First(&legacy, "task_id = ?", "task-legacy").Error; err != nil || legacy.Status != "pending" {
		t.Fatalf("legacy=%#v err=%v", legacy, err)
	}
}

func TestOldWorkerOutboxCannotBeClaimedByAttemptService(t *testing.T) {
	db := dispatchDB(t, true)
	now := time.Now().UTC()
	payload, _ := json.Marshal(requestFor("old"))
	if err := db.Create(&orm.WorkflowRunOutbox{TaskID: "task-old", Payload: payload, Status: "pending", CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	_, err := attempt.New(db, attempt.Config{}).Claim(context.Background(), "new-worker")
	if err != attempt.ErrNotClaimable {
		t.Fatalf("claim error=%v", err)
	}
	var row orm.WorkflowRunOutbox
	db.First(&row, "task_id = ?", "task-old")
	if row.Status != "pending" {
		t.Fatalf("old outbox mutated: %#v", row)
	}
}
