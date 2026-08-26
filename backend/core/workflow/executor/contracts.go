package executor

import (
	"context"
	"encoding/json"
)

// AttemptContext is the immutable Host-neutral execution snapshot used by
// trusted Executor boundaries. It never contains a model configuration, API
// credential or Host-local path. Public adapters must redact Metadata.
type AttemptContext struct {
	ContractVersion     string            `json:"contract_version"`
	SessionID           string            `json:"session_id"`
	AttemptID           string            `json:"attempt_id"`
	StepID              string            `json:"step_id"`
	AttemptNo           int               `json:"attempt_no"`
	Operation           string            `json:"operation"`
	Objective           string            `json:"objective,omitempty"`
	Prompt              string            `json:"prompt,omitempty"`
	Acceptance          []string          `json:"acceptance_criteria,omitempty"`
	Instruction         string            `json:"instruction,omitempty"`
	PartialSelector     map[string][]int  `json:"partial_selector,omitempty"`
	WorkflowRevision    string            `json:"workflow_revision"`
	Inputs              map[string]any    `json:"inputs,omitempty"`
	DeclaredInputTypes  map[string]string `json:"declared_input_types,omitempty"`
	DeclaredOutputs     []string          `json:"declared_outputs,omitempty"`
	DeclaredOutputTypes map[string]string `json:"declared_output_types,omitempty"`
	RequiredOutputs     []string          `json:"required_outputs,omitempty"`
	OutputCardinality   map[string]string `json:"output_cardinality,omitempty"`
	Capabilities        []string          `json:"capabilities,omitempty"`
	LegacyTools         []string          `json:"legacy_tools,omitempty"`
	TerminalTools       []string          `json:"terminal_tools,omitempty"`
	ToolsOnly           bool              `json:"tools_only,omitempty"`
	Resume              *ResumeCheckpoint `json:"resume,omitempty"`
	Metadata            map[string]string `json:"metadata,omitempty"`
}

// ResumeCheckpoint is a Host-neutral description of durable work produced by
// an earlier failed attempt. Every Workflow executor receives the same shape;
// workflow packages do not implement their own retry bookkeeping.
type ResumeCheckpoint struct {
	FromAttemptID    string                      `json:"from_attempt_id"`
	FromTaskID       string                      `json:"from_task_id,omitempty"`
	CompletedOutputs map[string]OutputCheckpoint `json:"completed_outputs,omitempty"`
}

// OutputCheckpoint describes which positions of an output slot are already
// effective. Scalar is true for a single-cardinality value; ListIndices uses
// the Workflow Runtime's stable zero-based list_index values.
type OutputCheckpoint struct {
	Scalar      bool  `json:"scalar,omitempty"`
	ListIndices []int `json:"list_indices,omitempty"`
}

type Artifact struct {
	Slot        string          `json:"slot"`
	ContentType string          `json:"content_type"`
	Value       json.RawMessage `json:"value"`
	Seq         int             `json:"seq"`
}

type Control struct {
	NextStep string `json:"next_step,omitempty"`
}

type Result struct {
	Summary     string         `json:"summary,omitempty"`
	ExecutorRef string         `json:"executor_ref,omitempty"`
	Artifacts   []Artifact     `json:"artifacts,omitempty"`
	Control     *Control       `json:"control,omitempty"`
	Projection  map[string]any `json:"projection,omitempty"`
}

type ContextLoader interface {
	LoadAttemptContext(context.Context, string) (AttemptContext, error)
}

type ArtifactSink interface {
	Save(context.Context, AttemptContext, Artifact) error
}
