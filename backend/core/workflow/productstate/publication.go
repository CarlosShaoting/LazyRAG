// Package productstate owns the durable publication boundary of the product workflow.
// A publication is an immutable set of revisions, independent of the working selection.
package productstate

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"gorm.io/gorm"
	"lazymind/core/common/orm"
	"lazymind/core/workflow/artifactfile"
)

const EventType = "product.published"

func Supports(id string) bool { return id == "product_solution_delivery" }

// PublicationEnabled reads the immutable package pinned to the Session, never
// the latest package or emitted artifacts. Legacy packages keep upstream behavior.
func PublicationEnabled(db *gorm.DB, session orm.WorkflowSession) (bool, error) {
	if !Supports(session.WorkflowID) || session.WorkflowRevisionID == "" {
		return false, nil
	}
	var revision orm.WorkflowRevision
	if err := db.Select("compiled_graph").First(&revision, "id = ?", session.WorkflowRevisionID).Error; err != nil {
		return false, err
	}
	var graph struct {
		Runtime struct {
			PublisherOwnedSlots []string `json:"publisher_owned_slots"`
		} `json:"runtime"`
	}
	if err := json.Unmarshal(revision.CompiledGraph, &graph); err != nil {
		return false, err
	}
	workspace, manifest := false, false
	for _, slot := range graph.Runtime.PublisherOwnedSlots {
		workspace = workspace || slot == "workspace_state"
		manifest = manifest || slot == "stage_manifest"
	}
	return workspace && manifest, nil
}

type Publication struct {
	AttemptID   string            `json:"attempt_id"`
	Stage       string            `json:"stage"`
	WorkspaceID string            `json:"workspace_id"`
	Revisions   map[string]string `json:"revisions"`
	Hashes      map[string]string `json:"hashes"`
}

func Latest(db *gorm.DB, sessionID string) (Publication, error) {
	var event orm.WorkflowEvent
	err := db.Where("session_id = ? AND event_type = ?", sessionID, EventType).Order("id DESC").First(&event).Error
	var value Publication
	if err == nil {
		err = json.Unmarshal(event.PayloadJSON, &value)
	}
	return value, err
}

func Record(db *gorm.DB, session orm.WorkflowSession, value Publication) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return db.Create(&orm.WorkflowEvent{SessionID: session.ID, OwnerUserID: session.CreateUserID,
		ContractVersion: "workflow.v1", EventType: EventType, EntityID: value.AttemptID,
		StateVersion: session.StateVersion + 1, PayloadJSON: raw, CreatedAt: time.Now().UTC()}).Error
}

// Bytes accepts only persisted content and managed files whose digest is verified by Inline.
// Legacy workspace paths are handled by the repository's owner-scoped compatibility reader.
func Bytes(db *gorm.DB, revision orm.WorkflowSlotRevision) ([]byte, error) {
	raw := revision.ContentSnapshot
	if revision.HumanArtifactID != nil {
		var artifact orm.WorkflowHumanArtifact
		if err := db.First(&artifact, "id = ?", *revision.HumanArtifactID).Error; err != nil {
			return nil, err
		}
		raw = artifact.Value
	}
	inlined, err := artifactfile.Inline(raw)
	if err != nil {
		return nil, err
	}
	var value any
	if err = json.Unmarshal(inlined, &value); err != nil {
		return nil, err
	}
	for n := 0; n < 4; n++ {
		switch v := value.(type) {
		case string:
			return []byte(v), nil
		case map[string]any:
			if b64, ok := v["content_base64"].(string); ok {
				return base64.StdEncoding.Strict().DecodeString(b64)
			}
			if _, ok := v["path"]; ok {
				return nil, errors.New("PRODUCT_ARTIFACT_NOT_FROZEN")
			}
			if data, ok := v["data"]; ok && len(v) <= 3 {
				value = data
				continue
			}
			if text, ok := v["text"]; ok && len(v) <= 3 {
				value = text
				continue
			}
		}
		return json.Marshal(value)
	}
	return nil, errors.New("PRODUCT_ARTIFACT_INVALID")
}

func digest(raw []byte) string { return fmt.Sprintf("%x", sha256.Sum256(raw)) }
func object(raw []byte) (map[string]any, error) {
	var value map[string]any
	err := json.Unmarshal(raw, &value)
	if err == nil && value == nil {
		err = errors.New("PRODUCT_PUBLICATION_INVALID")
	}
	return value, err
}

