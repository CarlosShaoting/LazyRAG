package chat

import (
	"context"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
	"lazymind/core/log"
	"lazymind/core/state"
)

// claimChatHistoryRun transfers a reused history row to a new run before that
// run can emit progress. Terminal/progress writers must then use the matching
// run_id guard so a late previous run cannot overwrite the current owner.
func claimChatHistoryRun(ctx context.Context, db *gorm.DB, historyID, runID string) error {
	if db == nil || strings.TrimSpace(historyID) == "" || strings.TrimSpace(runID) == "" {
		return nil
	}
	var history orm.ChatHistory
	if err := db.WithContext(ctx).Select("conversation_id").Where("id = ?", historyID).Take(&history).Error; err != nil {
		return err
	}
	return conversationCheckpoint(ctx, db, history.ConversationID, func(tx *gorm.DB) error {
		now := time.Now()
		return tx.Model(&orm.ChatHistory{}).Where("id = ?", historyID).Updates(map[string]any{
			"run_id": runID, "run_status": "generating", "run_terminal": nil,
			"create_time": now, "update_time": now,
		}).Error
	})
}

func updateOwnedChatHistory(ctx context.Context, db *gorm.DB, historyID, runID string, values map[string]any) (bool, error) {
	if db == nil || strings.TrimSpace(historyID) == "" || strings.TrimSpace(runID) == "" {
		return false, nil
	}
	var history orm.ChatHistory
	if err := db.WithContext(ctx).Select("conversation_id").Where("id = ?", historyID).Take(&history).Error; err != nil {
		return false, err
	}
	var affected int64
	err := conversationCheckpoint(ctx, db, history.ConversationID, func(tx *gorm.DB) error {
		result := tx.Model(&orm.ChatHistory{}).Where("id = ? AND run_id = ?", historyID, runID).Updates(values)
		affected = result.RowsAffected
		return result.Error
	})
	if err != nil {
		return false, err
	}
	if affected == 0 {
		log.Logger.Info().Str("history_id", historyID).Str("run_id", runID).
			Msg("ignored stale chat history write")
		return false, nil
	}
	return true, nil
}

// finalizeCancelledChatHistory makes the stop endpoint authoritative even when
// the original streaming handler no longer exists (for example after a desktop
// restart). A live handler can still persist a later partial-result snapshot;
// the run-decision guard will resolve that terminal to the same cancellation.
func finalizeCancelledChatHistory(
	ctx context.Context,
	db *gorm.DB,
	stateStore state.Store,
	conversationID, historyID, runID, currentResult string,
) error {
	terminal := &RunTerminal{Status: "cancelled", Reason: "user_cancelled"}
	if db != nil {
		var history orm.ChatHistory
		err := db.WithContext(ctx).
			Where("id = ? AND conversation_id = ? AND run_id = ?", historyID, conversationID, runID).
			Take(&history).Error
		if err != nil && err != gorm.ErrRecordNotFound {
			return err
		}
		if err == nil {
			if strings.TrimSpace(currentResult) == "" {
				currentResult = history.Result
			}
			terminal.PartialOutput = strings.TrimSpace(currentResult) != ""
			updated, updateErr := updateOwnedChatHistory(ctx, db, historyID, runID, map[string]any{
				"run_status": terminal.Status, "run_terminal": terminalJSON(terminal), "update_time": time.Now(),
			})
			if updateErr != nil {
				return updateErr
			}
			if !updated {
				return nil
			}
		}
	}
	terminal.PartialOutput = terminal.PartialOutput || strings.TrimSpace(currentResult) != ""
	if stateStore != nil {
		return setChatRuntimeStatus(ctx, stateStore, conversationID, historyID, terminal.Status, currentResult, runID, terminal)
	}
	return nil
}

func updateOwnedMultiAnswerHistory(ctx context.Context, db *gorm.DB, historyID, runID string, values any) (bool, error) {
	if db == nil || strings.TrimSpace(historyID) == "" || strings.TrimSpace(runID) == "" {
		return false, nil
	}
	result := db.WithContext(ctx).Model(&orm.MultiAnswersChatHistory{}).
		Where("id = ? AND run_id = ?", historyID, runID).Updates(values)
	if result.Error != nil {
		return false, result.Error
	}
	if result.RowsAffected == 0 {
		log.Logger.Info().Str("history_id", historyID).Str("run_id", runID).
			Msg("ignored stale multi-answer history write")
		return false, nil
	}
	return true, nil
}
