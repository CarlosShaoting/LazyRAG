package workflow

import (
	"context"
	"testing"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/workflow/graphengine"
)

func TestRetryKeepsGenericAttemptOutputsAsResumeCheckpoints(t *testing.T) {
	db := newTestDB(t)
	if err := db.AutoMigrate(
		&orm.WorkflowAttemptInputBinding{},
		&orm.WorkflowRouteDecision{},
	); err != nil {
		t.Fatalf("migrate retry dependency tables: %v", err)
	}
	ctx := context.Background()
	if _, err := CreateSession(ctx, db.DB, CreateSessionInput{
		SessionID: "resume-session", ConversationID: "resume-conversation", WorkflowID: "test-workflow",
	}); err != nil {
		t.Fatalf("create session: %v", err)
	}
	step, err := CreateSessionStep(ctx, db.DB, "resume-session", "assemble", "resume-task", 1)
	if err != nil {
		t.Fatalf("create step: %v", err)
	}
	if err := db.Model(&orm.WorkflowSessionStep{}).Where("id = ?", step.ID).
		Update("status", StepStatusFailed).Error; err != nil {
		t.Fatalf("fail step: %v", err)
	}
	index := 3
	revision := orm.WorkflowSlotRevision{
		ID: "partial-list-output", SessionID: "resume-session", SlotID: "items",
		Revision: 1, ListIndex: &index, Selected: true, ChangeSource: "ai",
		Slot: "items", StepID: "assemble", Attempt: 1,
		Validity: "effective", ProducerAttemptID: step.ID, CreatedAt: time.Now().UTC(),
	}
	if err := db.Create(&revision).Error; err != nil {
		t.Fatalf("create partial output: %v", err)
	}

	if err := invalidateForOperation(
		ctx, db.DB, &orm.WorkflowSession{ID: "resume-session"},
		&graphengine.CompiledStateGraph{}, "retry-command", "retry", "assemble",
	); err != nil {
		t.Fatalf("invalidate for retry: %v", err)
	}

	var got orm.WorkflowSlotRevision
	if err := db.First(&got, "id = ?", revision.ID).Error; err != nil {
		t.Fatalf("load partial output: %v", err)
	}
	if got.Validity != "effective" || !got.Selected {
		t.Fatalf("partial output was discarded on retry: validity=%q selected=%v", got.Validity, got.Selected)
	}
	var gotStep orm.WorkflowSessionStep
	if err := db.First(&gotStep, "id = ?", step.ID).Error; err != nil {
		t.Fatalf("load attempt: %v", err)
	}
	if gotStep.Validity != "stale" {
		t.Fatalf("retried attempt validity=%q, want stale", gotStep.Validity)
	}
}

func TestLoadWorkflowResumeCheckpointDescribesScalarAndListOutputs(t *testing.T) {
	db := newTestDB(t)
	ctx := context.Background()
	now := time.Now().UTC()
	source := orm.WorkflowSessionStep{
		ID: "attempt-1", SessionID: "session-1", StepID: "assemble",
		Attempt: 1, TaskID: "task-1", Status: StepStatusFailed,
		Validity: "effective", CreatedAt: now, UpdatedAt: now,
	}
	if err := db.Create(&source).Error; err != nil {
		t.Fatal(err)
	}
	indices := []int{0, 1, 3}
	ids := []string{"list-a", "list-b", "list-c"}
	for i, listIndex := range indices {
		index := listIndex
		if err := db.Create(&orm.WorkflowSlotRevision{
			ID: ids[i], SessionID: "session-1", SlotID: "items",
			Revision: 1, ListIndex: &index, Selected: true, Slot: "items",
			StepID: "assemble", Attempt: 1, Validity: "effective",
			ProducerAttemptID: source.ID, CreatedAt: now,
		}).Error; err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Create(&orm.WorkflowSlotRevision{
		ID: "scalar", SessionID: "session-1", SlotID: "summary", Revision: 1,
		Selected: true, Slot: "summary", StepID: "assemble", Attempt: 1,
		Validity: "effective", ProducerAttemptID: source.ID, CreatedAt: now,
	}).Error; err != nil {
		t.Fatal(err)
	}

	checkpoint, err := loadWorkflowResumeCheckpoint(
		ctx, db.DB, "session-1", "assemble", source,
	)
	if err != nil {
		t.Fatal(err)
	}
	if checkpoint.FromAttemptID != source.ID || checkpoint.FromTaskID != source.TaskID {
		t.Fatalf("source=%#v", checkpoint)
	}
	if !checkpoint.CompletedOutputs["summary"].Scalar {
		t.Fatalf("scalar checkpoint=%#v", checkpoint.CompletedOutputs["summary"])
	}
	got := checkpoint.CompletedOutputs["items"].ListIndices
	if len(got) != 3 || got[0] != 0 || got[1] != 1 || got[2] != 3 {
		t.Fatalf("list checkpoint=%v", got)
	}
}
