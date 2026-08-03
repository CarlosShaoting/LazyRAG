package orm

import (
	"path/filepath"
	"testing"
)

func TestWorkflowModelsRegisteredForLocalDDL(t *testing.T) {
	models := AllModelsForDDL()
	for _, want := range []any{
		&WorkflowSlotOrder{},
		&WorkflowHumanArtifact{},
		&WorkflowDraft{},
		&WorkflowResource{},
		&WorkflowBlob{},
		&WorkflowRevision{},
		&WorkflowRevisionEntry{},
		&UserWorkflowSetting{},
	} {
		if !modelListContains(models, want) {
			t.Fatalf("expected %T in AllModelsForDDL", want)
		}
	}

	names := map[string]bool{}
	for _, name := range TableNamesForDDL() {
		names[name] = true
	}
	for _, want := range []string{
		"plugin_slot_order",
		"plugin_human_artifacts",
		"plugin_drafts",
		"plugins",
		"plugin_blobs",
		"plugin_revisions",
		"plugin_revision_entries",
		"user_plugin_settings",
	} {
		if !names[want] {
			t.Fatalf("expected %s in TableNamesForDDL", want)
		}
	}
}

func TestProductionModelListCreatesWorkflowSchemaOnSQLite(t *testing.T) {
	db, err := Connect(DriverSQLite, filepath.Join(t.TempDir(), "workflow-schema.db"))
	if err != nil {
		t.Fatalf("connect sqlite: %v", err)
	}

	if err := db.AutoMigrate(AllModelsForDDL()...); err != nil {
		t.Fatalf("auto migrate production model list: %v", err)
	}

	for _, model := range []any{
		&WorkflowDraft{},
		&WorkflowResource{},
		&WorkflowBlob{},
		&WorkflowRevision{},
		&WorkflowRevisionEntry{},
		&UserWorkflowSetting{},
	} {
		if !db.Migrator().HasTable(model) {
			t.Fatalf("expected table for %T to exist", model)
		}
	}

	columnTypes, err := db.Migrator().ColumnTypes(&WorkflowBlob{})
	if err != nil {
		t.Fatalf("inspect plugin blob columns: %v", err)
	}
	foundContent := false
	for _, columnType := range columnTypes {
		if columnType.Name() == "content" {
			foundContent = true
			if columnType.DatabaseTypeName() != "blob" {
				t.Fatalf("expected plugin blob content to use SQLite blob type, got %s", columnType.DatabaseTypeName())
			}
		}
	}
	if !foundContent {
		t.Fatal("expected plugin blob content column")
	}

	if !db.Migrator().HasIndex(&WorkflowDraft{}, "idx_plugin_drafts_created_by") {
		t.Fatal("expected plugin draft owner index")
	}
	if !db.Migrator().HasIndex(&WorkflowDraft{}, "idx_plugin_drafts_user_plugin_id") {
		t.Fatal("expected plugin draft identity unique index")
	}
	if !db.Migrator().HasIndex(&WorkflowResource{}, "idx_plugins_owner") {
		t.Fatal("expected plugin owner index")
	}
	if !db.Migrator().HasIndex(&WorkflowRevision{}, "uk_plugin_revisions_resource_no") {
		t.Fatal("expected plugin revision unique index")
	}
}
