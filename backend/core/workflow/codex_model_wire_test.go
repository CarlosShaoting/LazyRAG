package workflow

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/mux"
	"lazymind/core/common/orm"
	"lazymind/core/store"
	"lazymind/core/workflow/graphengine"
)

func TestCodexModelRoundTrip(t *testing.T) {
	db := orm.MigrateTestDB(t, &orm.WorkflowSession{}, &orm.WorkflowSessionStep{}, &orm.WorkflowOutbox{}, &orm.WorkflowRevision{}, &orm.WorkflowRevisionEntry{}, &orm.WorkflowBlob{}, &orm.WorkflowActionJob{}, &orm.WorkflowHostAction{}, &orm.WorkflowAttemptInputBinding{}, &orm.WorkflowSlotRevision{}, &orm.WorkflowInputBinding{})
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })
	graph := graphengine.CompiledStateGraph{Runtime: graphengine.RuntimePolicy{Execution: &graphengine.ExecutionPolicy{Version: "1", ModelExecutor: "codex"}}, Nodes: map[string]graphengine.CompiledNode{"research_topic": {ID: "research_topic", Prompt: "Run the original paper step", Execution: &graphengine.StepExecution{Version: "1"}}}}
	expires := time.Now().Add(time.Hour)
	for _, row := range []any{
		&orm.WorkflowRevision{ID: "revision", WorkflowResourceID: "paper-writing", CompiledGraph: graph.JSON()},
		&orm.WorkflowSession{ID: "session", WorkflowID: "paper-writing", WorkflowRevisionID: "revision", Status: "active", CreateUserID: "owner", ControllerHost: "external-agent", ControlProtocol: "workflow.control.v1", ControlBindingJSON: `{"provider":"codex","connector_id":"connector","driver_session_id":"chat"}`},
		&orm.WorkflowSessionStep{ID: "attempt", SessionID: "session", StepID: "research_topic", TaskID: "task", Status: "claimed", Validity: "effective", ExecutorHost: "lazymind", LeaseToken: "lease", LeaseExpiresAt: &expires},
		&orm.WorkflowOutbox{ID: "outbox", AttemptID: "attempt", SessionID: "session", PayloadJSON: json.RawMessage(`{"metadata":{"workflow_control_inputs_frozen":"true"}}`)},
	} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	router := mux.NewRouter()
	router.HandleFunc("/model/{attempt_id}", CodexModelCompletion)
	server := httptest.NewServer(router)
	defer server.Close()
	done := make(chan string, 1)
	go func() {
		request, _ := http.NewRequest("POST", server.URL+"/model/attempt", strings.NewReader(`{"model":"codex","stream":true,"messages":[{"role":"user","content":"original native prompt"}]}`))
		request.Header.Set("Authorization", "Bearer lease")
		response, err := server.Client().Do(request)
		if err != nil {
			done <- err.Error()
			return
		}
		defer response.Body.Close()
		body, _ := io.ReadAll(response.Body)
		done <- string(body)
	}()
	var job orm.WorkflowActionJob
	deadline := time.Now().Add(3 * time.Second)
	for db.Where("session_id = ? AND slot_id = ?", "session", codexModelSlot).First(&job).Error != nil {
		if time.Now().After(deadline) {
			t.Fatal("native request did not enter the queue")
		}
		time.Sleep(5 * time.Millisecond)
	}
	request := httptest.NewRequest("POST", "/", strings.NewReader(`{"command_id":"worker-command-123"}`))
	request = mux.SetURLVars(request, map[string]string{"session_id": "session", "job_id": job.ID})
	request.Header.Set("X-User-Id", "owner")
	claim := httptest.NewRecorder()
	ClaimCodexModel(claim, request)
	if claim.Code != 200 {
		t.Fatal(claim.Code, claim.Body.String())
	}
	var envelope struct {
		Data struct {
			Hash    string         `json:"request_hash"`
			Token   string         `json:"worker_token"`
			Request map[string]any `json:"generation_request"`
		}
	}
	if err := json.Unmarshal(claim.Body.Bytes(), &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.Data.Request["model"] != "codex" {
		t.Fatal("native model request was not preserved", claim.Body.String())
	}
	encoded, _ := json.Marshal(codexModelResponse{WorkerToken: envelope.Data.Token, RequestHash: envelope.Data.Hash, Message: json.RawMessage(`{"role":"assistant","content":"native-result"}`)})
	request = httptest.NewRequest("POST", "/", strings.NewReader(string(encoded)))
	request = mux.SetURLVars(request, map[string]string{"session_id": "session", "job_id": job.ID})
	request.Header.Set("X-User-Id", "owner")
	response := httptest.NewRecorder()
	SubmitCodexModel(response, request)
	if response.Code != 200 {
		t.Fatal(response.Code, response.Body.String())
	}
	select {
	case body := <-done:
		if !strings.Contains(body, "native-result") || !strings.Contains(body, "[DONE]") {
			t.Fatal(body)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("native model caller was not resumed")
	}
}
