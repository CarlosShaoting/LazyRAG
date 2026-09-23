package facade

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/gorilla/mux"
	"gorm.io/gorm"
	"lazymind/core/common/orm"
	"lazymind/core/state"
	"lazymind/core/subagent"
	workflowstore "lazymind/core/workflow/store"
)

func TestRestartProductWorkflowOnLatestHTTPPublishesCreatedEvent(t *testing.T) {
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(append(workflowstore.Models(), &orm.WorkflowSession{}, &orm.Conversation{},
		&orm.WorkflowResource{}, &orm.WorkflowRevision{}, &orm.WorkflowRevisionEntry{}, &orm.WorkflowBlob{},
		&orm.WorkflowSlotRevision{}, &orm.WorkflowHumanArtifact{}, &orm.WorkflowSessionStep{})...); err != nil {
		t.Fatal(err)
	}
	repo := workflowstore.New(db)
	h := Handler{Store: repo}
	now := time.Now().UTC()
	graph := json.RawMessage(`{"schema_version":"3","graph_hash":"latest-graph","start_route":"all","nodes":{"route_product_stage":{"id":"route_product_stage"}},"control_edges":[{"from":"__start__","to":"route_product_stage"}],"material_producers":{"product_goal":{"kind":"external"}}}`)
	for _, value := range []any{
		&orm.Conversation{ID: "conversation", BaseModel: orm.BaseModel{CreateUserID: "owner", CreatedAt: now, UpdatedAt: now}},
		&orm.WorkflowResource{ID: "resource", WorkflowID: "product_solution_delivery", WorkflowRef: "builtin:product_solution_delivery", HeadRevisionID: "latest", Status: "active", Version: 15},
		&orm.WorkflowRevision{ID: "latest", WorkflowResourceID: "resource", RevisionNo: 15, CompiledGraph: graph, GraphHash: "latest-graph", GraphSchemaVersion: "3", CreatedAt: now},
		&orm.WorkflowSession{ID: "failed-old", ConversationID: "conversation", WorkflowID: "product_solution_delivery", WorkflowRevisionID: "rev14", CreateUserID: "owner", Status: "failed", StateVersion: 4, CreatedAt: now, UpdatedAt: now},
	} {
		if err := db.Create(value).Error; err != nil {
			t.Fatal(err)
		}
	}
	goal := []byte("keep exact goal")
	digest := sha256.Sum256(goal)
	resource, _, err := repo.ImportInputResource(context.Background(), "owner", "product_goal.txt", "text/plain", "sha256:"+hex.EncodeToString(digest[:]), goal)
	if err != nil {
		t.Fatal(err)
	}
	if err := repo.BindInput(context.Background(), "owner", workflowstore.InputBinding{WorkflowSessionID: "failed-old", MaterialID: "product_goal",
		ResourceType: "input_resource", ResourceID: resource.ID, ResourceRevision: resource.Revision, ContentHash: resource.ContentHash, CreatedByCommandID: "prepare"}); err != nil {
		t.Fatal(err)
	}

	var eventConversation, eventType string
	var eventPayload map[string]any
	subagent.EventHooks.RegisterConversationEventHook(func(_ context.Context, _ state.Store, conversationID, _ string, kind string, payload map[string]any) error {
		eventConversation, eventType, eventPayload = conversationID, kind, payload
		return nil
	})
	t.Cleanup(func() { subagent.EventHooks.RegisterConversationEventHook(nil) })
	body := []byte(`{"idempotency_key":"http-restart","expected_state_version":4}`)
	req := request(http.MethodPost, "/workflow-sessions/failed-old:restart-on-latest", "owner", body)
	req = mux.SetURLVars(req, map[string]string{"session_id": "failed-old"})
	recorder := httptest.NewRecorder()
	h.RestartProductWorkflowOnLatest(recorder, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if eventConversation != "conversation" || eventType != "workflow_session_created" || eventPayload["source_session_id"] != "failed-old" || eventPayload["restarted"] != true {
		t.Fatalf("created event missing or unsafe: conversation=%q type=%q payload=%#v", eventConversation, eventType, eventPayload)
	}
	response, _ := json.Marshal(decodeEnvelope(t, recorder).Data)
	if !json.Valid(response) || eventPayload["session_id"] == "" {
		t.Fatalf("bad response: %s", response)
	}
}
