package chat

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
	appLog "lazymind/core/log"
	"lazymind/core/settings"
	skillbuiltin "lazymind/core/skillv2/builtin"
	skillservice "lazymind/core/skillv2/service"
)

const feishuBuiltinSkillUID = "bsk_01M1FEISHUDOCS8R4K2V7Q9X0A"

// TODO(skill-auto-provision): replace this Feishu-only routing with a generic,
// catalog-driven intent matcher after the Chat resource selection contract can
// safely distinguish relevant Skills without installing false positives.

type autoBuiltinSkillState string

const (
	autoBuiltinSkillInstalled      autoBuiltinSkillState = "installed"
	autoBuiltinSkillAlreadyEnabled autoBuiltinSkillState = "already_enabled"
	autoBuiltinSkillDisabledByUser autoBuiltinSkillState = "disabled_by_user"
	autoBuiltinSkillDeletedByUser  autoBuiltinSkillState = "deleted_by_user"
)

type autoBuiltinSkillResult struct {
	SkillID string
	State   autoBuiltinSkillState
}

// autoConfigureChatSkills installs narrowly matched builtin Skills before the
// resource snapshot for the current turn is built. Existing disabled or deleted
// installations are deliberately preserved as explicit user choices.
func autoConfigureChatSkills(ctx context.Context, db *gorm.DB, userID, userName, query string) error {
	if !isFeishuChatIntent(query) {
		return nil
	}
	controls, err := settings.LoadFeatureControls(ctx, db, userID)
	if err != nil {
		return fmt.Errorf("load Skill feature control: %w", err)
	}
	if !controls.SkillsEnabled {
		appLog.Logger.Info().
			Str("user_id", userID).
			Str("builtin_skill_uid", feishuBuiltinSkillUID).
			Msg("skipped chat Skill auto-configuration because Skills are disabled")
		return nil
	}
	pkg, found, err := skillbuiltin.PackageByUID(feishuBuiltinSkillUID)
	if err != nil {
		return fmt.Errorf("load builtin Skill package: %w", err)
	}
	if !found {
		return fmt.Errorf("builtin Skill %s was not found", feishuBuiltinSkillUID)
	}
	result, err := ensureChatBuiltinSkillPackage(ctx, db, userID, userName, pkg)
	if err != nil {
		return err
	}
	appLog.Logger.Info().
		Str("user_id", userID).
		Str("builtin_skill_uid", pkg.UID).
		Str("skill_name", pkg.Name).
		Str("skill_id", result.SkillID).
		Str("state", string(result.State)).
		Msg("auto-configured builtin Skill for chat intent")
	return nil
}

func isFeishuChatIntent(query string) bool {
	normalized := strings.ToLower(strings.TrimSpace(query))
	if normalized == "" {
		return false
	}
	for _, marker := range []string{
		"feishu.cn", "larksuite.com", "飞书", "feishu",
		"lark doc", "lark wiki", "lark sheet", "lark base",
	} {
		if strings.Contains(normalized, marker) {
			return true
		}
	}
	return false
}

func ensureChatBuiltinSkillPackage(ctx context.Context, db *gorm.DB, userID, userName string, pkg skillbuiltin.Package) (autoBuiltinSkillResult, error) {
	userID = strings.TrimSpace(userID)
	uid := strings.TrimSpace(pkg.UID)
	if db == nil || userID == "" || uid == "" {
		return autoBuiltinSkillResult{}, fmt.Errorf("auto-configure builtin Skill requires database, user and Skill identity")
	}

	if existing, found, err := findChatBuiltinSkill(ctx, db, userID, uid, false); err != nil {
		return autoBuiltinSkillResult{}, err
	} else if found {
		state := autoBuiltinSkillAlreadyEnabled
		if !existing.IsEnabled {
			state = autoBuiltinSkillDisabledByUser
		}
		return autoBuiltinSkillResult{SkillID: existing.ID, State: state}, nil
	}
	if deleted, found, err := findChatBuiltinSkill(ctx, db, userID, uid, true); err != nil {
		return autoBuiltinSkillResult{}, err
	} else if found {
		return autoBuiltinSkillResult{SkillID: deleted.ID, State: autoBuiltinSkillDeletedByUser}, nil
	}

	return installChatBuiltinSkillPackage(ctx, db, userID, userName, pkg)
}

