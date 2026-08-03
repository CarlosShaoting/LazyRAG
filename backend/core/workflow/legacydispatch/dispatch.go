// Package legacydispatch is the metered compatibility boundary for old Core workers.
package legacydispatch

import (
	"context"
	"encoding/json"
	"sync/atomic"
	"time"

	"lazymind/core/common/orm"
	"lazymind/core/state"
	"lazymind/core/subagent"

	"gorm.io/gorm"
)

var calls atomic.Uint64

func Calls() uint64 { return calls.Load() }

func Dispatch(db *gorm.DB, stateStore state.Store, taskID string) {
	calls.Add(1)
	var row orm.WorkflowRunOutbox
	claimed := false
	if err := db.WithContext(context.Background()).Transaction(func(tx *gorm.DB) error {
		result := tx.Model(&orm.WorkflowRunOutbox{}).Where("task_id = ? AND status = ?", taskID, "pending").Updates(map[string]any{"status": "dispatching", "updated_at": time.Now().UTC()})
		if result.Error != nil || result.RowsAffected != 1 {
			return result.Error
		}
		if err := tx.Where("task_id = ?", taskID).First(&row).Error; err != nil {
			return err
		}
		var task orm.SubAgentTask
		if err := tx.Select("status").Where("id = ?", taskID).First(&task).Error; err != nil {
			return err
		}
		if task.Status == subagent.StatusSucceeded || task.Status == subagent.StatusFailed || task.Status == subagent.StatusInterrupted || task.Status == subagent.StatusCanceled {
			return tx.Model(&orm.WorkflowRunOutbox{}).Where("task_id = ?", taskID).Updates(map[string]any{"status": "completed", "updated_at": time.Now().UTC()}).Error
		}
		claimed = true
		return nil
	}); err != nil || !claimed {
		return
	}
	var request subagent.RunRequest
	if err := json.Unmarshal(row.Payload, &request); err != nil {
		_ = db.Model(&orm.WorkflowRunOutbox{}).Where("task_id = ?", taskID).Updates(map[string]any{"status": "failed", "last_error": err.Error(), "updated_at": time.Now().UTC()}).Error
		_ = subagent.UpdateFinalStatus(context.Background(), db, taskID, subagent.StatusFailed, "invalid legacy workflow run outbox payload")
		return
	}
	_ = subagent.WriteStatus(context.Background(), stateStore, taskID, map[string]any{"status": subagent.StatusPending, "progress": 0})
	go func() {
		err := subagent.Run(context.Background(), db, stateStore, request)
		status, lastError := "completed", ""
		if err != nil {
			status, lastError = "failed", err.Error()
		}
		_ = db.Model(&orm.WorkflowRunOutbox{}).Where("task_id = ?", taskID).Updates(map[string]any{"status": status, "last_error": lastError, "updated_at": time.Now().UTC()}).Error
	}()
}
