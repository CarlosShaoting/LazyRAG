package contracts

import (
	"encoding/json"
	"fmt"
	"os"
)

const VersionV1 = "workflow.v1"

type Attempt struct {
	AttemptID       string   `json:"attempt_id"`
	StepID          string   `json:"step_id"`
	Status          string   `json:"status"`
	Operation       string   `json:"operation"`
	AttemptNo       int      `json:"attempt_no"`
	PartialSelector []string `json:"partial_selector,omitempty"`
}

type Artifact struct {
	ArtifactID        string `json:"artifact_id"`
	Slot              string `json:"slot"`
	Revision          int    `json:"revision"`
	ProducerAttemptID string `json:"producer_attempt_id"`
	Stale             bool   `json:"stale"`
}

type Event struct {
	Cursor   int    `json:"cursor"`
	Type     string `json:"type"`
	EntityID string `json:"entity_id"`
}

type Projection struct {
	SessionID    string   `json:"session_id"`
	Status       string   `json:"status"`
	ReadySteps   []string `json:"ready_steps"`
	StateVersion int      `json:"state_version"`
}

type GoldenScenario struct {
	ContractVersion string         `json:"contract_version"`
	Scenario        string         `json:"scenario"`
	Input           map[string]any `json:"input"`
	Projection      Projection     `json:"projection"`
	Attempts        []Attempt      `json:"attempts"`
	Artifacts       []Artifact     `json:"artifacts"`
	Events          []Event        `json:"events"`
}

func ReadGolden(path string) (GoldenScenario, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return GoldenScenario{}, err
	}
	var fixture GoldenScenario
	if err := json.Unmarshal(data, &fixture); err != nil {
		return GoldenScenario{}, err
	}
	if err := fixture.Validate(); err != nil {
		return GoldenScenario{}, err
	}
	return fixture, nil
}

func (f GoldenScenario) Validate() error {
	if f.ContractVersion != VersionV1 || f.Scenario == "" || f.Projection.SessionID == "" {
		return fmt.Errorf("invalid workflow fixture identity")
	}
	previous := 0
	for _, event := range f.Events {
		if event.Cursor <= previous || event.Type == "" || event.EntityID == "" {
			return fmt.Errorf("invalid event sequence at cursor %d", event.Cursor)
		}
		previous = event.Cursor
	}
	for _, attempt := range f.Attempts {
		if attempt.AttemptID == "" || attempt.StepID == "" || attempt.AttemptNo < 1 {
			return fmt.Errorf("invalid attempt fixture")
		}
	}
	return nil
}
