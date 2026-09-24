package store

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/doc"
	"lazymind/core/subagent"
)

func productHostedFileFixture(t *testing.T) (*Repository, orm.WorkflowSession, Artifact, string) {
	t.Helper()
	r := productProjectFixture(t)
	uploadRoot := t.TempDir()
	t.Setenv("LAZYMIND_UPLOAD_ROOT", uploadRoot)
	t.Setenv("LAZYMIND_SUBAGENT_WORKSPACE", t.TempDir())
	var session orm.WorkflowSession
	r.db.First(&session, "id = 'source'")
	attempt := orm.WorkflowSessionStep{ID: "pss_native-attempt", SessionID: session.ID, StepID: "write_direction_document", Attempt: 1, TaskID: "", Status: "succeeded", Validity: "effective"}
	if err := r.db.Create(&attempt).Error; err != nil {
		t.Fatal(err)
	}
	root := filepath.Join(uploadRoot, "workflow-artifacts", session.ID, attempt.ID)
	if err := os.MkdirAll(root, 0o750); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, "draft_document-1234.md")
	content := []byte("Exact approved file bytes, not a generated summary")
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
	value, _ := json.Marshal(map[string]any{"path": path, "size": len(content), "filename": filepath.Base(path)})
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'business-r7'").Updates(map[string]any{"step_id": attempt.StepID, "attempt": attempt.Attempt, "producer_attempt_id": attempt.ID, "content_snapshot": value}).Error; err != nil {
		t.Fatal(err)
	}
	artifact, err := r.ReadArtifact(context.Background(), "owner", "business-r7")
	if err != nil {
		t.Fatal(err)
	}
	return r, session, artifact, root
}

func TestProductArtifactReadsNativeHostedUploadWithoutManagedTag(t *testing.T) {
	r, session, artifact, _ := productHostedFileFixture(t)
	name, kind, content, err := r.productArtifactBytes(context.Background(), session, artifact)
	if err != nil || name != "draft_document-1234.md" || !strings.HasPrefix(kind, "text/markdown") || string(content) != "Exact approved file bytes, not a generated summary" {
		t.Fatalf("native hosted file cannot be read: %s %s %q %v", name, kind, content, err)
	}
	preview, err := r.ProductProjectArtifact(context.Background(), "owner", session.ID, "direction")
	if err != nil || preview["available"] != true || preview["content"] != string(content) {
		t.Fatalf("native preview unavailable: %#v %v", preview, err)
	}
	next := productRelayTo(t, r, session.ID, "design", "native-file-relay", 9)
	if productBoundContents(t, r, next)["upstream_direction"] != string(content) {
		t.Fatal("native file bytes were not relayed")
	}
}

func TestProductRelayReadsOffloadedWorkspaceState(t *testing.T) {
	r := productRelayFixture(t)
	uploadRoot := t.TempDir()
	t.Setenv("LAZYMIND_UPLOAD_ROOT", uploadRoot)
	t.Setenv("LAZYMIND_SUBAGENT_WORKSPACE", t.TempDir())

	attempt := orm.WorkflowSessionStep{
		ID: "pss_workspace-attempt", SessionID: "source", StepID: "finalize_product_delivery",
		Attempt: 1, Status: "succeeded", Validity: "effective",
	}
	if err := r.db.Create(&attempt).Error; err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(uploadRoot, "workflow-artifacts", "source", attempt.ID)
	if err := os.MkdirAll(directory, 0o750); err != nil {
		t.Fatal(err)
	}
	workspacePath := filepath.Join(directory, "workspace-state.json")
	workspace := []byte(`{"workspace_id":"stable-project","current_run":{"selected_stage":"direction","run_status":"awaiting-stage-confirmation"},"artifacts":[]}`)
	if err := os.WriteFile(workspacePath, workspace, 0o600); err != nil {
		t.Fatal(err)
	}
	value, _ := json.Marshal(map[string]any{
		"type": "json", "path": workspacePath, "size": len(workspace),
	})
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Updates(map[string]any{
		"step_id": attempt.StepID, "attempt": attempt.Attempt,
		"producer_attempt_id": attempt.ID, "content_snapshot": value,
	}).Error; err != nil {
		t.Fatal(err)
	}

	summary, err := r.ProductRelaySummary(context.Background(), "owner", "source")
	if err != nil || summary["can_relay"] != true || summary["current_stage"] != "direction" {
		t.Fatalf("offloaded Workspace was not decoded: %#v %v", summary, err)
	}
}

