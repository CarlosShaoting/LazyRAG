package workflow

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/gorilla/mux"
	"lazymind/core/common/orm"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCompositeOrderAtomicPermutation(t *testing.T) {
	db := newTestDB(t)
	ctx := context.Background()
	for _, id := range []string{"prompts", "slides"} {
		if err := db.Create(&orm.WorkflowSlotOrder{SessionID: "linked", SlotID: id, OrderList: json.RawMessage(`[8,2,5]`), OrderVersion: 3}).Error; err != nil {
			t.Fatal(err)
		}
	}
	changes := []SlotOrderChange{{SlotID: "prompts", Order: []int{5, 8, 2}, Version: 3}, {SlotID: "slides", Order: []int{5, 8, 2}, Version: 2}}
	if err := ReorderSlots(ctx, db.DB, "linked", changes); !errors.Is(err, ErrConflict) {
		t.Fatalf("stale update: %v", err)
	}
	first, _ := GetSlotOrder(ctx, db.DB, "linked", "prompts")
	if string(first.OrderList) != "[8,2,5]" || first.OrderVersion != 3 {
		t.Fatalf("partial commit: %+v", first)
	}
	for _, order := range [][]int{{8, 8, 5}, {8, 2}, {8, 2, 99}} {
		if err := ReorderSlot(ctx, db.DB, "linked", "prompts", order, 3); !errors.Is(err, ErrInvalidOrder) {
			t.Fatalf("accepted invalid order %v: %v", order, err)
		}
	}
	changes[1].Version = 3
	if err := ReorderSlots(ctx, db.DB, "linked", changes); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"prompts", "slides"} {
		row, err := GetSlotOrder(ctx, db.DB, "linked", id)
		if err != nil || string(row.OrderList) != "[5,8,2]" || row.OrderVersion != 4 {
			t.Fatalf("wrong linked order: %+v %v", row, err)
		}
	}
}

func TestCompositeOrderHTTPRejectsPartialCommit(t *testing.T) {
	db := newHandlerTestDB(t)
	if err := db.Create(&orm.WorkflowSession{ID: "linked-http", ConversationID: "conversation", Status: SessionStatusCompleted}).Error; err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"prompts", "slides"} {
		if err := db.Create(&orm.WorkflowSlotOrder{SessionID: "linked-http", SlotID: id, OrderList: json.RawMessage(`[8,2]`), OrderVersion: 3}).Error; err != nil {
			t.Fatal(err)
		}
	}
	for _, tc := range []struct {
		version int
		status  int
	}{{2, 409}, {3, 200}} {
		request := httptest.NewRequest(http.MethodPatch, "/", strings.NewReader(fmt.Sprintf(`{"order":[2,8],"version":3,"linked_orders":[{"slot_id":"slides","order":[2,8],"version":%d}]}`, tc.version)))
		request = mux.SetURLVars(request, map[string]string{"session_id": "linked-http", "slot_id": "prompts"})
		response := httptest.NewRecorder()
		ReorderSlotItems(response, request)
		if response.Code != tc.status {
			t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
		}
		want := "[8,2]"
		if tc.status == 200 {
			want = "[2,8]"
		}
		for _, slot := range []string{"prompts", "slides"} {
			row, err := GetSlotOrder(context.Background(), db.DB, "linked-http", slot)
			if err != nil || string(row.OrderList) != want {
				t.Fatalf("slot %s: %+v %v", slot, row, err)
			}
		}
	}
}
