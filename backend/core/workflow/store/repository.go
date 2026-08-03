package store

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

var (
	ErrNotFound            error = repositoryError("WORKFLOW_NOT_FOUND")
	ErrPermissionDenied    error = repositoryError("PERMISSION_DENIED")
	ErrIdempotencyConflict error = repositoryError("IDEMPOTENCY_CONFLICT")
)

type repositoryError string

func (e repositoryError) Error() string { return string(e) }

type Repository struct {
	db   *gorm.DB
	mu   sync.RWMutex
	subs map[string]map[chan Event]struct{}
}

func New(db *gorm.DB) *Repository {
	return &Repository{db: db, subs: map[string]map[chan Event]struct{}{}}
}

func Models() []any {
	return []any{&Preparation{}, &Event{}, &Command{}, &InputResource{}, &InputBinding{}}
}

func (r *Repository) ImportInputResource(ctx context.Context, owner, name, mime, hash string, content []byte) (InputResource, bool, error) {
	var existing InputResource
	err := r.db.WithContext(ctx).Where("owner_user_id = ? AND content_hash = ?", owner, hash).First(&existing).Error
	if err == nil {
		return existing, false, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return InputResource{}, false, err
	}
	created := InputResource{ID: uuid.NewString(), OwnerUserID: owner, Name: name, MimeType: mime,
		Size: int64(len(content)), ContentHash: hash, Revision: 1, Content: content, CreatedAt: time.Now().UTC()}
	if err := r.db.WithContext(ctx).Create(&created).Error; err != nil {
		return InputResource{}, false, err
	}
	return created, true, nil
}

func (r *Repository) BindInput(ctx context.Context, owner string, binding InputBinding) error {
	if err := r.AuthorizeSession(ctx, binding.WorkflowSessionID, owner); err != nil {
		return err
	}
	var resource InputResource
	if err := r.db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", binding.ResourceID, owner).First(&resource).Error; err != nil {
		return ErrPermissionDenied
	}
	if resource.Revision != binding.ResourceRevision || resource.ContentHash != binding.ContentHash {
		return ErrIdempotencyConflict
	}
	binding.ID = uuid.NewString()
	binding.CreatedAt = time.Now().UTC()
	binding.Validity = "effective"
	return r.db.WithContext(ctx).Create(&binding).Error
}

func (r *Repository) AutoMigrate() error { return r.db.AutoMigrate(Models()...) }

func (r *Repository) PreparationByKey(ctx context.Context, owner, key string) (Preparation, error) {
	var prepared Preparation
	err := r.db.WithContext(ctx).Where("owner_user_id = ? AND idempotency_key = ?", owner, key).First(&prepared).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return Preparation{}, ErrNotFound
	}
	return prepared, err
}

func (r *Repository) Prepare(ctx context.Context, owner, key, workflowID, version string, request, response json.RawMessage) (Preparation, bool, error) {
	var existing Preparation
	err := r.db.WithContext(ctx).Where("owner_user_id = ? AND idempotency_key = ?", owner, key).First(&existing).Error
	if err == nil {
		return existing, false, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return Preparation{}, false, err
	}
	now := time.Now().UTC()
	created := Preparation{ID: uuid.NewString(), IdempotencyKey: key, OwnerUserID: owner, WorkflowID: workflowID, ContractVersion: version, RequestJSON: request, ResponseJSON: response, CreatedAt: now, UpdatedAt: now}
	result := r.db.WithContext(ctx).Clauses(clause.OnConflict{DoNothing: true}).Create(&created)
	if result.Error != nil {
		return Preparation{}, false, result.Error
	}
	if result.RowsAffected == 0 {
		if err := r.db.WithContext(ctx).Where("owner_user_id = ? AND idempotency_key = ?", owner, key).First(&existing).Error; err != nil {
			return Preparation{}, false, err
		}
		return existing, false, nil
	}
	return created, true, nil
}

