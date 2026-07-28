package plugin

import (
	"encoding/json"
	"testing"

	"lazymind/core/common/orm"
)

func TestHistoryFilesFromConversation(t *testing.T) {
	db := newTestDB(t)
	if err := db.AutoMigrate(&orm.ChatHistory{}); err != nil {
		t.Fatalf("migrate chat history: %v", err)
	}
	ext, err := json.Marshal(map[string]any{
		"input": []map[string]any{
			{"input_type": "text", "text": "animate this"},
			{"input_type": "image", "uri": "/runtime/uploads/dog.jpg"},
			{"input_type": "file", "uri": "https://example.com/remote.png"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	history := orm.ChatHistory{
		ID:             "history-1",
		Seq:            3,
		ConversationID: "conversation-1",
		Ext:            ext,
	}
	if err := db.Create(&history).Error; err != nil {
		t.Fatalf("create chat history: %v", err)
	}

	got := historyFilesFromConversation(db.DB, "conversation-1")

	if len(got) != 1 || len(got["3"]) != 2 {
		t.Fatalf("history files = %#v", got)
	}
	if got["3"][0] != "/runtime/uploads/dog.jpg" || got["3"][1] != "https://example.com/remote.png" {
		t.Fatalf("history files = %#v", got)
	}
}
