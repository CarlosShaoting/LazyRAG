package runtime

import (
	"errors"
	"sync"
)

var (
	ErrVersionUnsupported = errors.New("CONTRACT_VERSION_UNSUPPORTED")
	ErrCommandConflict    = errors.New("VERSION_CONFLICT")
)

type Preparation struct {
	ID            string            `json:"preparation_id"`
	WorkflowID    string            `json:"workflow_id"`
	Actor         string            `json:"actor"`
	InputBindings map[string]string `json:"input_bindings"`
	Consumed      bool              `json:"consumed"`
}

type Event struct {
	Cursor   int64          `json:"cursor"`
	Type     string         `json:"type"`
	EntityID string         `json:"entity_id"`
	Patch    map[string]any `json:"patch"`
}

type CommandResult struct {
	CommandID string         `json:"command_id"`
	Result    map[string]any `json:"result"`
}

type Facade struct {
	mu           sync.Mutex
	preparations map[string]Preparation
	commands     map[string]CommandResult
	events       map[string][]Event
}

func NewFacade() *Facade {
	return &Facade{preparations: map[string]Preparation{}, commands: map[string]CommandResult{}, events: map[string][]Event{}}
}

func (f *Facade) Prepare(version string, preparation Preparation) (Preparation, error) {
	if version != "workflow.v1" {
		return Preparation{}, ErrVersionUnsupported
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if existing, ok := f.preparations[preparation.ID]; ok {
		return existing, nil
	}
	f.preparations[preparation.ID] = preparation
	return preparation, nil
}

func (f *Facade) ConsumePreparation(id string) (Preparation, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	p, ok := f.preparations[id]
	if !ok {
		return Preparation{}, errors.New("PREPARATION_EXPIRED")
	}
	p.Consumed = true
	f.preparations[id] = p
	return p, nil
}

func (f *Facade) Command(id string, result map[string]any) CommandResult {
	f.mu.Lock()
	defer f.mu.Unlock()
	if existing, ok := f.commands[id]; ok {
		return existing
	}
	created := CommandResult{CommandID: id, Result: result}
	f.commands[id] = created
	return created
}

func (f *Facade) Append(sessionID, eventType, entityID string, patch map[string]any) Event {
	f.mu.Lock()
	defer f.mu.Unlock()
	event := Event{Cursor: int64(len(f.events[sessionID]) + 1), Type: eventType, EntityID: entityID, Patch: patch}
	f.events[sessionID] = append(f.events[sessionID], event)
	return event
}

func (f *Facade) Replay(sessionID string, after int64) []Event {
	f.mu.Lock()
	defer f.mu.Unlock()
	all := f.events[sessionID]
	if after >= int64(len(all)) {
		return []Event{}
	}
	result := make([]Event, len(all[after:]))
	copy(result, all[after:])
	return result
}
