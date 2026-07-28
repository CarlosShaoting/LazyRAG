package plugin

import (
	"encoding/json"
	"fmt"
	"strings"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
)

func historyFilesFromConversation(db *gorm.DB, conversationID string) map[string][]string {
	var histories []orm.ChatHistory
	if err := db.
		Where("conversation_id = ?", strings.TrimSpace(conversationID)).
		Order("seq ASC").
		Find(&histories).Error; err != nil {
		return nil
	}

	filesByTurn := make(map[string][]string)
	for _, history := range histories {
		var ext struct {
			Input []map[string]any `json:"input"`
		}
		if len(history.Ext) == 0 || json.Unmarshal(history.Ext, &ext) != nil {
			continue
		}
		turn := fmt.Sprintf("%d", history.Seq)
		for _, item := range ext.Input {
			inputType, _ := item["input_type"].(string)
			inputType = strings.ToLower(strings.TrimSpace(inputType))
			if inputType != "image" && inputType != "file" {
				continue
			}
			uri, _ := item["uri"].(string)
			uri = strings.TrimSpace(uri)
			if uri == "" {
				continue
			}
			filesByTurn[turn] = append(filesByTurn[turn], uri)
		}
	}
	if len(filesByTurn) == 0 {
		return nil
	}
	return filesByTurn
}
