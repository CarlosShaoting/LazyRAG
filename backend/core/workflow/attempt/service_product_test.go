package attempt

import (
	"context"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"lazymind/core/common/orm"
)

func productOutputTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(&orm.WorkflowSession{}, &orm.WorkflowSessionStep{}, &orm.WorkflowSlotRevision{},
		&orm.WorkflowAttemptInputBinding{}, &orm.WorkflowRouteDecision{}); err != nil {
		t.Fatal(err)
	}
	return db
}

func TestProductOutputsPublishOnlyOnSuccess(t *testing.T) {
	db := productOutputTestDB(t)
	now := time.Now().UTC()
	session := orm.WorkflowSession{ID: "session", ConversationID: "case-a", WorkflowID: "product_solution_delivery", CreatedAt: now, UpdatedAt: now}
	priorStep := orm.WorkflowSessionStep{ID: "prior", SessionID: session.ID, StepID: "write_prd_document", Attempt: 1, TaskID: "prior", Status: "succeeded", CreatedAt: now, UpdatedAt: now}
	current := orm.WorkflowSessionStep{ID: "current", SessionID: session.ID, StepID: "write_prd_document", Attempt: 2, TaskID: "current", Status: "succeeded", CreatedAt: now, UpdatedAt: now}
	for _, row := range []any{&session, &priorStep, &current} {
		if err := db.Select("*").Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	prior := orm.WorkflowSlotRevision{ID: "old", SessionID: session.ID, SlotID: "prd_document", Slot: "prd_document", Revision: 1, Selected: true, Validity: "effective", ProducerAttemptID: priorStep.ID, CreatedAt: now}
	newDoc := orm.WorkflowSlotRevision{ID: "new", SessionID: session.ID, SlotID: "prd_document", Slot: "prd_document", Revision: 2, Selected: false, Validity: "effective", ProducerAttemptID: current.ID, CreatedAt: now}
	newHTML := orm.WorkflowSlotRevision{ID: "html", SessionID: session.ID, SlotID: "prd_document_html", Slot: "prd_document_html", Revision: 1, Selected: false, Validity: "effective", ProducerAttemptID: current.ID, CreatedAt: now}
	for _, row := range []*orm.WorkflowSlotRevision{&prior, &newDoc, &newHTML} {
		if err := db.Select("*").Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Model(&orm.WorkflowSlotRevision{}).Where("producer_attempt_id = ?", current.ID).Update("selected", false).Error; err != nil {
		t.Fatal(err)
	}
	var selected []orm.WorkflowSlotRevision
	if err := db.Where("selected = ?", true).Find(&selected).Error; err != nil {
		t.Fatal(err)
	}
	if len(selected) != 1 || selected[0].ID != prior.ID {
		t.Fatalf("uncommitted outputs exposed: %+v", selected)
	}
	if err := db.Transaction(func(tx *gorm.DB) error {
		return finishProductAttemptOutputs(context.Background(), tx, current, "succeeded")
	}); err != nil {
		t.Fatal(err)
	}
	selected = nil
	if err := db.Where("selected = ?", true).Find(&selected).Error; err != nil {
		t.Fatal(err)
	}
	if len(selected) != 2 {
		t.Fatalf("want two committed outputs, got %+v", selected)
	}
	for _, row := range selected {
		if row.ID == prior.ID {
			t.Fatalf("old version remained selected: %+v", selected)
		}
	}
}

func TestProductFailedOutputsStayOutOfSelectedView(t *testing.T) {
	db := productOutputTestDB(t)
	now := time.Now().UTC()
	session := orm.WorkflowSession{ID: "session", ConversationID: "case-b", WorkflowID: "product_solution_delivery", CreatedAt: now, UpdatedAt: now}
	current := orm.WorkflowSessionStep{ID: "failed", SessionID: session.ID, StepID: "write_prd_document", Attempt: 1, TaskID: "failed", Status: "failed", CreatedAt: now, UpdatedAt: now}
	for _, row := range []any{&session, &current} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	for i := 0; i < 12; i++ {
		row := orm.WorkflowSlotRevision{ID: string(rune('a' + i)), SessionID: session.ID, SlotID: "prd_chapters", Slot: "prd_chapters", Revision: 1, ListIndex: &i, Selected: false, Validity: "effective", ProducerAttemptID: current.ID, CreatedAt: now}
		if err := db.Select("*").Create(&row).Error; err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Model(&orm.WorkflowSlotRevision{}).Where("producer_attempt_id = ?", current.ID).Update("selected", false).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Transaction(func(tx *gorm.DB) error {
		return finishProductAttemptOutputs(context.Background(), tx, current, "failed")
	}); err != nil {
		t.Fatal(err)
	}
	var selected, effective int64
	if err := db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ? AND selected = ?", session.ID, true).Count(&selected).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Model(&orm.WorkflowSlotRevision{}).Where("session_id = ? AND validity = ?", session.ID, "effective").Count(&effective).Error; err != nil {
		t.Fatal(err)
	}
	if selected != 0 || effective != 0 {
		t.Fatalf("failed chapters remained effective: selected=%d effective=%d", selected, effective)
	}
}

func TestProductFailureKeepsPreviousCompleteVersion(t *testing.T) {
	db := productOutputTestDB(t)
	now := time.Now().UTC()
	session := orm.WorkflowSession{ID: "session", ConversationID: "case-c", WorkflowID: "product_solution_delivery", CreatedAt: now, UpdatedAt: now}
	priorStep := orm.WorkflowSessionStep{ID: "prior", SessionID: session.ID, StepID: "build_interactive_prototype", Attempt: 1, TaskID: "prior", Status: "succeeded", CreatedAt: now, UpdatedAt: now}
	failedStep := orm.WorkflowSessionStep{ID: "failed", SessionID: session.ID, StepID: "build_interactive_prototype", Attempt: 2, TaskID: "failed", Status: "failed", CreatedAt: now, UpdatedAt: now}
	for _, row := range []any{&session, &priorStep, &failedStep} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	prior := orm.WorkflowSlotRevision{ID: "old", SessionID: session.ID, SlotID: "prototype", Slot: "prototype", Revision: 1, Selected: true, Validity: "effective", ProducerAttemptID: priorStep.ID, CreatedAt: now}
	partial := orm.WorkflowSlotRevision{ID: "partial", SessionID: session.ID, SlotID: "prototype", Slot: "prototype", Revision: 2, Selected: true, Validity: "effective", ProducerAttemptID: failedStep.ID, CreatedAt: now}
	for _, row := range []*orm.WorkflowSlotRevision{&prior, &partial} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	// Simulate an older binary which deselected v1 before the new attempt failed.
	if err := db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", prior.ID).Update("selected", false).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Transaction(func(tx *gorm.DB) error {
		return finishProductAttemptOutputs(context.Background(), tx, failedStep, "failed")
	}); err != nil {
		t.Fatal(err)
	}
	var selected []orm.WorkflowSlotRevision
	if err := db.Where("session_id = ? AND selected = ?", session.ID, true).Find(&selected).Error; err != nil {
		t.Fatal(err)
	}
	if len(selected) != 1 || selected[0].ID != prior.ID {
		t.Fatalf("previous complete version was not restored: %+v", selected)
	}
}
