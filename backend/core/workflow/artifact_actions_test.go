package workflow

import (
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"lazymind/core/common/orm"
)

func TestPPTRewriteSelectionUsesFinalBuiltinActionRevision(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(&orm.WorkflowResource{}, &orm.WorkflowRevision{}); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	resource := orm.WorkflowResource{
		ID: "ppt", WorkflowRef: "builtin:ppt-workflow", WorkflowID: "ppt-workflow",
		OwnerScope: "builtin", SourceType: "builtin", RelativeRoot: "workflows/builtin/ppt-workflow",
		Name: "PPT", HeadRevisionID: "final", Version: 19, Status: "active",
		CreatedAt: now, UpdatedAt: now,
	}
	if err := db.Create(&resource).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Create(&orm.WorkflowRevision{
		ID: "final", WorkflowResourceID: "ppt", RevisionNo: 19, TreeHash: "final-tree",
		CreatedAt: now,
	}).Error; err != nil {
		t.Fatal(err)
	}
	target := &artifactActionTarget{db: db, session: &orm.WorkflowSession{
		WorkflowID: "ppt-workflow", WorkflowRef: "builtin:ppt-workflow",
		WorkflowRevisionID: "legacy", WorkflowTreeHash: "legacy-tree",
	}}
	got, err := resolveArtifactActionWorkflow(t.Context(), target, "rewrite_selection")
	if err != nil {
		t.Fatal(err)
	}
	if got.revisionID != "final" || got.treeHash != "final-tree" {
		t.Fatalf("expected final PPT action revision, got %#v", got)
	}
}

func TestOtherArtifactActionsRemainPinned(t *testing.T) {
	target := &artifactActionTarget{session: &orm.WorkflowSession{
		WorkflowID: "writer-workflow", WorkflowRevisionID: "pinned", WorkflowTreeHash: "tree",
	}}
	got, err := resolveArtifactActionWorkflow(t.Context(), target, "rewrite_selection")
	if err != nil {
		t.Fatal(err)
	}
	if got.revisionID != "pinned" || got.treeHash != "tree" {
		t.Fatalf("non-PPT action must stay pinned, got %#v", got)
	}
}