func installChatBuiltinSkillPackage(ctx context.Context, db *gorm.DB, userID, userName string, pkg skillbuiltin.Package) (autoBuiltinSkillResult, error) {
	if strings.TrimSpace(pkg.ArchivePath) == "" {
		return autoBuiltinSkillResult{}, fmt.Errorf("builtin Skill %s has no bundled archive", pkg.UID)
	}
	enabled := true
	service := skillservice.NewSkillService(skillservice.SkillServiceDeps{
		DB: db,
		BlobStore: skillservice.NewBlobStore(
			db,
			skillservice.NewLocalObjectStore(chatSkillObjectRoot()),
		),
	})
	created, err := service.CreateSkill(ctx, skillservice.CreateSkillRequest{
		OwnerUserID:           userID,
		OwnerUserName:         userName,
		CreateUserID:          userID,
		CreateUserName:        userName,
		Name:                  pkg.Name,
		Category:              pkg.Category,
		OriginBuiltinSkillUID: pkg.UID,
		Description:           pkg.Description,
		Tags:                  pkg.Tags,
		IsEnabled:             &enabled,
		Source: skillservice.SourceInput{
			Type:       "builtin_zip",
			StoredPath: pkg.ArchivePath,
			Filename:   fmt.Sprintf("%s@%s#%s", pkg.UID, pkg.Version, pkg.SHA256),
		},
		Distribution: &skillservice.DistributionSource{
			BuiltinUID: pkg.UID, Version: pkg.Version, ArchiveSHA256: pkg.SHA256, TreeSHA256: pkg.TreeSHA256,
		},
	})
	if err == nil {
		return autoBuiltinSkillResult{SkillID: created.SkillID, State: autoBuiltinSkillInstalled}, nil
	}

	// Concurrent chat requests may both observe a missing install. Treat the
	// winner's row as success instead of surfacing a uniqueness race.
	existing, found, lookupErr := findChatBuiltinSkill(ctx, db, userID, pkg.UID, false)
	if lookupErr == nil && found {
		state := autoBuiltinSkillAlreadyEnabled
		if !existing.IsEnabled {
			state = autoBuiltinSkillDisabledByUser
		}
		return autoBuiltinSkillResult{SkillID: existing.ID, State: state}, nil
	}
	return autoBuiltinSkillResult{}, fmt.Errorf("install builtin Skill %s: %w", pkg.UID, err)
}

func findChatBuiltinSkill(ctx context.Context, db *gorm.DB, userID, uid string, deleted bool) (orm.SkillV2Skill, bool, error) {
	var skill orm.SkillV2Skill
	query := db.WithContext(ctx).
		Where("owner_user_id = ? AND origin_builtin_skill_uid = ?", userID, uid)
	if deleted {
		query = query.Where("deleted_at IS NOT NULL").Order("deleted_at DESC, created_at ASC")
	} else {
		query = query.Where("deleted_at IS NULL").Order("created_at ASC")
	}
	err := query.Take(&skill).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return orm.SkillV2Skill{}, false, nil
	}
	if err != nil {
		return orm.SkillV2Skill{}, false, err
	}
	return skill, true, nil
}

func chatSkillObjectRoot() string {
	if value := strings.TrimSpace(os.Getenv("LAZYMIND_SKILL_OBJECT_ROOT")); value != "" {
		return strings.TrimRight(value, "/")
	}
	uploadRoot := strings.TrimSpace(os.Getenv("LAZYMIND_UPLOAD_ROOT"))
	if uploadRoot == "" {
		uploadRoot = "/var/lib/lazymind/uploads"
	}
	return filepath.Join(strings.TrimRight(uploadRoot, "/"), "skill-objects")
}
