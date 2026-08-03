package compat

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLegacyRoutesFlagDefaultsOnAndCanRollback(t *testing.T) {
	t.Setenv(LegacyRoutesEnv, "")
	if !LegacyRoutesEnabled() {
		t.Fatal("compatibility must default on during migration")
	}
	t.Setenv(LegacyRoutesEnv, "false")
	if LegacyRoutesEnabled() {
		t.Fatal("legacy route flag did not disable aliases")
	}
}

func TestLegacyRouteMetricsTrackCallerAndRoute(t *testing.T) {
	metrics := NewRouteMetrics()
	handler := metrics.Wrap("/plugins", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})
	r := httptest.NewRequest(http.MethodGet, "/plugins", nil)
	r.Header.Set("X-LazyMind-Workflow-Caller", "algorithm-chat")
	handler(httptest.NewRecorder(), r)
	if got := metrics.Count("algorithm-chat", "/plugins"); got != 1 {
		t.Fatalf("count = %d", got)
	}
}

func TestCallerUsesBoundedMetadata(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/", nil)
	if Caller(r) != "unknown" {
		t.Fatal(Caller(r))
	}
	r.Header.Set("X-LazyMind-Workflow-Caller", "frontend")
	if Caller(r) != "frontend" {
		t.Fatal(Caller(r))
	}
}
