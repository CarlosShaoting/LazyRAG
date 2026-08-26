package modelprovider

import (
	"reflect"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"lazymind/core/common/orm"
)

func TestAutoSelectFirstProviderModelsUsesFirstCatalogModelAndReportsMissing(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:auto_select_first_provider?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&orm.UserModelProviderGroupModel{}, &orm.UserSelectedModel{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	now := time.Now().UTC()
	models := []orm.UserModelProviderGroupModel{
		{ID: "llm-first", Name: "llm-catalog-first", ModelType: "llm"},
		{ID: "llm-second", Name: "llm-catalog-second", ModelType: "llm"},
		{ID: "vlm-first", Name: "vlm-catalog-first", ModelType: "vlm"},
	}
	result, err := autoSelectFirstProviderModels(db, "user-1", "User One", "Example", models, now)
	if err != nil {
		t.Fatalf("auto select: %v", err)
	}

	wantConfigured := []autoSelectedModel{
		{ModelKey: "llm", Name: "llm-catalog-first"},
		{ModelKey: "vlm", Name: "vlm-catalog-first"},
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
	if len(selections) != 2 {
		t.Fatalf("selection count = %d, want 2", len(selections))
	}
	selectedIDs := map[string]string{}
	for _, selection := range selections {
		selectedIDs[selection.ModelKey] = selection.UserModelProviderGroupModelID
	}
	if selectedIDs["llm"] != "llm-first" || selectedIDs["vlm"] != "vlm-first" {
		t.Fatalf("selected model ids = %#v", selectedIDs)
	}
}

func TestIsFirstModelProviderGroupOnlyCountsModelCategory(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:first_model_provider_group?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&orm.UserModelProvider{}, &orm.UserModelProviderGroup{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	now := time.Now().UTC()
	externalProvider := orm.UserModelProvider{
		ID: "external-provider", Name: "Search", Category: "search",
		BaseModel: orm.BaseModel{CreateUserID: "user-1", CreatedAt: now, UpdatedAt: now},
	}
	if err := db.Create(&externalProvider).Error; err != nil {
		t.Fatalf("create external provider: %v", err)
	}
	if err := db.Create(&orm.UserModelProviderGroup{
		ID: "external-group", UserModelProviderID: externalProvider.ID, Name: "Search", BaseURL: "https://example.com",
		BaseModel: orm.BaseModel{CreateUserID: "user-1", CreatedAt: now, UpdatedAt: now},
	}).Error; err != nil {
		t.Fatalf("create external group: %v", err)
	}

	first, err := isFirstModelProviderGroup(db, "user-1", defaultProviderCategory)
	if err != nil {
		t.Fatalf("check first provider: %v", err)
	}
	if !first {
		t.Fatal("external-service groups must not prevent first model-provider auto selection")
	}
}
