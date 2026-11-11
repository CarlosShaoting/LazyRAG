package workflow

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"gorm.io/gorm"
	"lazymind/core/common"
	"lazymind/core/common/orm"
	"lazymind/core/store"
	"lazymind/core/workflow/attempt"
	"lazymind/core/workflow/controlstore"
	"lazymind/core/workflow/executor"
)

// Each Workflow session admits at most two model jobs. Running workers retain
// their reservation until exit is acknowledged, including after cancellation.
const codexModelCapacity = 2
const codexModelSlot = "__codex_model_generation"

type codexModelRequest struct {
	AttemptID string          `json:"attempt_id"`
	LeaseHash string          `json:"lease_hash"`
	Hash      string          `json:"request_hash"`
	Request   json.RawMessage `json:"request"`
}

type codexModelResult struct {
	WorkerHash string          `json:"worker_hash,omitempty"`
	Message    json.RawMessage `json:"message,omitempty"`
	Error      string          `json:"error,omitempty"`
}

func codexModelEnabled(session orm.WorkflowSession) bool {
	return controlstore.Controlled(session) && (session.WorkflowID == "paper-writing" || session.WorkflowID == "writer-workflow")
}

func modelAttemptValid(tx *gorm.DB, request codexModelRequest) (bool, error) {
	var row orm.WorkflowSessionStep
	if err := tx.First(&row, "id = ?", request.AttemptID).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return false, nil
		}
		return false, err
	}
	return (row.Status == "claimed" || row.Status == "running") && row.Validity != "stale" && row.ExecutorHost == "lazymind" &&
		controlstore.Hash([]byte(row.LeaseToken)) == request.LeaseHash && row.LeaseExpiresAt != nil && row.LeaseExpiresAt.After(time.Now()), nil
}

// Called only under controlstore.Transaction's session lock. Both admissions and
// releases use this lock, including different API workers and simultaneous runs.
func dispatchCodexModels(tx *gorm.DB, session orm.WorkflowSession) error {
	binding, err := controlstore.DecodeBinding(session)
	if err != nil {
		return err
	}
	if binding.Provider != "codex" {
		return nil
	}
	var active int64
	if err := tx.Model(&orm.WorkflowActionJob{}).Where("session_id = ? AND slot_id = ? AND status IN ?", session.ID, codexModelSlot,
		[]string{"waiting_agent", "running", "cancel_requested"}).Count(&active).Error; err != nil {
		return err
	}
	if active >= codexModelCapacity || session.Status == "stopped" || session.Status == "failed" || session.Status == "completed" {
		return nil
	}
	var pending []orm.WorkflowActionJob
	if err := tx.Where("session_id = ? AND slot_id = ? AND status = 'queued'", session.ID, codexModelSlot).
		Order("created_at ASC, id ASC").Find(&pending).Error; err != nil {
		return err
	}
	for _, job := range pending {
		if active >= codexModelCapacity {
			break
		}
		var request codexModelRequest
		if err := json.Unmarshal([]byte(job.RequestJSON), &request); err != nil {
			return err
		}
		valid, err := modelAttemptValid(tx, request)
		if err != nil {
			return err
		}
		if !valid {
			if err := tx.Model(&job).Update("status", "cancelled").Error; err != nil {
				return err
			}
			continue
		}
		if err := tx.Model(&job).Update("status", "waiting_agent").Error; err != nil {
			return err
		}
		if _, err := controlstore.EnqueueHostAction(tx, session, "model-generation:"+job.ID, "model_generate", job.ID); err != nil {
			return err
		}
		active++
	}
	return nil
}

