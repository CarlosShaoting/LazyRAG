package domain

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestSessionPublicPayloadUsesWorkflowNames(t *testing.T) {
	payload, err := json.Marshal(Session{WorkflowID: "wf", WorkflowRevision: "rev"})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), "plugin") {
		t.Fatalf("legacy name leaked into public payload: %s", payload)
	}
}

func TestLegacyRouteFeatureFlagRollback(t *testing.T) {
	if got := PublicRoute(true); got != "/api/workflows" {
		t.Fatal(got)
	}
	if got := PublicRoute(false); got != "/api/plugins" {
		t.Fatal(got)
	}
}

func TestPhysicalPersistenceMappingRemainsCompatible(t *testing.T) {
	if (Session{}).TableName() != "plugin_sessions" {
		t.Fatal("physical table must remain stable")
	}
}
