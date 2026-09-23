package store

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"lazymind/core/common/orm"
	"lazymind/core/workflow/graphengine"
)

// ProductRestartRequest is an optimistic, idempotent request to clone a failed
// product session onto the currently published workflow revision.
type ProductRestartRequest struct {
	IdempotencyKey       string `json:"idempotency_key"`
	ExpectedStateVersion int64  `json:"expected_state_version"`
}

func productWorkflowID(id string) bool {
	return id == "product_solution_delivery" || id == "product-solution-delivery"
}

func productStageForSlot(slot string) string {
	for _, stage := range productStages {
		if stage.Slot == slot || stage.HTMLSlot == slot || stage.MarkdownSlot == slot {
			return stage.ID
		}
	}
	return ""
}

func productRestartGraph(pkg WorkflowPackage) (*graphengine.CompiledStateGraph, map[string]bool, error) {
	var graph graphengine.CompiledStateGraph
	if json.Unmarshal(pkg.CompiledGraph, &graph) != nil || graph.MaterialProducers == nil || len(graph.Nodes) == 0 || len(graph.ControlEdges) == 0 ||
		graph.SchemaVersion != graphengine.SchemaVersion || graph.SchemaVersion != pkg.GraphVersion || graph.GraphHash == "" || graph.GraphHash != pkg.GraphHash {
		return nil, nil, repositoryError("PRODUCT_RESTART_REVISION_UNSUPPORTED")
	}
	external := make(map[string]bool, len(graph.MaterialProducers))
	for material, producer := range graph.MaterialProducers {
		external[material] = producer.Kind == "external"
	}
	return &graph, external, nil
}

func productRestartBindingCommand(key, suffix string) string {
	digest := requestHash([]byte(key + ":" + suffix))
	return "product-restart:" + digest[:32]
}

func removeProductRestartMaterial(bindings []InputBinding, material string) []InputBinding {
	kept := bindings[:0]
	for _, binding := range bindings {
		if binding.MaterialID != material {
			kept = append(kept, binding)
		}
	}
	return kept
}

func addProductRestartLineage(workspace map[string]any, session orm.WorkflowSession, artifact Artifact, material string, resource InputResource) {
	lineage, _ := workspace["host_artifact_bindings"].([]any)
	kept := make([]any, 0, len(lineage)+1)
	for _, raw := range lineage {
		entry, _ := raw.(map[string]any)
		if entry["material_id"] != material {
			kept = append(kept, raw)
		}
	}
	workspace["host_artifact_bindings"] = append(kept, map[string]any{
		"material_id": material, "slot_id": artifact.SlotID, "source_session_id": session.ID,
		"revision_id": artifact.ID, "revision": artifact.Revision, "content_hash": resource.ContentHash,
		"resource_id": resource.ID,
	})
}

func removeProductRestartLineage(workspace map[string]any, material, slot string) {
	lineage, _ := workspace["host_artifact_bindings"].([]any)
	kept := make([]any, 0, len(lineage))
	for _, raw := range lineage {
		entry, _ := raw.(map[string]any)
		if entry["material_id"] != material {
			kept = append(kept, raw)
		}
	}
	workspace["host_artifact_bindings"] = kept
	registered, _ := workspace["artifacts"].([]any)
	changed := map[string]bool{}
	for _, raw := range registered {
		entry, _ := raw.(map[string]any)
		host, _ := entry["host_artifact"].(map[string]any)
		if host["slot"] == slot && entry["status"] != "superseded" {
			entry["status"], entry["implementation_readiness"] = "superseded", "blocked"
			changed[productString(entry["artifact_id"])] = true
		}
	}
	seen := map[string]bool{}
	for len(changed) != 0 {
		next := map[string]bool{}
		for _, raw := range registered {
			entry, _ := raw.(map[string]any)
			id := productString(entry["artifact_id"])
			if id == "" || seen[id] || entry["status"] == "superseded" {
				continue
			}
			dependencies, _ := entry["dependencies"].([]any)
			for _, rawDependency := range dependencies {
				dependency, _ := rawDependency.(map[string]any)
				if changed[productString(dependency["artifact_id"])] {
					dependency["status"] = "outdated"
					entry["status"], entry["implementation_readiness"] = "needs-update", "blocked"
					next[id] = true
				}
			}
		}
		for id := range changed {
			seen[id] = true
		}
		changed = next
	}
}