func (r *Repository) Consume(ctx context.Context, id, owner, sessionID string) (Preparation, bool, error) {
	var result Preparation
	consumed := false
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("id = ?", id).First(&result).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrNotFound
			}
			return err
		}
		if result.OwnerUserID != owner {
			return ErrPermissionDenied
		}
		if result.ConsumedAt != nil {
			return nil
		}
		now := time.Now().UTC()
		if err := tx.Model(&Preparation{}).Where("id = ? AND consumed_at IS NULL", id).Updates(map[string]any{"consumed_at": now, "session_id": sessionID, "updated_at": now}).Error; err != nil {
			return err
		}
		result.ConsumedAt, result.SessionID, result.UpdatedAt = &now, sessionID, now
		consumed = true
		return nil
	})
	return result, consumed, err
}

func requestHash(body []byte) string { sum := sha256.Sum256(body); return hex.EncodeToString(sum[:]) }

func (r *Repository) Command(ctx context.Context, owner, sessionID, commandID, version string, request []byte, execute func(*gorm.DB) (int, json.RawMessage, error)) (Command, bool, error) {
	var result Command
	var committedEvent *Event
	hash := requestHash(request)
	created := false
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("command_id = ?", commandID).First(&result).Error; err == nil {
			if result.OwnerUserID != owner {
				return ErrPermissionDenied
			}
			if result.RequestHash != hash {
				return ErrIdempotencyConflict
			}
			return nil
		} else if !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		status, response, err := execute(tx)
		if err != nil {
			return err
		}
		result = Command{CommandID: commandID, OwnerUserID: owner, SessionID: sessionID, ContractVersion: version, RequestHash: hash, HTTPStatus: status, ResponseJSON: response, CreatedAt: time.Now().UTC()}
		if err := tx.Create(&result).Error; err != nil {
			return err
		}
		if status < 400 {
			var responseObject map[string]any
			_ = json.Unmarshal(response, &responseObject)
			stateVersion, _ := responseObject["state_version"].(float64)
			event := &Event{SessionID: sessionID, OwnerUserID: owner, ContractVersion: version, EventType: "workflow.patch", EntityID: sessionID, StateVersion: int64(stateVersion), CommandID: commandID, PayloadJSON: response, CreatedAt: time.Now().UTC()}
			if err := tx.Create(event).Error; err != nil {
				return err
			}
			committedEvent = event
		}
		created = true
		return nil
	})
	if err != nil {
		return Command{}, false, err
	}
	if committedEvent != nil {
		r.publish(*committedEvent)
	}
	return result, created, nil
}

func (r *Repository) AppendEvent(ctx context.Context, event *Event) error {
	if event.ContractVersion == "" {
		event.ContractVersion = "workflow.v1"
	}
	event.CreatedAt = time.Now().UTC()
	if err := r.db.WithContext(ctx).Create(event).Error; err != nil {
		return err
	}
	r.publish(*event)
	return nil
}

func (r *Repository) publish(event Event) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for ch := range r.subs[event.SessionID] {
		select {
		case ch <- event:
		default:
		}
	}
}

func (r *Repository) Replay(ctx context.Context, sessionID, owner string, after int64, limit int) ([]Event, error) {
	if limit <= 0 || limit > 1000 {
		limit = 1000
	}
	var events []Event
	err := r.db.WithContext(ctx).Where("session_id = ? AND owner_user_id = ? AND id > ?", sessionID, owner, after).Order("id ASC").Limit(limit).Find(&events).Error
	return events, err
}

func (r *Repository) AuthorizeSession(ctx context.Context, sessionID, owner string) error {
	var count int64
	if err := r.db.WithContext(ctx).Table("plugin_sessions").Where("id = ? AND create_user_id = ?", sessionID, owner).Count(&count).Error; err != nil {
		return err
	}
	if count == 0 {
		return ErrPermissionDenied
	}
	return nil
}

func (r *Repository) Subscribe(sessionID string) (<-chan Event, func()) {
	ch := make(chan Event, 32)
	r.mu.Lock()
	if r.subs[sessionID] == nil {
		r.subs[sessionID] = map[chan Event]struct{}{}
	}
	r.subs[sessionID][ch] = struct{}{}
	r.mu.Unlock()
	return ch, func() {
		r.mu.Lock()
		if _, ok := r.subs[sessionID][ch]; ok {
			delete(r.subs[sessionID], ch)
			close(ch)
		}
		r.mu.Unlock()
	}
}