// Publish runs inside the Attempt completion transaction, after output validation.
// Its input bindings freeze the body/HTML/assessment used by this finalizer. A failed
// finalizer cannot replace this event, and a retry of a terminal Attempt cannot append it twice.
func Publish(db *gorm.DB, session orm.WorkflowSession, attempt orm.WorkflowSessionStep) error {
	pub := Publication{AttemptID: attempt.ID, Revisions: map[string]string{}, Hashes: map[string]string{}}
	contents := map[string][]byte{}
	var bindings []orm.WorkflowAttemptInputBinding
	if err := db.Where("attempt_id = ? AND source_type = 'artifact'", attempt.ID).Find(&bindings).Error; err != nil {
		return err
	}
	for _, binding := range bindings {
		if binding.MaterialID == "workspace_seed" {
			continue
		}
		var row orm.WorkflowSlotRevision
		if err := db.Where("id = ? AND session_id = ?", binding.MaterialRevisionID, session.ID).First(&row).Error; err != nil {
			return err
		}
		if row.Validity != "effective" {
			return errors.New("PRODUCT_PUBLICATION_INPUT_CHANGED")
		}
		bytes, err := Bytes(db, row)
		if err != nil {
			return err
		}
		pub.Revisions[row.SlotID] = row.ID
		pub.Hashes[row.SlotID] = digest(bytes)
		contents[row.SlotID] = bytes
	}
	var outputs []orm.WorkflowSlotRevision
	if err := db.Where("producer_attempt_id = ? AND validity = 'effective'", attempt.ID).Order("revision ASC").Find(&outputs).Error; err != nil {
		return err
	}
	for _, row := range outputs {
		bytes, err := Bytes(db, row)
		if err != nil {
			return err
		}
		pub.Revisions[row.SlotID] = row.ID
		pub.Hashes[row.SlotID] = digest(bytes)
		contents[row.SlotID] = bytes
	}
	for _, slot := range []string{"workspace_state", "stage_manifest", "delivery_summary"} {
		if len(contents[slot]) == 0 {
			return fmt.Errorf("PRODUCT_PUBLICATION_INCOMPLETE: %s", slot)
		}
	}
	manifest, err := object(contents["stage_manifest"])
	if err != nil {
		return err
	}
	workspace, err := object(contents["workspace_state"])
	if err != nil {
		return err
	}
	pub.Stage, _ = manifest["stage"].(string)
	pub.WorkspaceID, _ = workspace["workspace_id"].(string)
	pairs := map[string][]string{
		"direction": {"direction_document", "direction_document_html"}, "competitive": {"competitive_analysis", "competitive_analysis_markdown"},
		"design": {"design_document", "design_document_html"}, "prd": {"prd_document", "prd_document_html"},
		"prototype": {"prototype", "prototype_markdown"}, "review": {"review_document", "review_document_html"}, "handoff": {"handoff_document", "handoff_document_html"},
	}
	run, _ := workspace["current_run"].(map[string]any)
	if run["selected_stage"] != pub.Stage || manifest["workspace_id"] != pub.WorkspaceID {
		return errors.New("PRODUCT_PUBLICATION_INVALID")
	}
	pair, ok := pairs[pub.Stage]
	if !ok || pub.WorkspaceID == "" {
		return errors.New("PRODUCT_PUBLICATION_INVALID")
	}
	for _, slot := range append(pair, pub.Stage+"_assessment") {
		if len(contents[slot]) == 0 {
			return fmt.Errorf("PRODUCT_PUBLICATION_INCOMPLETE: %s", slot)
		}
	}
	host, _ := manifest["host_artifact"].(map[string]any)
	slot, _ := host["slot"].(string)
	expected, _ := host["content_sha256"].(string)
	if slot != pair[0] || expected == "" || pub.Hashes[slot] != strings.TrimPrefix(expected, "sha256:") {
		return errors.New("PRODUCT_PUBLICATION_CONTENT_MISMATCH")
	}
	if representations, ok := manifest["representations"].(map[string]any); ok {
		for _, raw := range representations {
			rep, _ := raw.(map[string]any)
			slot, _ := rep["slot"].(string)
			hash, _ := rep["content_sha256"].(string)
			if hash != "" && pub.Hashes[slot] != strings.TrimPrefix(hash, "sha256:") {
				return errors.New("PRODUCT_PUBLICATION_CONTENT_MISMATCH")
			}
		}
	}
	return Record(db, session, pub)
}