func TestProductArtifactReadsHostedShapeWithHumanArtifactStorage(t *testing.T) {
	r, session, artifact, _ := productHostedFileFixture(t)
	humanID := "hosted-human-storage"
	if err := r.db.Create(&orm.WorkflowHumanArtifact{
		ID: humanID, SessionID: session.ID, Slot: artifact.Slot, ContentType: "file",
		Value: artifact.Value, CreatedAt: time.Now().UTC(),
	}).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", artifact.ID).Updates(map[string]any{
		"human_artifact_id": humanID, "change_source": "host", "content_snapshot": nil,
	}).Error; err != nil {
		t.Fatal(err)
	}
	stored, err := r.ReadArtifact(context.Background(), "owner", artifact.ID)
	if err != nil {
		t.Fatal(err)
	}
	_, _, content, err := r.productArtifactBytes(context.Background(), session, stored)
	if err != nil || string(content) != "Exact approved file bytes, not a generated summary" {
		t.Fatalf("host-managed human row regressed: %q %v", content, err)
	}
}

func productHumanUploadFixture(t *testing.T) (*Repository, orm.WorkflowSession, Artifact, string, []byte) {
	t.Helper()
	r := productProjectFixture(t)
	uploadRoot := t.TempDir()
	t.Setenv("LAZYMIND_UPLOAD_ROOT", uploadRoot)
	var session orm.WorkflowSession
	if err := r.db.First(&session, "id = 'source'").Error; err != nil {
		t.Fatal(err)
	}
	uploadID := "upload_editor_save"
	directory := filepath.Join(doc.TempUserFilesRoot(session.CreateUserID), uploadID)
	if err := os.MkdirAll(directory, 0o750); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "direction-edited.md")
	content := []byte("Human-edited direction shared with every stage")
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	metadata, _ := json.Marshal(map[string]any{
		"upload_id": uploadID, "stored_name": filepath.Base(path), "file_size": len(content),
		"upload_state": "UPLOADED", "upload_scope": "TEMP", "create_user_id": session.CreateUserID,
	})
	if err := r.db.Create(&orm.UploadSession{
		UploadID: uploadID, UploadState: "UPLOADED", Ext: metadata,
		BaseModel: orm.BaseModel{CreateUserID: session.CreateUserID, CreateUserName: "Owner", CreatedAt: now, UpdatedAt: now},
	}).Error; err != nil {
		t.Fatal(err)
	}
	value, _ := json.Marshal(map[string]any{"path": path, "filename": filepath.Base(path), "size": len(content)})
	humanID := "human-editor-save"
	if err := r.db.Create(&orm.WorkflowHumanArtifact{
		ID: humanID, SessionID: session.ID, Slot: "direction_document", ContentType: "file", Value: value, CreatedAt: now,
	}).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'business-r7'").Update("selected", false).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Create(&orm.WorkflowSlotRevision{
		ID: "business-human-r8", SessionID: session.ID, SlotID: "direction_document", Slot: "direction_document",
		Revision: 8, Selected: true, HumanArtifactID: &humanID, ChangeSource: "human", Validity: "effective", CreatedAt: now,
	}).Error; err != nil {
		t.Fatal(err)
	}
	artifact, err := r.ReadArtifact(context.Background(), session.CreateUserID, "business-human-r8")
	if err != nil {
		t.Fatal(err)
	}
	return r, session, artifact, path, content
}

