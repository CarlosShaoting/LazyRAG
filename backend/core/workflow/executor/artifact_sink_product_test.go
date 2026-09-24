package executor

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"lazymind/core/common/orm"
	"lazymind/core/workflow/attempt"
)

func TestProductArtifactStaysUnselectedUntilAttemptCompletes(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(&orm.WorkflowSession{}, &orm.WorkflowSessionStep{}, &orm.WorkflowSlotRevision{}, &orm.WorkflowHumanArtifact{}, &orm.WorkflowEvent{}, &orm.WorkflowOutbox{}); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	session := orm.WorkflowSession{ID: "product-session", ConversationID: "product-case", WorkflowID: "product_solution_delivery", CreatedAt: now, UpdatedAt: now}
	if err := db.Create(&session).Error; err != nil {
		t.Fatal(err)
	}
	leaseExpiry := now.Add(time.Minute)
	step := orm.WorkflowSessionStep{ID: "attempt", SessionID: session.ID, StepID: "write_prd_document", Attempt: 1, TaskID: "attempt", Status: "running", LeaseToken: "lease", LeaseExpiresAt: &leaseExpiry, CreatedAt: now, UpdatedAt: now}
	if err := db.Create(&step).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Create(&orm.WorkflowOutbox{ID: "outbox", AttemptID: step.ID, SessionID: session.ID, PayloadJSON: json.RawMessage(`{}`), Status: "claimed", CreatedAt: now, UpdatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	value := json.RawMessage(`{"text":"PRD draft"}`)
	contract := AttemptContext{SessionID: session.ID, AttemptID: step.ID, StepID: step.StepID, AttemptNo: 1, OutputCardinality: map[string]string{"prd_document": "single"}}
	if err := (DBArtifactSink{DB: db}).Save(context.Background(), contract, Artifact{Slot: "prd_document", Seq: 1, ContentType: "text", Value: value}); err != nil {
		t.Fatal(err)
	}
	var revision orm.WorkflowSlotRevision
	if err := db.Where("producer_attempt_id = ?", step.ID).First(&revision).Error; err != nil {
		t.Fatal(err)
	}
	if revision.Selected || revision.Validity != "effective" {
		t.Fatalf("output published before terminal success: %+v", revision)
	}
	if err := attempt.New(db, attempt.Config{}).Complete(context.Background(), step.ID, "lease", json.RawMessage(`{}`)); err != nil {
		t.Fatal(err)
	}
	if err := db.Where("id = ?", revision.ID).First(&revision).Error; err != nil {
		t.Fatal(err)
	}
	if !revision.Selected || revision.Validity != "effective" {
		t.Fatalf("output not committed with terminal success: %+v", revision)
	}
}