func enqueueCodexModel(ctx context.Context, db *gorm.DB, contract executor.AttemptContext, lease string, request json.RawMessage) (orm.WorkflowActionJob, error) {
	job := orm.WorkflowActionJob{ID: common.GenerateID(), SessionID: contract.SessionID, SlotID: codexModelSlot,
		ListIndex: -1, Status: "queued", Version: 1, ResultJSON: "{}"}
	encoded, err := json.Marshal(codexModelRequest{AttemptID: contract.AttemptID,
		LeaseHash: controlstore.Hash([]byte(lease)), Hash: controlstore.Hash(request), Request: request})
	if err != nil {
		return job, err
	}
	job.RequestJSON = string(encoded)
	err = controlstore.Transaction(ctx, db, job.SessionID, func(tx *gorm.DB, session *orm.WorkflowSession) error {
		binding, err := controlstore.DecodeBinding(*session)
		if err != nil || !codexModelEnabled(*session) || binding.Provider != "codex" || binding.ConnectorID == "" || binding.DriverSession == "" {
			return errors.New("a bound Codex document workflow is required")
		}
		var saved codexModelRequest
		_ = json.Unmarshal(encoded, &saved)
		valid, err := modelAttemptValid(tx, saved)
		if err != nil {
			return err
		}
		if !valid || contract.Metadata["model_executor"] != "codex" {
			return errors.New("model request belongs to an inactive attempt")
		}
		job.CreatedAt = time.Now().UTC()
		job.UpdatedAt = job.CreatedAt
		if err := tx.Create(&job).Error; err != nil {
			return err
		}
		return dispatchCodexModels(tx, *session)
	})
	return job, err
}

func cancelCodexModel(db *gorm.DB, job orm.WorkflowActionJob) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = controlstore.Transaction(ctx, db, job.SessionID, func(tx *gorm.DB, session *orm.WorkflowSession) error {
		var current orm.WorkflowActionJob
		if err := tx.First(&current, "id = ?", job.ID).Error; err != nil {
			return err
		}
		status := "cancel_requested"
		if current.Status == "queued" || current.Status == "waiting_agent" {
			status = "cancelled"
		} else if current.Status != "running" {
			return nil
		}
		if err := tx.Model(&current).Update("status", status).Error; err != nil {
			return err
		}
		if status == "cancel_requested" {
			// A running worker must acknowledge exit before this reservation is freed.
			return nil
		}
		// Claim and cancellation share the session lock. An unclaimed notification
		// can be fenced immediately, even if its delivery is already in progress.
		if err := tx.Model(&orm.WorkflowHostAction{}).Where("session_id = ? AND kind = 'model_generate' AND execution_id = ?", session.ID, job.ID).
			Update("consumed_at", time.Now().UTC()).Error; err != nil {
			return err
		}
		return dispatchCodexModels(tx, *session)
	})
}

// CodexModelCompletion is the internal OpenAI-compatible transport for the native
// runtime. Its bearer is an existing fenced attempt lease, not a provider key.
func CodexModelCompletion(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	id := common.PathVar(r, "attempt_id")
	lease := strings.TrimSpace(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
	if lease == "" || attempt.New(db, attempt.Config{}).ValidateLease(r.Context(), id, lease) != nil {
		http.Error(w, "inactive workflow lease", http.StatusUnauthorized)
		return
	}
	contract, err := (executor.DBContextLoader{DB: db}).LoadAttemptContext(r.Context(), id)
	if err != nil || contract.Metadata["model_executor"] != "codex" {
		http.Error(w, "Codex model execution is unavailable", http.StatusConflict)
		return
	}
	var request map[string]json.RawMessage
	if json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<20)).Decode(&request) != nil || len(request["messages"]) == 0 {
		http.Error(w, "messages are required", http.StatusBadRequest)
		return
	}
	encoded, err := json.Marshal(request)
	if err != nil {
		http.Error(w, "invalid generation request", http.StatusBadRequest)
		return
	}
	job, err := enqueueCodexModel(r.Context(), db, contract, lease, encoded)
	if err != nil {
		http.Error(w, "cannot queue Codex generation", http.StatusConflict)
		return
	}
	var streaming bool
	_ = json.Unmarshal(request["stream"], &streaming)
	if streaming {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("X-Accel-Buffering", "no")
		_, _ = fmt.Fprint(w, ": queued\n\n")
		http.NewResponseController(w).Flush()
	}
	// No keepalive frames after admission. The native model client's configured
	// read timeout measures this queued request, including its queue wait.
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-r.Context().Done():
			cancelCodexModel(db, job)
			return
		case <-ticker.C:
			if db.WithContext(r.Context()).First(&job, "id = ?", job.ID).Error != nil {
				cancelCodexModel(db, job)
				return
			}
			if job.Status != "succeeded" && job.Status != "failed" && job.Status != "cancelled" {
				continue
			}
			var result codexModelResult
			_ = json.Unmarshal([]byte(job.ResultJSON), &result)
			if job.Status != "succeeded" {
				if streaming {
					_, _ = fmt.Fprint(w, "data: {\"error\":{\"message\":\"Codex generation ended without a result\"}}\n\ndata: [DONE]\n\n")
					http.NewResponseController(w).Flush()
				} else {
					http.Error(w, "Codex generation ended without a result", http.StatusBadGateway)
				}
				return
			}
			writeCodexModelResult(w, job.ID, result.Message, streaming)
			return
		}
	}
}