func TestProductHumanEditBecomesSharedDraftAndRelaysExactBytes(t *testing.T) {
	r, session, artifact, _, content := productHumanUploadFixture(t)
	var workspaceRevision orm.WorkflowSlotRevision
	if err := r.db.First(&workspaceRevision, "id = 'workspace-r1'").Error; err != nil {
		t.Fatal(err)
	}
	workspace := productObject(workspaceRevision.ContentSnapshot)
	workspace["artifacts"] = append(workspace["artifacts"].([]any), map[string]any{
		"artifact_id": "design-v1", "artifact_type": "product-design-spec", "title": "产品方案",
		"version": "1.0", "status": "accepted", "implementation_readiness": "not-assessed",
		"dependencies":  []any{map[string]any{"artifact_id": "direction-v1", "status": "available"}},
		"host_artifact": map[string]any{"slot": "design_document", "source_session_id": "prior-design", "content_sha256": "old-design"},
	})
	encodedWorkspace, _ := json.Marshal(workspace)
	if err := r.db.Model(&workspaceRevision).Update("content_snapshot", encodedWorkspace).Error; err != nil {
		t.Fatal(err)
	}
	name, kind, loaded, err := r.productArtifactBytes(context.Background(), session, artifact)
	if err != nil || name != "direction-edited.md" || !strings.HasPrefix(kind, "text/markdown") || string(loaded) != string(content) {
		t.Fatalf("saved editor revision cannot be read: %s %s %q %v", name, kind, loaded, err)
	}
	preview, err := r.ProductProjectArtifact(context.Background(), "owner", session.ID, "direction")
	if err != nil || preview["content"] != string(content) || preview["status"] != "draft" || preview["version"] != "working-r8" {
		t.Fatalf("edited source was not projected as a draft: %#v %v", preview, err)
	}
	summary, err := r.ProductRelaySummary(context.Background(), "owner", session.ID)
	if err != nil || summary["can_relay"] != true || summary["can_accept_current_artifact"] != false || summary["artifacts"].([]map[string]any)[0]["version"] != "working-r8" {
		t.Fatalf("relay summary did not expose the usable edited draft: %#v %v", summary, err)
	}
	next := productRelayTo(t, r, session.ID, "design", "relay-human-edit", 9)
	inputs := productBoundContents(t, r, next)
	if inputs["upstream_direction"] != string(content) {
		t.Fatalf("successor did not receive exact edited bytes: %q", inputs["upstream_direction"])
	}
	seed := productObject(json.RawMessage(inputs["workspace_seed"]))
	if seed["workspace_id"] != "stable-project" {
		t.Fatalf("relay changed the project workspace: %#v", seed["workspace_id"])
	}
	var historical, draft, downstream map[string]any
	for _, raw := range seed["artifacts"].([]any) {
		entry := raw.(map[string]any)
		if entry["artifact_id"] == "direction-v1" {
			historical = entry
		}
		host, _ := entry["host_artifact"].(map[string]any)
		if host["revision_id"] == artifact.ID {
			draft = entry
		}
		if entry["artifact_id"] == "design-v1" {
			downstream = entry
		}
	}
	if historical["status"] != "superseded" || draft["status"] != "draft" || draft["version"] != "1.1" || draft["supersedes"] != "direction-v1" {
		t.Fatalf("edited version lifecycle is wrong: historical=%#v draft=%#v", historical, draft)
	}
	if draft["accepted_by"] != nil || draft["checks"].(map[string]any) == nil || draft["host_artifact"].(map[string]any)["content_sha256"] != requestHash(content) {
		t.Fatalf("draft inherited acceptance/checks or lost its exact digest: %#v", draft)
	}
	if downstream["status"] != "needs-update" || downstream["implementation_readiness"] != "blocked" || downstream["dependencies"].([]any)[0].(map[string]any)["status"] != "outdated" {
		t.Fatalf("downstream dependency was not invalidated: %#v", downstream)
	}
	shared, err := r.ProductProjectArtifact(context.Background(), "owner", next, "direction")
	if err != nil || shared["content"] != string(content) || shared["version"] != "1.1" || shared["status"] != "draft" {
		t.Fatalf("successor cannot use the shared draft: %#v %v", shared, err)
	}
}

