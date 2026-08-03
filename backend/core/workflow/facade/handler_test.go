package facade

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/gorilla/mux"
	"gorm.io/gorm"
	workflowstore "lazymind/core/workflow/store"
)

func TestInputResourceImportAndBindingPinsStableRevision(t *testing.T) {
	h, db := testHandler(t)
	if err := db.Exec(`INSERT INTO plugin_sessions(id, create_user_id) VALUES ('s1','owner')`).Error; err != nil {
		t.Fatal(err)
	}
	content := []byte("stable requirements")
	sum := sha256.Sum256(content)
	body, _ := json.Marshal(map[string]any{
		"contract_version": ContractVersion, "name": "requirements.txt", "mime_type": "text/plain",
		"size": len(content), "content_hash": "sha256:" + hex.EncodeToString(sum[:]),
		"content_base64": base64.StdEncoding.EncodeToString(content),
	})
	w := httptest.NewRecorder()
	h.ImportInputResource(w, request(http.MethodPost, "/workflow-input-resources", "owner", body))
	if w.Code != http.StatusOK {
		t.Fatalf("import=%d %s", w.Code, w.Body.String())
	}
	var resource struct {
		ResourceID  string `json:"resource_id"`
		ContentHash string `json:"content_hash"`
		Revision    int64  `json:"revision"`
	}
	encoded, _ := json.Marshal(decodeEnvelope(t, w).Data)
	if err := json.Unmarshal(encoded, &resource); err != nil {
		t.Fatal(err)
	}
	bindBody, _ := json.Marshal(map[string]any{
		"material_id": "requirements", "resource_type": "file", "resource_id": resource.ResourceID,
		"resource_revision": resource.Revision, "content_hash": resource.ContentHash, "command_id": "cmd-bind",
	})
	bindRequest := mux.SetURLVars(request(http.MethodPost, "/workflow-sessions/s1/input-bindings", "owner", bindBody), map[string]string{"session_id": "s1"})
	bound := httptest.NewRecorder()
	h.BindInput(bound, bindRequest)
	if bound.Code != http.StatusOK {
		t.Fatalf("bind=%d %s", bound.Code, bound.Body.String())
	}
	var count int64
	if err := db.Table("workflow_input_bindings").Where("workflow_session_id = ? AND resource_id = ?", "s1", resource.ResourceID).Count(&count).Error; err != nil || count != 1 {
		t.Fatalf("binding count=%d err=%v", count, err)
	}
	if bytes.Contains(encoded, []byte("content_base64")) || bytes.Contains(encoded, []byte("/tmp/")) {
		t.Fatalf("Host-private data leaked: %s", encoded)
	}
}

func testHandler(t *testing.T) (Handler, *gorm.DB) {
	t.Helper()
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	repo := workflowstore.New(db)
	if err := repo.AutoMigrate(); err != nil {
		t.Fatal(err)
	}
	if err := db.Exec(`CREATE TABLE plugin_sessions (id TEXT PRIMARY KEY, create_user_id TEXT NOT NULL)`).Error; err != nil {
		t.Fatal(err)
	}
	return Handler{Store: repo}, db
}

func request(method, path, owner string, body []byte) *http.Request {
	r := httptest.NewRequest(method, path, bytes.NewReader(body))
	r.Header.Set("X-User-Id", owner)
	r.Header.Set("Workflow-Contract-Version", ContractVersion)
	return r
}

func decodeEnvelope(t *testing.T, recorder *httptest.ResponseRecorder) envelope {
	t.Helper()
	var got envelope
	if err := json.Unmarshal(recorder.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode response %q: %v", recorder.Body.String(), err)
	}
	return got
}