func writeCodexModelResult(w http.ResponseWriter, id string, raw json.RawMessage, streaming bool) {
	var message map[string]any
	_ = json.Unmarshal(raw, &message)
	finish := "stop"
	if calls, ok := message["tool_calls"].([]any); ok && len(calls) > 0 {
		finish = "tool_calls"
	}
	choice := map[string]any{"index": 0, "message": message, "finish_reason": finish}
	object := "chat.completion"
	if streaming {
		object = "chat.completion.chunk"
		delete(choice, "message")
		// Native stream decoders use an explicit index for each tool-call delta.
		if calls, ok := message["tool_calls"].([]any); ok {
			for index, call := range calls {
				if value, ok := call.(map[string]any); ok {
					value["index"] = index
				}
			}
		}
		choice["delta"] = message
	} else {
		w.Header().Set("Content-Type", "application/json")
	}
	value := map[string]any{"id": id, "object": object, "created": time.Now().Unix(), "model": "codex", "choices": []any{choice}}
	encoded, _ := json.Marshal(value)
	if streaming {
		_, _ = fmt.Fprintf(w, "data: %s\n\ndata: [DONE]\n\n", encoded)
		http.NewResponseController(w).Flush()
	} else {
		_, _ = w.Write(encoded)
	}
}

type codexModelClaim struct {
	CommandID string `json:"command_id"`
}

func ClaimCodexModel(w http.ResponseWriter, r *http.Request) {
	var input codexModelClaim
	if json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&input) != nil || len(input.CommandID) < 16 || len(input.CommandID) > 255 {
		common.ReplyErr(w, "a stable command_id is required", 400)
		return
	}
	var output map[string]any
	err := controlstore.Transaction(r.Context(), store.DB(), common.PathVar(r, "session_id"), func(tx *gorm.DB, session *orm.WorkflowSession) error {
		if err := controlOwner(*session, store.UserID(r)); err != nil {
			return err
		}
		var job orm.WorkflowActionJob
		if err := tx.Where("id = ? AND session_id = ? AND slot_id = ?", common.PathVar(r, "job_id"), session.ID, codexModelSlot).First(&job).Error; err != nil {
			return err
		}
		var request codexModelRequest
		var result codexModelResult
		if json.Unmarshal([]byte(job.RequestJSON), &request) != nil || json.Unmarshal([]byte(job.ResultJSON), &result) != nil {
			return errors.New("invalid saved model request")
		}
		worker := controlstore.Hash([]byte(input.CommandID))
		if result.WorkerHash != "" && result.WorkerHash != worker {
			output = map[string]any{"status": "already_claimed"}
			return nil
		}
		if job.Status != "waiting_agent" && job.Status != "running" && job.Status != "cancel_requested" {
			output = map[string]any{"status": job.Status}
			return nil
		}
		result.WorkerHash = worker
		status := "running"
		valid, err := modelAttemptValid(tx, request)
		if err != nil {
			return err
		}
		if job.Status == "cancel_requested" || session.Status == "stopped" || session.Status == "failed" || session.Dismissed || !valid {
			status = "cancel_requested"
		}
		encoded, _ := json.Marshal(result)
		if err := tx.Model(&job).Updates(map[string]any{"status": status, "result_json": string(encoded)}).Error; err != nil {
			return err
		}
		output = map[string]any{"status": status, "job_id": job.ID, "request_hash": request.Hash, "worker_token": input.CommandID,
			"capacity": codexModelCapacity, "enqueued_at": job.CreatedAt}
		if status == "running" {
			output["generation_request"] = request.Request
			var ready []string
			if err := tx.Model(&orm.WorkflowActionJob{}).Where("session_id = ? AND slot_id = ? AND status = 'waiting_agent' AND id <> ?", session.ID, codexModelSlot, job.ID).
				Order("created_at ASC, id ASC").Pluck("id", &ready).Error; err != nil {
				return err
			}
			output["ready_job_ids"] = ready
		}
		return nil
	})
	if err != nil {
		common.ReplyErr(w, "model request cannot be claimed", 409)
		return
	}
	common.ReplyOK(w, output)
}

