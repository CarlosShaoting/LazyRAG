package chat

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/evolution"
	skillbuiltin "lazymind/core/skillv2/builtin"
	"lazymind/core/skillv2/testutil"
)

func TestIsFeishuChatIntent(t *testing.T) {
	for _, query := range []string{
		"打开 https://sensetime.feishu.cn/wiki/example 并写入日报",
		"把内容写到飞书文档",
		"Use Feishu to update the report",
		"read this Lark doc",
		"https://example.larksuite.com/docx/demo",
	} {
		if !isFeishuChatIntent(query) {
			t.Fatalf("query %q should match Feishu intent", query)
		}
	}
	for _, query := range []string{"打开 BBC 官网", "生成一个小狗图片", "The meadowlark is a bird", ""} {
		if isFeishuChatIntent(query) {
			t.Fatalf("query %q should not match Feishu intent", query)
		}
	}
}

func TestInstallChatBuiltinSkillPackageCreatesEnabledInstall(t *testing.T) {
	db := testutil.NewTestDB(t)
	pkg := testChatBuiltinPackage(t)
	t.Setenv("LAZYMIND_SKILL_OBJECT_ROOT", t.TempDir())

	result, err := installChatBuiltinSkillPackage(context.Background(), db.DB, "user_001", "张三", pkg)
	if err != nil {
		t.Fatalf("installChatBuiltinSkillPackage: %v", err)
	}
	if result.State != autoBuiltinSkillInstalled || result.SkillID == "" {
		t.Fatalf("unexpected install result: %#v", result)
	}

	var row testutil.SkillRow
	if err := db.Where("id = ?", result.SkillID).Take(&row).Error; err != nil {
		t.Fatal(err)
	}
	if row.OwnerUserID != "user_001" || row.OriginBuiltinSkillUID != pkg.UID || !row.IsEnabled || row.HeadRevisionID == nil {
		t.Fatalf("unexpected installed row: %#v", row)
	}
	if got := testutil.CountRows(t, db, "skill_distribution_bindings", "skill_id = ?", result.SkillID); got != 1 {
		t.Fatalf("distribution binding count=%d, want 1", got)
	}
}

func TestInstalledChatBuiltinSkillIsAvailableInSameTurnContext(t *testing.T) {
	database := newPromptTestDB(t)
	if err := database.AutoMigrate(
		&orm.SkillDistributionArtifact{},
		&orm.SkillDistributionEntry{},
		&orm.SkillDistributionBinding{},
		&orm.SkillRevisionDistribution{},
	); err != nil {
		t.Fatalf("auto migrate Skill distribution tables: %v", err)
	}
	pkg := testChatBuiltinPackage(t)
	t.Setenv("LAZYMIND_SKILL_OBJECT_ROOT", t.TempDir())

	if _, err := installChatBuiltinSkillPackage(context.Background(), database.DB, "user_001", "张三", pkg); err != nil {
		t.Fatalf("installChatBuiltinSkillPackage: %v", err)
	}
	resourceContext, err := evolution.BuildChatResourceContext(
		context.Background(), database.DB, "user_001", "张三", "conversation_1_session",
	)
	if err != nil {
		t.Fatalf("BuildChatResourceContext: %v", err)
	}
	if len(resourceContext.AvailableSkills) != 1 || resourceContext.AvailableSkills[0] != "productivity/feishu" {
		t.Fatalf("available Skills=%#v, want productivity/feishu", resourceContext.AvailableSkills)
	}
}

func TestEnsureChatBuiltinSkillPreservesDisabledAndDeletedChoices(t *testing.T) {
	for _, tc := range []struct {
		name      string
		disabled  bool
		deleted   bool
		wantState autoBuiltinSkillState
	}{
		{name: "disabled", disabled: true, wantState: autoBuiltinSkillDisabledByUser},
		{name: "deleted", deleted: true, wantState: autoBuiltinSkillDeletedByUser},
	} {
		t.Run(tc.name, func(t *testing.T) {
			db := testutil.NewTestDB(t)
			testutil.SeedSkillWithRevision(t, db, "skill1", "rev1")
			updates := map[string]any{"origin_builtin_skill_uid": feishuBuiltinSkillUID}
			if tc.disabled {
				updates["is_enabled"] = false
			}
			if tc.deleted {
				now := time.Now().UTC()
				updates["deleted_at"] = now
			}
			if err := db.Model(&testutil.SkillRow{}).Where("id = ?", "skill1").Updates(updates).Error; err != nil {
				t.Fatal(err)
			}

			pkg := skillbuiltin.Package{UID: feishuBuiltinSkillUID}
			result, err := ensureChatBuiltinSkillPackage(context.Background(), db.DB, "user_001", "张三", pkg)
			if err != nil {
				t.Fatalf("ensureChatBuiltinSkill: %v", err)
			}
			if result.State != tc.wantState || result.SkillID != "skill1" {
				t.Fatalf("result=%#v, want state=%q", result, tc.wantState)
			}
		})
	}
}

func testChatBuiltinPackage(t *testing.T) skillbuiltin.Package {
	t.Helper()
	archivePath := filepath.Join(t.TempDir(), "feishu.zip")
	file, err := os.Create(archivePath)
	if err != nil {
		t.Fatal(err)
	}
	writer := zip.NewWriter(file)
	files := map[string]string{
		"SKILL.md":                         "---\nname: feishu\ndescription: 飞书文档操作\ncategory: productivity\n---\n# 飞书文档\n",
		"references/browser-ui-editing.md": "# 浏览器 UI 编辑流程\n",
	}
	for path, content := range files {
		entry, createErr := writer.Create(path)
		if createErr != nil {
			t.Fatal(createErr)
		}
		if _, writeErr := entry.Write([]byte(content)); writeErr != nil {
			t.Fatal(writeErr)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	body, err := os.ReadFile(archivePath)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(body)
	return skillbuiltin.Package{
		UID: feishuBuiltinSkillUID, Name: "feishu", Category: "productivity",
		Description: "飞书文档操作", Version: "1.0.0",
		SHA256: hex.EncodeToString(hash[:]), TreeSHA256: strings.Repeat("b", 64),
		ArchivePath: archivePath, MarketVisible: true,
	}
}