func TestPrepareHTTPIsOwnerScopedIdempotentAndPreservesLegacyPlan(t *testing.T) {
	h, _ := testHandler(t)
	var calls atomic.Int32
	h.PlanLegacy = http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"legacy_plan":true}`))
	})
	body := []byte(`{"workflow_id":"writer","idempotency_key":"same","input_bindings":{"source":"r1"}}`)
	var firstID string
	for i := 0; i < 2; i++ {
		recorder := httptest.NewRecorder()
		h.Prepare(recorder, request(http.MethodPost, "/workflow-preparations", "owner", body))
		if recorder.Code != http.StatusOK {
			t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
		}
		got := decodeEnvelope(t, recorder)
		encoded, _ := json.Marshal(got.Data)
		var prepared workflowstore.Preparation
		if err := json.Unmarshal(encoded, &prepared); err != nil {
			t.Fatal(err)
		}
		if string(prepared.ResponseJSON) != `{"legacy_plan":true}` {
			t.Fatalf("legacy parity lost: %s", prepared.ResponseJSON)
		}
		if firstID == "" {
			firstID = prepared.ID
		} else if prepared.ID != firstID {
			t.Fatalf("idempotency changed id: %s != %s", prepared.ID, firstID)
		}
	}
	if calls.Load() != 1 {
		t.Fatalf("idempotent prepare planned %d times", calls.Load())
	}
}

func TestConsumeHTTPChecksOwnerAndConsumesExactlyOnce(t *testing.T) {
	h, _ := testHandler(t)
	p, _, err := h.Store.Prepare(t.Context(), "owner", "key", "writer", ContractVersion, json.RawMessage(`{}`), json.RawMessage(`{}`))
	if err != nil {
		t.Fatal(err)
	}
	consume := func(owner, session string) *httptest.ResponseRecorder {
		r := request(http.MethodPost, "/workflow-preparations/"+p.ID+"/consume", owner, []byte(`{"session_id":"`+session+`"}`))
		r = mux.SetURLVars(r, map[string]string{"preparation_id": p.ID})
		w := httptest.NewRecorder()
		h.Consume(w, r)
		return w
	}
	denied := consume("other", "s1")
	if denied.Code != http.StatusForbidden || decodeEnvelope(t, denied).Error.Code != "PERMISSION_DENIED" {
		t.Fatalf("denied=%d %s", denied.Code, denied.Body.String())
	}
	if got := consume("owner", "s1"); got.Code != http.StatusOK {
		t.Fatalf("consume=%d %s", got.Code, got.Body.String())
	}
	second := consume("owner", "s2")
	if second.Code != http.StatusOK || !bytes.Contains(second.Body.Bytes(), []byte(`"session_id":"s1"`)) {
		t.Fatalf("second consume changed session: %s", second.Body.String())
	}
}

func TestCommandHTTPChecksVersionPermissionAndExecutesLegacyOnce(t *testing.T) {
	h, db := testHandler(t)
	if err := db.Exec(`INSERT INTO plugin_sessions(id, create_user_id) VALUES ('s1','owner')`).Error; err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	legacy := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		if payload["operation"] != "advance" || payload["hand_off"] != false || len(payload["targets"].([]any)) != 1 {
			t.Errorf("legacy adapter payload=%#v", payload)
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"accepted":true,"state_version":2}`))
	})
	command := h.Command(legacy)
	body := []byte(`{"contract_version":"workflow.v1","command_id":"cmd-1","tool":"advance_step","session_id":"s1","expected_state_version":1,"steps":[{"step_id":"draft"}]}`)
	call := func(owner string, payload []byte) *httptest.ResponseRecorder {
		r := request(http.MethodPost, "/workflow-sessions/s1/commands", owner, payload)
		r = mux.SetURLVars(r, map[string]string{"session_id": "s1"})
		w := httptest.NewRecorder()
		command(w, r)
		return w
	}
	denied := call("other", body)
	if denied.Code != http.StatusForbidden || decodeEnvelope(t, denied).Error.Code != "PERMISSION_DENIED" {
		t.Fatalf("permission=%d %s", denied.Code, denied.Body.String())
	}
	for i := 0; i < 2; i++ {
		got := call("owner", body)
		if got.Code != http.StatusAccepted {
			t.Fatalf("legacy parity=%d %q", got.Code, got.Body.String())
		}
		wrapped := decodeEnvelope(t, got)
		encoded, _ := json.Marshal(wrapped.Data)
		if !bytes.Contains(encoded, []byte(`"state_version":2`)) || !wrapped.OK || wrapped.ContractVersion != ContractVersion {
			t.Fatalf("contract/legacy parity lost: %s", got.Body.String())
		}
	}
	if calls.Load() != 1 {
		t.Fatalf("idempotent command executed %d times", calls.Load())
	}
	conflict := call("owner", bytes.Replace(body, []byte(`"draft"`), []byte(`"review"`), 1))
	if conflict.Code != http.StatusConflict || decodeEnvelope(t, conflict).Error.Code != "IDEMPOTENCY_CONFLICT" {
		t.Fatalf("conflict=%d %s", conflict.Code, conflict.Body.String())
	}
	badVersion := request(http.MethodPost, "/workflow-sessions/s1/commands", "owner", body)
	badVersion = mux.SetURLVars(badVersion, map[string]string{"session_id": "s1"})
	badVersion.Header.Set("Workflow-Contract-Version", "workflow.v2")
	w := httptest.NewRecorder()
	command(w, badVersion)
	if w.Code != http.StatusUnprocessableEntity || decodeEnvelope(t, w).Error.Code != "CONTRACT_VERSION_UNSUPPORTED" {
		t.Fatalf("version=%d %s", w.Code, w.Body.String())
	}
}