type codexModelResponse struct {
	WorkerToken string          `json:"worker_token"`
	RequestHash string          `json:"request_hash"`
	Message     json.RawMessage `json:"message"`
	Error       string          `json:"error,omitempty"`
	Cancelled   bool            `json:"cancelled,omitempty"`
}

func settleCodexModel(tx *gorm.DB, session orm.WorkflowSession, job *orm.WorkflowActionJob, input codexModelResponse) error {
	var request codexModelRequest
	var result codexModelResult
	if json.Unmarshal([]byte(job.RequestJSON), &request) != nil || json.Unmarshal([]byte(job.ResultJSON), &result) != nil ||
		input.WorkerToken == "" || result.WorkerHash != controlstore.Hash([]byte(input.WorkerToken)) || request.Hash != input.RequestHash {
		return errors.New("model response does not match its claimed request")
	}
	if job.Status == "succeeded" || job.Status == "failed" || job.Status == "cancelled" {
		if string(result.Message) != string(input.Message) || result.Error != input.Error {
			return errors.New("a completed generation cannot be replaced")
		}
		return nil
	}
	if job.Status != "running" && job.Status != "cancel_requested" {
		return errors.New("model request is not running")
	}
	status := "succeeded"
	valid, err := modelAttemptValid(tx, request)
	if err != nil {
		return err
	}
	if input.Cancelled || job.Status == "cancel_requested" || !valid {
		status = "cancelled"
	} else if input.Error != "" {
		status = "failed"
	} else {
		var message struct {
			Role      string           `json:"role"`
			Content   *string          `json:"content"`
			ToolCalls []map[string]any `json:"tool_calls"`
		}
		if json.Unmarshal(input.Message, &message) != nil || message.Role != "assistant" || (message.Content == nil && len(message.ToolCalls) == 0) {
			return errors.New("an assistant message is required")
		}
	}
	result.Message, result.Error = input.Message, input.Error
	encoded, _ := json.Marshal(result)
	if err := tx.Model(job).Updates(map[string]any{"status": status, "result_json": string(encoded)}).Error; err != nil {
		return err
	}
	if err := tx.Model(&orm.WorkflowHostAction{}).Where("session_id = ? AND kind = 'model_generate' AND execution_id = ?", session.ID, job.ID).Update("consumed_at", time.Now().UTC()).Error; err != nil {
		return err
	}
	return dispatchCodexModels(tx, session)
}

func SubmitCodexModel(w http.ResponseWriter, r *http.Request) {
	var input codexModelResponse
	if json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<20)).Decode(&input) != nil {
		common.ReplyErr(w, "invalid model response", 400)
		return
	}
	err := controlstore.Transaction(r.Context(), store.DB(), common.PathVar(r, "session_id"), func(tx *gorm.DB, session *orm.WorkflowSession) error {
		if err := controlOwner(*session, store.UserID(r)); err != nil {
			return err
		}
		var job orm.WorkflowActionJob
		if err := tx.Where("id = ? AND session_id = ? AND slot_id = ?", common.PathVar(r, "job_id"), session.ID, codexModelSlot).First(&job).Error; err != nil {
			return err
		}
		return settleCodexModel(tx, *session, &job, input)
	})
	if err != nil {
		common.ReplyErr(w, "model response is stale or invalid", 409)
		return
	}
	common.ReplyOK(w, map[string]any{"accepted": true})
}
