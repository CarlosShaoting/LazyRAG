package executor

import (
	"context"
	"encoding/json"

	"lazymind/core/common/orm"
	"lazymind/core/state"
	"lazymind/core/subagent"
	"lazymind/core/workflow/attempt"

	"gorm.io/gorm"
)

// DBContextLoader freezes the neutral Attempt Context from the durable outbox
// payload. Runtime-specific paths, models and credentials never enter it.
type DBContextLoader struct{ DB *gorm.DB }

func (loader DBContextLoader) LoadAttemptContext(ctx context.Context, id string) (AttemptContext, error) {
	var row orm.WorkflowSessionStep
	if err := loader.DB.WithContext(ctx).Where("id = ?", id).First(&row).Error; err != nil {
		return AttemptContext{}, err
	}
	var outbox orm.WorkflowOutbox
	if err := loader.DB.WithContext(ctx).Where("attempt_id = ?", id).First(&outbox).Error; err != nil {
		return AttemptContext{}, err
	}
	value := AttemptContext{ContractVersion: attempt.ContractVersion, SessionID: row.SessionID, AttemptID: row.ID, StepID: row.StepID, AttemptNo: row.Attempt}
	if len(outbox.PayloadJSON) != 0 {
		if err := json.Unmarshal(outbox.PayloadJSON, &value); err != nil {
			return AttemptContext{}, err
		}
	}
	value.ContractVersion, value.SessionID, value.AttemptID, value.StepID, value.AttemptNo = attempt.ContractVersion, row.SessionID, row.ID, row.StepID, row.Attempt
	return value, nil
}

type LazyMindAdapter struct {
	DB            *gorm.DB
	State         state.Store
	WorkspacePath string
	DBDSN         string
	LLMConfig     map[string]any
	ToolConfig    map[string]any
}

// BuildRunSpec is the sole Attempt Context -> LazyMind AgentRunPlan boundary.
// The Python host still constructs AgentRunPlan from this existing request and
// the authoritative task row; callers cannot inject a model or filesystem path.
func (adapter LazyMindAdapter) BuildRunSpec(_ context.Context, value AttemptContext) (HostRunSpec, error) {
	if value.AttemptID == "" || value.Operation == "" {
		return HostRunSpec{}, executorError("attempt_id and operation are required")
	}
	return HostRunSpec{Attempt: value, Params: map[string]any{"operation": value.Operation, "objective": value.Objective, "inputs": value.Inputs, "capabilities": value.Capabilities}}, nil
}

func (adapter LazyMindAdapter) RunSubAgent(ctx context.Context, spec HostRunSpec, callbacks Callbacks) (Result, error) {
	request := subagent.RunRequest{TaskID: spec.Attempt.AttemptID, AgentType: "workflow_step", Params: spec.Params,
		WorkspacePath: adapter.WorkspacePath, DBDSN: adapter.DBDSN, LLMConfig: adapter.LLMConfig, ToolConfig: adapter.ToolConfig}
	result := Result{ExecutorRef: request.TaskID}
	err := subagent.RunObserved(ctx, adapter.DB, adapter.State, request, func(event subagent.TaskEvent) error {
		switch event.Type {
		case "progress", "task_start":
			if callbacks.Progress != nil {
				value, _ := json.Marshal(map[string]any{"progress": event.Progress, "phase": event.CurrentPhase})
				return callbacks.Progress(value)
			}
		case "artifact":
			artifact := Artifact{Slot: event.ArtifactKey, ContentType: event.ContentType, Value: event.Value, Seq: event.Seq}
			result.Artifacts = append(result.Artifacts, artifact)
			if callbacks.Artifact != nil {
				return callbacks.Artifact(artifact)
			}
		case "done":
			result.Summary = event.Summary
		case "error":
			return executorError(event.Message)
		}
		return nil
	})
	return result, err
}

func (adapter LazyMindAdapter) Cancel(_ context.Context, _ string) error { return nil }

// Mode is an explicit rollback switch. legacy performs no canonical claim;
// shadow compares output but leaves legacy authoritative; canary enables it for
// the configured percentage; canonical enables all eligible Attempts.
type Mode string

const (
	ModeLegacy    Mode = "legacy"
	ModeShadow    Mode = "shadow"
	ModeCanary    Mode = "canary"
	ModeCanonical Mode = "canonical"
)

func UseCanonical(mode Mode, canaryPercent, bucket int, schemaCapable bool) bool {
	if !schemaCapable || mode == ModeLegacy || mode == ModeShadow {
		return false
	}
	if mode == ModeCanonical {
		return true
	}
	return mode == ModeCanary && canaryPercent > 0 && bucket >= 0 && bucket%100 < canaryPercent
}
