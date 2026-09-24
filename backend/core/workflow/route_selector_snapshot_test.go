package workflow

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"lazymind/core/common/orm"
	"lazymind/core/workflow/graphengine"
)

func TestRouterSnapshotUsesActualSelectedArtifactAndDoesNotExposePayload(t *testing.T) {
	db := newTestDB(t)
	if err := db.AutoMigrate(&orm.WorkflowInputBinding{}, &orm.WorkflowRouteDecision{}, &orm.WorkflowHumanArtifact{}); err != nil {
		t.Fatal(err)
	}
	graph := &graphengine.CompiledStateGraph{Nodes: map[string]graphengine.CompiledNode{
		"route": {ID: "route", Route: "choice", RouteSelector: &graphengine.RouteSelector{Material: "routing_record", Field: "selected_stage", Targets: map[string]string{"design": "design", "prototype": "prototype"}}},
	}, ControlEdges: []graphengine.CompiledEdge{{From: "route", To: "design", When: "design"}, {From: "route", To: "prototype", When: "prototype"}}}
	artifactID := "human-route-artifact"
	if err := db.Create(&orm.WorkflowHumanArtifact{ID: artifactID, ContentType: "json", Value: json.RawMessage(`{"data":{"selected_stage":"prototype","internal_note":"never-publish-this"}}`)}).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Create(&orm.WorkflowSlotRevision{ID: "route-new", SessionID: "route-session", SlotID: "routing_record", Revision: 2, Selected: true, Validity: "effective", HumanArtifactID: &artifactID,
		ContentSnapshot: json.RawMessage(`{"selected_stage":"design"}`)}).Error; err != nil {
		t.Fatal(err)
	}
	// An unrelated file slot has no loadable body. Metadata-only projection must not
	// read every artifact, or a missing attachment would break all route selection.
	if err := db.Create(&orm.WorkflowSlotRevision{ID: "unrelated", SessionID: "route-session", SlotID: "large_document", Revision: 1, Selected: true, Validity: "effective"}).Error; err != nil {
		t.Fatal(err)
	}
	snapshot, err := loadRuntimeSnapshot(context.Background(), db.DB, "route-session", graph)
	if err != nil {
		t.Fatal(err)
	}
	decision := graphengine.DecideRoute(graph, "route", snapshot.Materials)
	if len(decision.Activated) != 1 || decision.Activated[0] != "prototype" {
		t.Fatalf("must resolve human artifact, not outdated legacy snapshot: %+v", decision)
	}
	encoded, _ := json.Marshal(snapshot)
	if strings.Contains(string(encoded), "never-publish-this") {
		t.Fatal("Router payload leaked through snapshot serialization")
	}
}
