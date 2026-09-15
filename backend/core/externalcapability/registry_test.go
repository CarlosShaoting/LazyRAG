package externalcapability

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"lazymind/core/capability"
	"lazymind/core/common/orm"
)

func TestRegistrySearchUsesVerifiedOwnConfigAndFreshGrant(t *testing.T) {
	db := testDB(t)
	now := time.Now().UTC()
	for _, row := range []any{
		&orm.UserModelProvider{ID: "search-provider", Name: "Tavily", Category: "search", BaseModel: orm.BaseModel{CreateUserID: "user-1"}},
		&orm.UserModelProviderGroup{ID: "search-group", UserModelProviderID: "search-provider", APIKey: "test-search-key", IsVerified: true, BaseModel: orm.BaseModel{CreateUserID: "user-1"}},
		&orm.UserSelectedProvider{UserID: "user-1", Category: "search", UserModelProviderGroupID: "search-group", CreatedAt: now, UpdatedAt: now},
	} {
		if err := db.Create(row).Error; err != nil {
			t.Fatal(err)
		}
	}
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-LazyMind-Internal-Token") != "test-internal" {
			t.Error("missing internal auth")
		}
		var input struct {
			ToolConfig map[string]any `json:"tool_config"`
		}
		if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
			t.Fatal(err)
		}
		available := input.ToolConfig["tavily"] == "test-search-key"
		if r.URL.Path == "/api/chat/tools/external-catalog" {
			_ = json.NewEncoder(w).Encode(map[string]any{"items": []any{map[string]any{
				"name": "web_search", "available": available, "input_schema": map[string]any{"type": "object"},
			}}})
			return
		}
		if !available {
			t.Error("search credential was not injected")
		}
		calls++
		_, _ = w.Write([]byte(`{"result":{"results":[{"title":"test","url":"https://example.com"}]}}`))
	}))
	defer server.Close()
	t.Setenv("LAZYMIND_CHAT_SERVICE_URL", server.URL)
	t.Setenv("LAZYMIND_AUTH_SERVICE_INTERNAL_TOKEN", "test-internal")
	s := New(db, server.Client())
	ctx := context.Background()
	call := capability.InvocationContext{Principal: capability.Principal{UserID: "user-1"}, ExternalAgent: "codex"}
	input := capability.InvokeExternalToolInput{ToolID: "builtin:web_search", Arguments: map[string]any{"query": "test"}}
	if _, err := s.InvokeExternalTool(ctx, call, input); err == nil {
		t.Fatal("default authorization must be closed")
	}
	grant := GrantUpdate{Agent: "codex", CapabilityType: CapabilityTool, CapabilityID: input.ToolID, Enabled: true}
	if err := s.SetGrant(ctx, "user-1", grant); err != nil {
		t.Fatal(err)
	}
	if _, err := s.InvokeExternalTool(ctx, call, input); err != nil {
		t.Fatal(err)
	}
	call.ExternalAgent = "cursor"
	if _, err := s.InvokeExternalTool(ctx, call, input); err == nil {
		t.Fatal("another Agent must be denied")
	}
	call.ExternalAgent = "codex"
	if err := db.Model(&orm.UserModelProviderGroup{}).Where("id = ?", "search-group").Update("is_verified", false).Error; err != nil {
		t.Fatal(err)
	}
	if _, err := s.InvokeExternalTool(ctx, call, input); err == nil {
		t.Fatal("unverified provider must be denied")
	}
	grant.Enabled = false
	if err := s.SetGrant(ctx, "user-1", grant); err != nil {
		t.Fatal(err)
	}
	if _, err := s.InvokeExternalTool(ctx, call, input); err == nil {
		t.Fatal("revoked grant must be denied")
	}
	if calls != 1 {
		t.Fatalf("unexpected executions: %d", calls)
	}
}
