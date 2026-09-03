package workflow

import (
	"encoding/json"
	"net/http"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"lazymind/core/common"
	"lazymind/core/common/orm"
	"lazymind/core/store"
	"lazymind/core/workflow/graphengine"
)

type approvalPreferenceRequest struct {
	StepID           string `json:"step_id"`
	Scope            string `json:"scope"`
	ApprovalRequired bool   `json:"approval_required"`
}

func applyApprovalPreferences(ctxDB *gorm.DB, userID, workflowID string, projection graphengine.Projection) graphengine.Projection {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(workflowID) == "" {
		return projection
	}
	var rows []orm.WorkflowApprovalPreference
	if err := ctxDB.Where("user_id = ? AND workflow_id = ?", userID, workflowID).Find(&rows).Error; err != nil {
		// Keep projections available during rolling upgrades before the migration
		// has reached every local/dev database.
		return projection
	}
	for _, row := range rows {
		node, ok := projection.Nodes[row.StepID]
		if !ok {
			continue
		}
		node.RequiresApproval = row.ApprovalRequired
		projection.Nodes[row.StepID] = node
	}
	return projection
}

func projectWithApprovalPreferences(db *gorm.DB, userID, workflowID string, graph *graphengine.CompiledStateGraph, snapshot graphengine.RuntimeSnapshot) graphengine.Projection {
	return applyApprovalPreferences(db, userID, workflowID, graphengine.Project(graph, snapshot))
}

func descendantStepIDs(graph *graphengine.CompiledStateGraph, start string) []string {
	seen := map[string]bool{start: true}
	queue := []string{start}
	result := make([]string, 0)
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		for _, edge := range graph.ControlEdges {
			if edge.From != current || edge.To == "__end__" || seen[edge.To] {
				continue
			}
			seen[edge.To] = true
			queue = append(queue, edge.To)
			if _, ok := graph.Nodes[edge.To]; ok {
				result = append(result, edge.To)
			}
		}
	}
	sort.Strings(result)
	return result
}

// SetWorkflowApprovalPreference persists a user-level exception to a package's
// default approval modes. "step" affects this checkpoint in future sessions;
// "following" affects all downstream checkpoints but not the current one.
func SetWorkflowApprovalPreference(w http.ResponseWriter, r *http.Request) {
	userID := common.UserID(r)
	var session orm.WorkflowSession
	if err := store.DB().Where("id = ? AND dismissed = false", common.PathVar(r, "session_id")).First(&session).Error; err != nil {
		common.ReplyErr(w, "session not found", http.StatusNotFound)
		return
	}
	if userID == "" || session.CreateUserID != userID {
		common.ReplyErr(w, "forbidden", http.StatusForbidden)
		return
	}
	var req approvalPreferenceRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid approval preference", http.StatusBadRequest)
		return
	}
	req.StepID = strings.TrimSpace(req.StepID)
	if req.StepID == "" || (req.Scope != "step" && req.Scope != "following") {
		common.ReplyErr(w, "step_id and scope (step|following) are required", http.StatusUnprocessableEntity)
		return
	}
	// The current UI only offers opt-out actions. Reject opt-in writes so a
	// malformed client cannot silently make package-auto steps require approval.
	if req.ApprovalRequired {
		common.ReplyErr(w, "approval_required must be false", http.StatusUnprocessableEntity)
		return
	}
	graph, err := loadSessionGraph(r.Context(), store.DB(), &session)
	if err != nil {
		common.ReplyErr(w, "load workflow graph failed: "+err.Error(), http.StatusUnprocessableEntity)
		return
	}
	if _, ok := graph.Nodes[req.StepID]; !ok {
		common.ReplyErr(w, "workflow step not found", http.StatusNotFound)
		return
	}
	stepIDs := []string{req.StepID}
	if req.Scope == "following" {
		stepIDs = descendantStepIDs(graph, req.StepID)
	}
	now := time.Now().UTC()
	rows := make([]orm.WorkflowApprovalPreference, 0, len(stepIDs))
	for _, stepID := range stepIDs {
		rows = append(rows, orm.WorkflowApprovalPreference{
			UserID: userID, WorkflowID: session.WorkflowID, StepID: stepID,
			ApprovalRequired: false, CreatedAt: now, UpdatedAt: now,
		})
	}
	if len(rows) > 0 {
		if err := store.DB().Clauses(clause.OnConflict{
			Columns:   []clause.Column{{Name: "user_id"}, {Name: "workflow_id"}, {Name: "step_id"}},
			DoUpdates: clause.Assignments(map[string]any{"approval_required": false, "updated_at": now}),
		}).Create(&rows).Error; err != nil {
			common.ReplyErr(w, "save approval preference failed", http.StatusInternalServerError)
			return
		}
	}
	common.ReplyOK(w, map[string]any{"workflow_id": session.WorkflowID, "scope": req.Scope, "step_ids": stepIDs, "approval_required": false})
}
