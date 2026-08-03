package facade

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/gorilla/mux"
	"gorm.io/gorm"
	workflowstore "lazymind/core/workflow/store"
)

const ContractVersion = "workflow.v1"

type Error struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	Retryable bool           `json:"retryable"`
	Details   map[string]any `json:"details,omitempty"`
}

type envelope struct {
	ContractVersion string `json:"contract_version"`
	RequestID       string `json:"request_id"`
	OK              bool   `json:"ok"`
	Data            any    `json:"result,omitempty"`
	Error           *Error `json:"error,omitempty"`
}

type Handler struct {
	Store *workflowstore.Repository
	// Legacy handlers remain the sole Runtime writers during PR4.
	PlanLegacy       http.Handler
	StartLegacy      http.Handler
	TransitionLegacy http.Handler
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	if wrapped, ok := value.(envelope); ok {
		wrapped.ContractVersion = ContractVersion
		wrapped.RequestID = "server-generated"
		wrapped.OK = wrapped.Error == nil
		value = wrapped
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func fail(w http.ResponseWriter, status int, code, message string, retryable bool) {
	writeJSON(w, status, envelope{Error: &Error{Code: code, Message: message, Retryable: retryable}})
}

func identityAndVersion(w http.ResponseWriter, r *http.Request) (string, bool) {
	owner := strings.TrimSpace(r.Header.Get("X-User-Id"))
	if owner == "" {
		fail(w, http.StatusBadRequest, "IDENTITY_REQUIRED", "X-User-Id is required", false)
		return "", false
	}
	version := strings.TrimSpace(r.Header.Get("Workflow-Contract-Version"))
	if version == "" {
		version = ContractVersion
	}
	if version != ContractVersion {
		fail(w, http.StatusUnprocessableEntity, "CONTRACT_VERSION_UNSUPPORTED", "supported version is workflow.v1", false)
		return "", false
	}
	return owner, true
}

type prepareRequest struct {
	PreparationID  string         `json:"preparation_id"`
	IdempotencyKey string         `json:"idempotency_key"`
	WorkflowID     string         `json:"workflow_id"`
	InputBindings  map[string]any `json:"input_bindings"`
}

type toolCommandRequest struct {
	ContractVersion      string `json:"contract_version"`
	CommandID            string `json:"command_id"`
	Tool                 string `json:"tool"`
	SessionID            string `json:"session_id"`
	ExpectedStateVersion *int64 `json:"expected_state_version"`
	Steps                []struct {
		StepID string `json:"step_id"`
	} `json:"steps"`
}

func validateToolCommand(body []byte, pathSessionID string) error {
	var command toolCommandRequest
	if err := json.Unmarshal(body, &command); err != nil {
		return errors.New("invalid JSON command")
	}
	if command.ContractVersion != ContractVersion {
		return errors.New("contract_version must be workflow.v1")
	}
	if command.SessionID == "" || command.SessionID != pathSessionID {
		return errors.New("session_id must match request path")
	}
	if command.Tool != "advance_step" && command.Tool != "advance_step_and_hand_off" {
		return errors.New("unsupported workflow tool")
	}
	if command.ExpectedStateVersion == nil || *command.ExpectedStateVersion < 0 {
		return errors.New("expected_state_version is required")
	}
	if len(command.Steps) == 0 {
		return errors.New("at least one step is required")
	}
	for _, step := range command.Steps {
		if strings.TrimSpace(step.StepID) == "" {
			return errors.New("step_id is required")
		}
	}
	return nil
}

func legacyTransitionBody(body []byte) ([]byte, error) {
	var public map[string]any
	if err := json.Unmarshal(body, &public); err != nil {
		return nil, err
	}
	steps, _ := public["steps"].([]any)
	targets := make([]any, 0, len(steps))
	for _, raw := range steps {
		step, _ := raw.(map[string]any)
		target := map[string]any{"target_step_id": step["step_id"]}
		for _, key := range []string{"task_id", "objective", "user_input", "runtime_instruction", "partial_indices"} {
			if value, ok := step[key]; ok {
				target[key] = value
			}
		}
		targets = append(targets, target)
	}
	if len(targets) > 1 {
		public["operation"] = "execute_batch"
	} else {
		public["operation"] = "advance"
	}
	public["targets"] = targets
	public["hand_off"] = public["tool"] == "advance_step_and_hand_off"
	delete(public, "steps")
	delete(public, "tool")
	delete(public, "contract_version")
	delete(public, "session_id")
	return json.Marshal(public)
}

func (h Handler) Prepare(w http.ResponseWriter, r *http.Request) {
	owner, ok := identityAndVersion(w, r)
	if !ok {
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		fail(w, 400, "INVALID_REQUEST", err.Error(), false)
		return
	}
	var req prepareRequest
	if err := json.Unmarshal(body, &req); err != nil || req.WorkflowID == "" {
		fail(w, 422, "INVALID_REQUEST", "workflow_id is required", false)
		return
	}
	key := strings.TrimSpace(req.IdempotencyKey)
	if key == "" {
		key = strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	}
	if existing, err := h.Store.PreparationByKey(r.Context(), owner, key); err == nil {
		if !bytes.Equal(bytes.TrimSpace(existing.RequestJSON), bytes.TrimSpace(body)) {
			fail(w, http.StatusConflict, "IDEMPOTENCY_CONFLICT", "idempotency key was used with another payload", false)
			return
		}
		writeJSON(w, http.StatusOK, envelope{Data: existing})
		return
	} else if !errors.Is(err, workflowstore.ErrNotFound) {
		fail(w, http.StatusServiceUnavailable, "PREPARATION_STORE_FAILED", err.Error(), true)
		return
	}
	if key == "" {
		fail(w, 422, "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required", false)
		return
	}
	plan := json.RawMessage(`{"status":"ready"}`)
	if h.PlanLegacy != nil {
		recorder := &capture{header: http.Header{}}
		clone := r.Clone(r.Context())
		clone.Body = io.NopCloser(bytes.NewReader(body))
		h.PlanLegacy.ServeHTTP(recorder, clone)
		if recorder.status >= 400 {
			w.Header().Set("Content-Type", recorder.header.Get("Content-Type"))
			w.WriteHeader(recorder.status)
			_, _ = w.Write(recorder.body.Bytes())
			return
		}
		plan = append(plan[:0], recorder.body.Bytes()...)
	}
	prepared, _, err := h.Store.Prepare(r.Context(), owner, key, req.WorkflowID, ContractVersion, body, plan)
	if err != nil {
		fail(w, 503, "PREPARATION_STORE_FAILED", err.Error(), true)
		return
	}
	writeJSON(w, http.StatusOK, envelope{Data: prepared})
}

func (h Handler) Consume(w http.ResponseWriter, r *http.Request) {
	owner, ok := identityAndVersion(w, r)
	if !ok {
		return
	}
	id := mux.Vars(r)["preparation_id"]
	var req struct {
		SessionID string `json:"session_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.SessionID == "" {
		fail(w, 422, "INVALID_REQUEST", "session_id is required", false)
		return
	}
	prepared, _, err := h.Store.Consume(r.Context(), id, owner, req.SessionID)
	if errors.Is(err, workflowstore.ErrNotFound) {
		fail(w, 404, "PREPARATION_NOT_FOUND", "preparation not found", false)
		return
	}
	if errors.Is(err, workflowstore.ErrPermissionDenied) {
		fail(w, 403, "PERMISSION_DENIED", "preparation belongs to another owner", false)
		return
	}
	if err != nil {
		fail(w, 503, "PREPARATION_CONSUME_FAILED", err.Error(), true)
		return
	}
	if h.StartLegacy != nil {
		var startPayload map[string]any
		if err := json.Unmarshal(prepared.RequestJSON, &startPayload); err != nil {
			fail(w, 422, "INVALID_REQUEST", "stored preparation is invalid", false)
			return
		}
		startPayload["command_id"] = "prepare:" + prepared.ID
		startPayload["session_id"] = req.SessionID
		startBody, _ := json.Marshal(startPayload)
		recorder := &capture{header: http.Header{}}
		clone := r.Clone(r.Context())
		clone.Body = io.NopCloser(bytes.NewReader(startBody))
		h.StartLegacy.ServeHTTP(recorder, clone)
		if recorder.status >= 400 {
			writeJSON(w, recorder.status, envelope{Error: &Error{Code: "INVALID_TRANSITION", Message: recorder.body.String(), Retryable: false}})
			return
		}
		writeJSON(w, recorder.status, envelope{Data: json.RawMessage(recorder.body.Bytes())})
		return
	}
	writeJSON(w, 200, envelope{Data: prepared})
}

func (h Handler) Command(delegate http.Handler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		owner, ok := identityAndVersion(w, r)
		if !ok {
			return
		}
		sessionID := mux.Vars(r)["session_id"]
		if err := h.Store.AuthorizeSession(r.Context(), sessionID, owner); err != nil {
			fail(w, 403, "PERMISSION_DENIED", "workflow session belongs to another owner", false)
			return
		}
		commandID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
		if err != nil {
			fail(w, 400, "INVALID_REQUEST", err.Error(), false)
			return
		}
		if commandID == "" {
			var payload struct {
				CommandID string `json:"command_id"`
			}
			_ = json.Unmarshal(body, &payload)
			commandID = payload.CommandID
		}
		if err := validateToolCommand(body, sessionID); err != nil {
			fail(w, http.StatusUnprocessableEntity, "INVALID_TRANSITION", err.Error(), false)
			return
		}
		if commandID == "" {
			fail(w, 422, "IDEMPOTENCY_KEY_REQUIRED", "command_id or Idempotency-Key is required", false)
			return
		}
		result, _, err := h.Store.Command(r.Context(), owner, sessionID, commandID, ContractVersion, body, func(_ *gorm.DB) (int, json.RawMessage, error) {
			legacyBody, err := legacyTransitionBody(body)
			if err != nil {
				return 0, nil, err
			}
			recorder := &capture{header: http.Header{}}
			clone := r.Clone(r.Context())
			clone.Body = io.NopCloser(bytes.NewReader(legacyBody))
			delegate.ServeHTTP(recorder, clone)
			return recorder.status, append(json.RawMessage(nil), recorder.body.Bytes()...), nil
		})
		if errors.Is(err, workflowstore.ErrIdempotencyConflict) {
			fail(w, 409, "IDEMPOTENCY_CONFLICT", "command id was used with another payload", false)
			return
		}
		if errors.Is(err, workflowstore.ErrPermissionDenied) {
			fail(w, 403, "PERMISSION_DENIED", "command belongs to another owner", false)
			return
		}
		if err != nil {
			fail(w, 503, "COMMAND_FAILED", err.Error(), true)
			return
		}
		writeJSON(w, result.HTTPStatus, envelope{Data: json.RawMessage(result.ResponseJSON)})
	}
}

type capture struct {
	header http.Header
	body   bytes.Buffer
	status int
}

func (c *capture) Header() http.Header    { return c.header }
func (c *capture) WriteHeader(status int) { c.status = status }
func (c *capture) Write(value []byte) (int, error) {
	if c.status == 0 {
		c.status = 200
	}
	return c.body.Write(value)
}
