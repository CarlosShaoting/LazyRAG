package store

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func testRepo(t *testing.T) *Repository {
	t.Helper()
	db, err := gorm.Open(sqlite.Open("file:"+t.Name()+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	repo := New(db)
	if err := repo.AutoMigrate(); err != nil {
		t.Fatal(err)
	}
	return repo
}

func TestPreparationIsOwnerScopedAndConsumedOnce(t *testing.T) {
	repo := testRepo(t)
	ctx := context.Background()
	p1, created, err := repo.Prepare(ctx, "u1", "same", "writer", "workflow.v1", json.RawMessage(`{"x":1}`), json.RawMessage(`{"ready":true}`))
	if err != nil || !created {
		t.Fatalf("prepare: created=%v err=%v", created, err)
	}
	p2, created, err := repo.Prepare(ctx, "u1", "same", "writer", "workflow.v1", json.RawMessage(`{"x":1}`), json.RawMessage(`{"ready":true}`))
	if err != nil || created || p1.ID != p2.ID {
		t.Fatalf("idempotent prepare: %#v %v", p2, err)
	}
	if _, _, err := repo.Consume(ctx, p1.ID, "u2", "s1"); !errors.Is(err, ErrPermissionDenied) {
		t.Fatalf("owner check: %v", err)
	}
	got, consumed, err := repo.Consume(ctx, p1.ID, "u1", "s1")
	if err != nil || !consumed || got.SessionID != "s1" {
		t.Fatalf("consume: %#v %v", got, err)
	}
	got, consumed, err = repo.Consume(ctx, p1.ID, "u1", "other")
	if err != nil || consumed || got.SessionID != "s1" {
		t.Fatalf("second consume: %#v %v", got, err)
	}
}

func TestCommandExecutesOnceAndRejectsPayloadConflict(t *testing.T) {
	repo := testRepo(t)
	ctx := context.Background()
	var calls atomic.Int32
	execute := func(_ *gorm.DB) (int, json.RawMessage, error) {
		calls.Add(1)
		return 200, json.RawMessage(`{"accepted":true}`), nil
	}
	first, created, err := repo.Command(ctx, "u1", "s1", "cmd", "workflow.v1", []byte(`{"step":"a"}`), execute)
	if err != nil || !created {
		t.Fatalf("first: %#v %v", first, err)
	}
	second, created, err := repo.Command(ctx, "u1", "s1", "cmd", "workflow.v1", []byte(`{"step":"a"}`), execute)
	if err != nil || created || string(second.ResponseJSON) != string(first.ResponseJSON) {
		t.Fatalf("replay: %#v %v", second, err)
	}
	if calls.Load() != 1 {
		t.Fatalf("execute calls=%d", calls.Load())
	}
	events, err := repo.Replay(ctx, "s1", "u1", 0, 100)
	if err != nil || len(events) != 1 || events[0].CommandID != "cmd" || events[0].EventType != "workflow.patch" {
		t.Fatalf("durable command event=%#v err=%v", events, err)
	}
	_, _, err = repo.Command(ctx, "u1", "s1", "cmd", "workflow.v1", []byte(`{"step":"b"}`), execute)
	if !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("conflict=%v", err)
	}
}

func TestConcurrentPreparationDeduplicates(t *testing.T) {
	repo := testRepo(t)
	var wg sync.WaitGroup
	ids := make(chan string, 8)
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p, _, err := repo.Prepare(context.Background(), "u", "key", "wf", "workflow.v1", json.RawMessage(`{}`), json.RawMessage(`{}`))
			if err != nil {
				t.Errorf("prepare: %v", err)
				return
			}
			ids <- p.ID
		}()
	}
	wg.Wait()
	close(ids)
	var want string
	for id := range ids {
		if want == "" {
			want = id
		}
		if id != want {
			t.Fatalf("ids differ: %q != %q", id, want)
		}
	}
}

func TestEventReplayUsesPersistentCursorAndOwner(t *testing.T) {
	repo := testRepo(t)
	ctx := context.Background()
	for _, typ := range []string{"snapshot", "attempt.running", "artifact.saved"} {
		if err := repo.AppendEvent(ctx, &Event{SessionID: "s1", OwnerUserID: "u1", EventType: typ, PayloadJSON: json.RawMessage(`{}`)}); err != nil {
			t.Fatal(err)
		}
	}
	all, err := repo.Replay(ctx, "s1", "u1", 0, 100)
	if err != nil || len(all) != 3 {
		t.Fatalf("all=%d err=%v", len(all), err)
	}
	replay, err := repo.Replay(ctx, "s1", "u1", all[0].ID, 100)
	if err != nil || len(replay) != 2 || replay[0].ID <= all[0].ID {
		t.Fatalf("replay=%#v err=%v", replay, err)
	}
	other, err := repo.Replay(ctx, "s1", "u2", 0, 100)
	if err != nil || len(other) != 0 {
		t.Fatalf("owner leak: %#v %v", other, err)
	}
}