func TestProductHumanUploadRequiresExactCompletedOwnerUpload(t *testing.T) {
	for _, name := range []string{"missing-upload", "unfinished-upload", "wrong-scope", "wrong-name", "wrong-size", "different-owner-root", "file-symlink"} {
		t.Run(name, func(t *testing.T) {
			r, session, artifact, path, _ := productHumanUploadFixture(t)
			switch name {
			case "missing-upload":
				r.db.Where("upload_id = 'upload_editor_save'").Delete(&orm.UploadSession{})
			case "unfinished-upload":
				r.db.Model(&orm.UploadSession{}).Where("upload_id = 'upload_editor_save'").Update("upload_state", "UPLOADING")
			case "wrong-scope", "wrong-name", "wrong-size":
				var upload orm.UploadSession
				r.db.First(&upload, "upload_id = 'upload_editor_save'")
				var metadata map[string]any
				json.Unmarshal(upload.Ext, &metadata)
				if name == "wrong-scope" {
					metadata["upload_scope"] = "DATASET"
				}
				if name == "wrong-name" {
					metadata["stored_name"] = "other.md"
				}
				if name == "wrong-size" {
					metadata["file_size"] = 1
				}
				encoded, _ := json.Marshal(metadata)
				r.db.Model(&upload).Update("ext", encoded)
			case "different-owner-root":
				otherDirectory := filepath.Join(doc.TempUserFilesRoot("another-owner"), "upload_other")
				if err := os.MkdirAll(otherDirectory, 0o750); err != nil {
					t.Fatal(err)
				}
				path = filepath.Join(otherDirectory, "other.md")
				if err := os.WriteFile(path, []byte("other"), 0o600); err != nil {
					t.Fatal(err)
				}
				value, _ := json.Marshal(map[string]any{"path": path})
				r.db.Model(&orm.WorkflowHumanArtifact{}).Where("id = 'human-editor-save'").Update("value", value)
				artifact, _ = r.ReadArtifact(context.Background(), "owner", artifact.ID)
			case "file-symlink":
				outside := filepath.Join(t.TempDir(), "outside.md")
				if err := os.WriteFile(outside, []byte("outside"), 0o600); err != nil {
					t.Fatal(err)
				}
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(outside, path); err != nil {
					t.Fatal(err)
				}
			}
			if _, _, _, err := r.productArtifactBytes(context.Background(), session, artifact); err == nil || err.Error() != "PRODUCT_ARTIFACT_PATH_INVALID" {
				t.Fatalf("unsafe human upload accepted: %s: %v", name, err)
			}
		})
	}
}

func TestProductArtifactRejectsOtherHostedScopeAndSymlinkEscapes(t *testing.T) {
	for _, name := range []string{"other-session", "other-attempt", "producer-mismatch", "missing-producer", "traversal", "file-symlink", "attempt-directory-symlink"} {
		t.Run(name, func(t *testing.T) {
			r, session, artifact, root := productHostedFileFixture(t)
			path := filepath.Join(root, "draft_document-1234.md")
			switch name {
			case "other-session":
				path = filepath.Join(filepath.Dir(filepath.Dir(root)), "other-session", artifact.ProducerAttemptID, "outside.md")
			case "other-attempt":
				path = filepath.Join(filepath.Dir(root), "pss_other-attempt", "outside.md")
			case "producer-mismatch":
				artifact.ProducerAttemptID = "pss_other-attempt"
			case "missing-producer":
				artifact.ProducerAttemptID = ""
			case "traversal":
				path = root + "/../" + artifact.ProducerAttemptID + "/draft_document-1234.md"
			case "file-symlink", "attempt-directory-symlink":
				outside := t.TempDir()
				outsideFile := filepath.Join(outside, "draft_document-1234.md")
				if err := os.WriteFile(outsideFile, []byte("outside file"), 0o600); err != nil {
					t.Fatal(err)
				}
				if name == "file-symlink" {
					path = filepath.Join(root, "escape.md")
					if err := os.Symlink(outsideFile, path); err != nil {
						t.Fatal(err)
					}
				} else {
					if err := os.Rename(root, root+"-original"); err != nil {
						t.Fatal(err)
					}
					if err := os.Symlink(outside, root); err != nil {
						t.Fatal(err)
					}
				}
			}
			if name == "other-session" || name == "other-attempt" {
				if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(path, []byte("another scope's file"), 0o600); err != nil {
					t.Fatal(err)
				}
			}
			artifact.Value, _ = json.Marshal(map[string]any{"path": path, "filename": filepath.Base(path), "size": 1})
			if _, _, _, err := r.productArtifactBytes(context.Background(), session, artifact); err == nil || err.Error() != "PRODUCT_ARTIFACT_PATH_INVALID" {
				t.Fatalf("unsafe hosted path accepted: %s: %v", name, err)
			}
		})
	}
}

func TestProductArtifactStillReadsPersistedLocalTaskWorkspace(t *testing.T) {
	r, session, artifact, _ := productHostedFileFixture(t)
	artifact.ProducerAttemptID = ""
	r.db.Model(&orm.WorkflowSessionStep{}).Where("id = 'pss_native-attempt'").Update("task_id", "local-task")
	root := subagent.WorkspacePath(session.CreateUserID, "local-task")
	if err := os.MkdirAll(root, 0o750); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, "local.md")
	if err := os.WriteFile(path, []byte("local task content"), 0o600); err != nil {
		t.Fatal(err)
	}
	artifact.Value, _ = json.Marshal(map[string]any{"path": path})
	_, _, content, err := r.productArtifactBytes(context.Background(), session, artifact)
	if err != nil || string(content) != "local task content" {
		t.Fatalf("local workspace regression: %q %v", content, err)
	}
}
