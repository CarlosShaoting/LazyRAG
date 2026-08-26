package modelprovider

import (
	"reflect"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"lazymind/core/common/orm"
)

func TestAutoSelectUnconfiguredProviderModelsSkipsExistingAndReportsMissing(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:auto_select_unconfigured_provider?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&orm.UserModelProviderGroupModel{}, &orm.UserSelectedModel{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	now := time.Now().UTC()
	if err := db.Create(&orm.UserSelectedModel{
		UserID: "user-1", UserName: "User One", ModelKey: "llm",
		UserModelProviderGroupModelID: "existing-llm", CreatedAt: now, UpdatedAt: now,
	}).Error; err != nil {
		t.Fatalf("create existing selection: %v", err)
	}
	models := []orm.UserModelProviderGroupModel{
		{ID: "llm-first", Name: "llm-catalog-first", ModelType: "llm"},
		{ID: "llm-second", Name: "llm-catalog-second", ModelType: "llm"},
		{ID: "vlm-first", Name: "vlm-catalog-first", ModelType: "vlm"},
		{ID: "image-first", Name: "image-catalog-first", ModelType: "text2image"},
	}
	result, err := autoSelectUnconfiguredProviderModels(db, "user-1", "User One", "Example", models, now)
	if err != nil {
		t.Fatalf("auto select: %v", err)
	}

	wantConfigured := []autoSelectedModel{
		{ModelKey: "vlm", Name: "vlm-catalog-first"},
		{ModelKey: "image_generator", Name: "image-catalog-first"},
	}
	if !reflect.DeepEqual(result.Configured, wantConfigured) {
		t.Fatalf("configured = %#v, want %#v", result.Configured, wantConfigured)
	}
	if !reflect.DeepEqual(result.Missing, []string{"embed_main"}) {
		t.Fatalf("missing = %#v, want embed_main", result.Missing)
	}

	var selections []orm.UserSelectedModel
	if err := db.Order("model_type ASC").Find(&selections).Error; err != nil {
		t.Fatalf("load selections: %v", err)
	}
	if len(selections) != 3 {
		t.Fatalf("selection count = %d, want 3", len(selections))
	}
	selectedIDs := map[string]string{}
	for _, selection := range selections {
		selectedIDs[selection.ModelKey] = selection.UserModelProviderGroupModelID
	}
	if selectedIDs["llm"] != "existing-llm" ||
		selectedIDs["vlm"] != "vlm-first" ||
		selectedIDs["image_generator"] != "image-first" {
		t.Fatalf("selected model ids = %#v", selectedIDs)
	}
}

func TestAutoSelectUnconfiguredProviderModelsDoesNothingWhenAllRolesExist(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:auto_select_all_configured?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&orm.UserSelectedModel{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	now := time.Now().UTC()
	for _, slot := range autoModelSlots {
		if err := db.Create(&orm.UserSelectedModel{
			UserID: "user-1", UserName: "User One", ModelKey: slot.ModelKey,
			UserModelProviderGroupModelID: "existing-" + slot.ModelKey,
			CreatedAt:                     now, UpdatedAt: now,
		}).Error; err != nil {
			t.Fatalf("create %s selection: %v", slot.ModelKey, err)
		}
	}

	result, err := autoSelectUnconfiguredProviderModels(
		db, "user-1", "User One", "Another Provider", nil, now,
	)
	if err != nil {
		t.Fatalf("auto select: %v", err)
	}
	if len(result.Configured) != 0 || len(result.Missing) != 0 {
		t.Fatalf("unexpected result when all roles exist: %#v", result)
	}
}