// RestartProductWorkflowOnLatest leaves the immutable execution record pinned
// to its original revision and creates a fresh Session on the current head.
func (r *Repository) RestartProductWorkflowOnLatest(ctx context.Context, owner, sourceID string, req ProductRestartRequest) (json.RawMessage, error) {
	if err := r.AuthorizeSession(ctx, sourceID, owner); err != nil {
		return nil, err
	}
	if strings.TrimSpace(req.IdempotencyKey) == "" || len(req.IdempotencyKey) > 128 || req.ExpectedStateVersion < 1 {
		return nil, repositoryError("INVALID_PRODUCT_RESTART")
	}
	body, _ := json.Marshal(map[string]any{"session_id": sourceID, "request": req})
	r.commandMu.Lock()
	defer r.commandMu.Unlock()
	command, _, err := r.commandTransactional(ctx, owner, sourceID, req.IdempotencyKey, "workflow.v1", body, func(tx *gorm.DB) (int, json.RawMessage, error) {
		txRepo := New(tx)
		var source orm.WorkflowSession
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&source, "id = ?", sourceID).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return 0, nil, ErrNotFound
			}
			return 0, nil, err
		}
		if source.CreateUserID != owner {
			return 0, nil, ErrPermissionDenied
		}
		if !productWorkflowID(source.WorkflowID) {
			return 0, nil, repositoryError("PRODUCT_RESTART_UNSUPPORTED")
		}
		if source.StateVersion != req.ExpectedStateVersion {
			return 0, nil, repositoryError("STATE_VERSION_CONFLICT")
		}
		if source.Status != "failed" || source.Dismissed {
			return 0, nil, repositoryError("PRODUCT_RESTART_NOT_ALLOWED")
		}
		pkg, err := txRepo.GetWorkflowPackage(ctx, owner, source.WorkflowID, "")
		if err != nil {
			return 0, nil, err
		}
		if pkg.RevisionID == source.WorkflowRevisionID {
			return 0, nil, repositoryError("PRODUCT_WORKFLOW_ALREADY_CURRENT")
		}
		graph, external, err := productRestartGraph(pkg)
		if err != nil {
			return 0, nil, err
		}
		var conversation struct{ ID string }
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Table("conversations").Select("id").
			Where("id = ? AND create_user_id = ?", source.ConversationID, owner).Take(&conversation).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return 0, nil, ErrPermissionDenied
			}
			return 0, nil, err
		}
		var active int64
		if err := tx.Model(&orm.WorkflowSession{}).
			Where("conversation_id = ? AND id <> ? AND dismissed = false AND status NOT IN ?", source.ConversationID, source.ID, []string{"completed", "failed", "stopped"}).
			Count(&active).Error; err != nil {
			return 0, nil, err
		}
		if active != 0 {
			return 0, nil, ErrSessionConflict
		}

		bindings, err := txRepo.ListInputBindings(ctx, owner, source.ID)
		if err != nil {
			return 0, nil, err
		}
		newestBinding := map[string]InputBinding{}
		carried := make([]InputBinding, 0, len(bindings)+8)
		listIdentity := map[string]bool{}
		for _, binding := range bindings {
			if !external[binding.MaterialID] {
				continue
			}
			if graph.MaterialCardinalities[binding.MaterialID] == "list" {
				identity := binding.MaterialID + "\x00" + binding.ResourceType + "\x00" + binding.ResourceID + "\x00" + binding.ContentHash + "\x00" + strconv.FormatInt(binding.ResourceRevision, 10)
				if listIdentity[identity] {
					continue
				}
				listIdentity[identity] = true
				binding.ID, binding.WorkflowSessionID = "", ""
				binding.CreatedByCommandID = productRestartBindingCommand(req.IdempotencyKey, "binding:"+binding.ResourceID+":"+binding.ContentHash)
				carried = append(carried, binding)
				continue
			}
			if previous, ok := newestBinding[binding.MaterialID]; !ok || binding.CreatedAt.After(previous.CreatedAt) {
				newestBinding[binding.MaterialID] = binding
			}
		}
		for material, binding := range newestBinding {
			binding.ID, binding.WorkflowSessionID = "", ""
			binding.CreatedByCommandID = productRestartBindingCommand(req.IdempotencyKey, "binding:"+material)
			carried = append(carried, binding)
		}

		artifacts, err := txRepo.ListArtifacts(ctx, owner, source.ID)
		if err != nil {
			return 0, nil, err
		}
		var workspace map[string]any
		if seed, ok := newestBinding["workspace_seed"]; ok {
			resource, getErr := txRepo.GetInputResource(ctx, owner, seed.ResourceID)
			if getErr != nil || resource.Revision != seed.ResourceRevision || resource.ContentHash != seed.ContentHash {
				return 0, nil, repositoryError("PRODUCT_RESTART_INPUT_INVALID")
			}
			workspace = productObject(resource.Content)
			if workspace == nil {
				return 0, nil, repositoryError("PRODUCT_RESTART_INPUT_INVALID")
			}
		}
		workspaceChanged := false
		for _, artifact := range artifacts {
			if artifact.SlotID != "workspace_state" {
				continue
			}
			if artifact.Validity == "deleted" {
				workspace = nil
				carried = removeProductRestartMaterial(carried, "workspace_seed")
				continue
			}
			if artifact.Validity != "effective" {
				continue
			}
			candidate := productObject(artifact.Value)
			if candidate == nil {
				return 0, nil, repositoryError("PRODUCT_RESTART_INPUT_INVALID")
			}
			workspace, workspaceChanged = candidate, true
		}

		for _, artifact := range artifacts {
			stage := productStageForSlot(artifact.SlotID)
			if stage == "" {
				continue
			}
			var definition productStageDefinition
			for _, candidate := range productStages {
				if candidate.ID == stage {
					definition = candidate
					break
				}
			}
			material := productStageMaterial(definition, artifact.SlotID)
			if artifact.Validity == "deleted" {
				carried = removeProductRestartMaterial(carried, material)
				if workspace != nil {
					removeProductRestartLineage(workspace, material, artifact.SlotID)
					workspaceChanged = true
				}
				continue
			}
			if artifact.Validity != "effective" {
				continue
			}
			if !external[material] {
				return 0, nil, repositoryError("PRODUCT_RESTART_REVISION_UNSUPPORTED")
			}
			name, mime, content, readErr := txRepo.productArtifactBytes(ctx, source, artifact)
			if readErr != nil {
				return 0, nil, readErr
			}
			resource, _, importErr := txRepo.ImportInputResource(ctx, owner, name, mime, "sha256:"+requestHash(content), content)
			if importErr != nil {
				return 0, nil, importErr
			}
			carried = removeProductRestartMaterial(carried, material)
			carried = append(carried, InputBinding{MaterialID: material, ResourceType: "input_resource", ResourceID: resource.ID,
				ResourceRevision: resource.Revision, ContentHash: resource.ContentHash,
				CreatedByCommandID: productRestartBindingCommand(req.IdempotencyKey, "binding:"+material)})
			if workspace == nil {
				workspace = map[string]any{"schema_version": "1.1", "visibility": "agent-internal",
					"workspace_id":   "workspace-" + strings.ReplaceAll(uuid.NewSHA1(uuid.NameSpaceURL, []byte(source.ConversationID)).String(), "-", ""),
					"workspace_mode": "shared-project", "artifacts": []any{}, "decisions": []any{}, "approvals": []any{}}
			}
			if entry := productCurrentRegistration(workspace, definition.Slot, source.ID); entry != nil {
				host, _ := entry["host_artifact"].(map[string]any)
				if artifact.SlotID == definition.Slot {
					if productString(host["content_sha256"]) != "" && productString(host["content_sha256"]) != requestHash(content) {
						productRegisterEditedDraft(workspace, definition, source.ID, artifact, resource, requestHash(content))
					} else {
						host["revision_id"], host["revision"], host["content_hash"] = artifact.ID, artifact.Revision, resource.ContentHash
						host["content_sha256"] = requestHash(content)
					}
				}
				representations, _ := entry["representations"].(map[string]any)
				if representations == nil {
					representations = map[string]any{}
					entry["representations"] = representations
				}
				representations[productStageFormat(definition, artifact.SlotID)] = map[string]any{
					"slot": artifact.SlotID, "source_session_id": source.ID,
					"revision_id": artifact.ID, "revision": artifact.Revision,
					"content_hash": resource.ContentHash, "content_sha256": requestHash(content), "present": true,
				}
			}
			addProductRestartLineage(workspace, source, artifact, material, resource)
			workspaceChanged = true
		}
		if workspace != nil {
			bound := map[string]InputBinding{}
			for _, binding := range carried {
				if strings.HasPrefix(binding.MaterialID, "upstream_") {
					bound[binding.MaterialID] = binding
				}
			}
			lineage, _ := workspace["host_artifact_bindings"].([]any)
			kept := make([]any, 0, len(lineage))
			for _, raw := range lineage {
				entry, _ := raw.(map[string]any)
				material := productString(entry["material_id"])
				if !strings.HasPrefix(material, "upstream_") {
					kept = append(kept, raw)
					continue
				}
				binding, ok := bound[material]
				if !ok {
					workspaceChanged = true
					continue
				}
				if entry["resource_id"] != binding.ResourceID || entry["content_hash"] != binding.ContentHash {
					workspaceChanged = true
					continue
				}
				kept = append(kept, raw)
			}
			workspace["host_artifact_bindings"] = kept
		}
		if workspace != nil && workspaceChanged {
			if !external["workspace_seed"] {
				return 0, nil, repositoryError("PRODUCT_RESTART_REVISION_UNSUPPORTED")
			}
			content, _ := json.Marshal(workspace)
			resource, _, importErr := txRepo.ImportInputResource(ctx, owner, "workspace_seed.json", "application/json", "sha256:"+requestHash(content), content)
			if importErr != nil {
				return 0, nil, importErr
			}
			carried = removeProductRestartMaterial(carried, "workspace_seed")
			carried = append(carried, InputBinding{MaterialID: "workspace_seed", ResourceType: "input_resource", ResourceID: resource.ID,
				ResourceRevision: resource.Revision, ContentHash: resource.ContentHash,
				CreatedByCommandID: productRestartBindingCommand(req.IdempotencyKey, "binding:workspace_seed")})
		}
		materialFacts := make([]graphengine.MaterialValue, 0, len(carried))
		for _, binding := range carried {
			materialFacts = append(materialFacts, graphengine.MaterialValue{MaterialID: binding.MaterialID, RevisionID: binding.ResourceID, Valid: true})
		}
		readySteps := graphengine.Project(graph, graphengine.RuntimeSnapshot{Materials: materialFacts}).Ready
		if len(readySteps) != 1 {
			return 0, nil, repositoryError("PRODUCT_RESTART_REVISION_UNSUPPORTED")
		}

		now := time.Now().UTC()
		newID := uuid.NewString()
		if err := tx.Model(&orm.WorkflowSession{}).
			Where("conversation_id = ? AND dismissed = false AND status IN ?", source.ConversationID, []string{"completed", "failed", "stopped"}).
			UpdateColumn("dismissed", true).Error; err != nil {
			return 0, nil, err
		}
		next := orm.WorkflowSession{ID: newID, ConversationID: source.ConversationID, OriginHost: source.OriginHost,
			OriginRef: source.OriginRef, ControllerHost: source.ControllerHost, WorkflowID: pkg.WorkflowID,
			WorkflowRef: pkg.WorkflowRef, WorkflowRevisionID: pkg.RevisionID, WorkflowRevisionNo: pkg.RevisionNo,
			WorkflowTreeHash: pkg.TreeHash, StateVersion: 1, GraphHash: pkg.GraphHash, GraphSchemaVersion: pkg.GraphVersion,
			TriggerHistoryID: source.TriggerHistoryID, Status: "waiting", IntentContext: source.IntentContext,
			CreateUserID: owner, CreatedAt: now, UpdatedAt: now}
		if err := tx.Create(&next).Error; err != nil {
			return 0, nil, err
		}
		for _, binding := range carried {
			binding.WorkflowSessionID = next.ID
			if err := txRepo.bindInputTx(tx, owner, binding); err != nil {
				return 0, nil, err
			}
		}
		response := map[string]any{"source_session_id": source.ID, "session_id": next.ID, "restarted": true,
			"status": next.Status, "state_version": next.StateVersion, "ready_steps": readySteps,
			"conversation_id": source.ConversationID, "workflow_id": next.WorkflowID}
		payload, _ := json.Marshal(response)
		if err := tx.Create(&Event{SessionID: next.ID, OwnerUserID: owner, ContractVersion: "workflow.v1",
			EventType: "workflow.snapshot", EntityID: next.ID, StateVersion: 1, PayloadJSON: payload, CreatedAt: now}).Error; err != nil {
			return 0, nil, err
		}
		return http.StatusOK, payload, nil
	})
	if err != nil {
		return nil, err
	}
	return command.ResponseJSON, nil
}
