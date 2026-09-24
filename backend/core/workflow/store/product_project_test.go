package store

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"

	"lazymind/core/common/orm"
)

func productProjectFixture(t *testing.T) *Repository {
	t.Helper()
	r := productRelayFixture(t)
	digest := requestHash([]byte("Exact approved file bytes, not a generated summary"))
	manifest := map[string]any{"artifact_id": "direction-v1", "title": "方向说明", "version": "1.0", "status": "reviewable", "eligible_next_stages": []string{"design"}, "host_artifact": map[string]any{"slot": "direction_document", "source_session_id": "source", "content_sha256": digest}, "open_questions": []any{map[string]any{"question_id": "Q1", "question": "明确预算", "blocking": false, "runtime_secret": "never-expose"}}}
	manifestJSON, _ := json.Marshal(manifest)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'manifest-r1'").Update("content_snapshot", manifestJSON)
	workspace := map[string]any{"workspace_id": "stable-project", "name": "共享产品项目", "current_run": map[string]any{"run_status": "awaiting-stage-confirmation", "selected_stage": "direction"}, "decisions": []any{map[string]any{"decision_id": "D1", "status": "proposed", "decision": "目标用户", "risk": "high", "internal_path": "never-expose"}}, "artifacts": []any{manifest}}
	workspaceJSON, _ := json.Marshal(workspace)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Update("content_snapshot", workspaceJSON)
	var revision orm.WorkflowRevision
	r.db.First(&revision, "id = 'published'")
	var graph map[string]any
	json.Unmarshal(revision.CompiledGraph, &graph)
	producers := graph["material_producers"].(map[string]any)
	for _, material := range []string{"upstream_design", "upstream_prd", "upstream_prototype", "upstream_competitive", "upstream_review", "upstream_handoff", "execution_depth", "word_target", "reference_sample_choice", "reference_sample"} {
		producers[material] = map[string]any{"kind": "external"}
	}
	compiled, _ := json.Marshal(graph)
	r.db.Model(&revision).Update("compiled_graph", compiled)
	return r
}

func productRelayTo(t *testing.T, r *Repository, source, stage, key string, version int64) string {
	t.Helper()
	response, err := r.RelayProductStage(context.Background(), "owner", source, ProductRelayRequest{Action: "switch-stage", SelectedStage: stage, IdempotencyKey: key, ExpectedStateVersion: version, RequestContext: "保留既有内容，只完善这个阶段"})
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	json.Unmarshal(response, &result)
	return result["session_id"].(string)
}

func productBoundContents(t *testing.T, r *Repository, session string) map[string]string {
	t.Helper()
	bindings, err := r.ListInputBindings(context.Background(), "owner", session)
	if err != nil {
		t.Fatal(err)
	}
	result := map[string]string{}
	for _, binding := range bindings {
		resource, err := r.GetInputResource(context.Background(), "owner", binding.ResourceID)
		if err != nil {
			t.Fatal(err)
		}
		result[binding.MaterialID] = string(resource.Content)
	}
	return result
}

func TestProductProjectAvailableDuringActiveSuccessorAndPinnedAfterSourceEdit(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	nextID := productRelayTo(t, r, "source", "design", "shared-design", 9)
	summary, err := r.ProductRelaySummary(ctx, "owner", nextID)
	if err != nil {
		t.Fatal(err)
	}
	project := summary["project"].(map[string]any)
	if summary["can_relay"] != false || summary["current_stage"] != "design" || project["workspace_id"] != "stable-project" || project["conversation_id"] != "conversation" {
		t.Fatalf("active project lost: %#v", summary)
	}
	public, _ := json.Marshal(summary)
	if strings.Contains(string(public), "never-expose") || strings.Contains(string(public), "host_artifact_bindings") {
		t.Fatalf("internal state leaked: %s", public)
	}
	views := project["artifacts"].([]map[string]any)
	if len(views) != 1 || views[0]["stage"] != "direction" || views[0]["version"] != "1.0" || views[0]["revision_id"] != "business-r7" {
		t.Fatalf("bad shared views: %#v", views)
	}
	preview, err := r.ProductProjectArtifact(ctx, "owner", nextID, "direction")
	if err != nil || preview["content"] != "Exact approved file bytes, not a generated summary" || preview["content_format"] != "markdown" || preview["stale"] != false {
		t.Fatalf("preview: %#v %v", preview, err)
	}
	// Relay archives the source session, so a user patch is correctly denied.
	// Simulate an out-of-band later source revision to verify the pinned view.
	if err := r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = ?", "business-r7").Update("selected", false).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Create(&orm.WorkflowSlotRevision{ID: "business-r8", SessionID: "source", SlotID: "direction_document", Slot: "direction_document", Revision: 8, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(`"Changed later source"`), CreatedAt: time.Now().UTC()}).Error; err != nil {
		t.Fatal(err)
	}
	pinned, err := r.ProductProjectArtifact(ctx, "owner", nextID, "direction")
	if err != nil || pinned["content"] != preview["content"] || pinned["stale"] != true || pinned["artifact_id"] != preview["artifact_id"] {
		t.Fatalf("source edit silently changed snapshot: %#v %v", pinned, err)
	}
	var conversations int64
	r.db.Model(&orm.Conversation{}).Count(&conversations)
	if conversations != 1 {
		t.Fatal("stage selection created another conversation")
	}
}

func TestProductProjectCurrentSameStageDraftWinsWithoutFalseAcceptance(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	nextID := productRelayTo(t, r, "source", "direction", "revise-direction", 9)
	before, err := r.ProductProjectArtifact(ctx, "owner", nextID, "direction")
	if err != nil {
		t.Fatal(err)
	}
	r.db.Create(&orm.WorkflowSlotRevision{ID: "new-output", SessionID: nextID, SlotID: "direction_document", Slot: "direction_document", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(`"Updated current content"`), CreatedAt: time.Now().UTC()})
	after, err := r.ProductProjectArtifact(ctx, "owner", nextID, "direction")
	if err != nil || after["content"] != "Updated current content" || after["status"] != "draft" || after["revision_id"] != "new-output" || after["artifact_id"] != before["artifact_id"] {
		t.Fatalf("same logical view failed: %#v %v", after, err)
	}
	summary, _ := r.ProductRelaySummary(ctx, "owner", nextID)
	if len(summary["project"].(map[string]any)["artifacts"].([]map[string]any)) != 1 {
		t.Fatal("same stage created duplicate project tabs")
	}
}

func TestProductProjectDefaultsToHTMLAndReadsMarkdownFromSameLogicalVersion(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	html := "<!doctype html><html><head><title>方向</title></head><body><h1>共享方向</h1></body></html>"
	r.db.Create(&orm.WorkflowSlotRevision{ID: "direction-html-r1", SessionID: "source", SlotID: "direction_document_html", Slot: "direction_document_html", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(strconv.Quote(html)), CreatedAt: time.Now().UTC()})
	var workspaceRevision orm.WorkflowSlotRevision
	r.db.Where("id = 'workspace-r1'").First(&workspaceRevision)
	workspace := productObject(workspaceRevision.ContentSnapshot)
	entry := workspace["artifacts"].([]any)[0].(map[string]any)
	entry["representations"] = map[string]any{
		"html":     map[string]any{"slot": "direction_document_html", "content_sha256": requestHash([]byte(html)), "present": true},
		"markdown": entry["host_artifact"],
	}
	content, _ := json.Marshal(workspace)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Update("content_snapshot", content)

	defaultView, err := r.ProductProjectArtifact(ctx, "owner", "source", "direction")
	if err != nil || defaultView["content"] != html || defaultView["content_format"] != "html" {
		t.Fatalf("default HTML view: %#v %v", defaultView, err)
	}
	markdown, err := r.ProductProjectArtifact(ctx, "owner", "source", "direction", "markdown")
	if err != nil || markdown["content"] != "Exact approved file bytes, not a generated summary" || markdown["content_format"] != "markdown" {
		t.Fatalf("markdown view: %#v %v", markdown, err)
	}
	summary, _ := r.ProductRelaySummary(ctx, "owner", "source")
	formats := summary["project"].(map[string]any)["artifacts"].([]map[string]any)[0]["available_formats"].([]string)
	if len(formats) != 2 || formats[0] != "html" || formats[1] != "markdown" {
		t.Fatalf("available formats: %#v", formats)
	}
}

func TestProductProjectMarkdownEditCreatesVersionAndSynchronizesHTML(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	markdown := "# 更新后的方向\n\n```mermaid\ntimeline\n  Q1 : 验证范围\n```\n\n![外部跟踪图](https://tracker.example/secret.png)"
	req := ProductMarkdownUpdateRequest{
		BaseRevisionID: "business-r7", BaseRevision: 7, Markdown: markdown, IdempotencyKey: "edit-direction-1",
	}
	first, err := r.UpdateProductProjectMarkdown(ctx, "owner", "source", "direction", req)
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	if err := json.Unmarshal(first, &result); err != nil {
		t.Fatal(err)
	}
	if result["revision"] != float64(8) || result["html_synced"] != true || result["html_sync_required"] != false {
		t.Fatalf("unexpected edit result: %#v", result)
	}
	updatedMarkdown, err := r.ProductProjectArtifact(ctx, "owner", "source", "direction", "markdown")
	if err != nil || updatedMarkdown["content"] != markdown || updatedMarkdown["revision"] != 8 || updatedMarkdown["editable"] != true {
		t.Fatalf("updated Markdown: %#v %v", updatedMarkdown, err)
	}
	updatedHTML, err := r.ProductProjectArtifact(ctx, "owner", "source", "direction", "html")
	htmlContent, _ := updatedHTML["content"].(string)
	if err != nil || !strings.Contains(htmlContent, "更新后的方向") || !strings.Contains(htmlContent, "时间轴") ||
		strings.Contains(htmlContent, "https://tracker.example") || strings.Contains(htmlContent, "%!") {
		t.Fatalf("updated HTML was not deterministic and safe: %v %#v", err, updatedHTML)
	}
	if updatedHTML["status"] != "draft" || updatedHTML["stale"] != true {
		t.Fatalf("edited artifact must be revalidated: %#v", updatedHTML)
	}
	replayed, err := r.UpdateProductProjectMarkdown(ctx, "owner", "source", "direction", req)
	if err != nil || string(replayed) != string(first) {
		t.Fatalf("idempotent replay: %s %v", replayed, err)
	}
	stale := req
	stale.IdempotencyKey = "edit-direction-stale"
	if _, err := r.UpdateProductProjectMarkdown(ctx, "owner", "source", "direction", stale); !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("stale base was accepted: %v", err)
	}
}

func TestProductProjectMarkdownEditPreservesInteractivePrototypeHTML(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	htmlPrototype := `<!doctype html><button onclick="this.textContent='完成'">交互原型</button>`
	now := time.Now().UTC()
	if err := r.db.Create(&orm.WorkflowSlotRevision{ID: "prototype-r1", SessionID: "source", SlotID: "prototype", Slot: "prototype", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(strconv.Quote(htmlPrototype)), CreatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	if err := r.db.Create(&orm.WorkflowSlotRevision{ID: "prototype-md-r1", SessionID: "source", SlotID: "prototype_markdown", Slot: "prototype_markdown", Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: json.RawMessage(strconv.Quote("# 原型说明")), CreatedAt: now}).Error; err != nil {
		t.Fatal(err)
	}
	var workspaceRevision orm.WorkflowSlotRevision
	r.db.Where("id = 'workspace-r1'").First(&workspaceRevision)
	workspace := productObject(workspaceRevision.ContentSnapshot)
	workspace["artifacts"] = append(workspace["artifacts"].([]any), map[string]any{
		"artifact_id": "prototype-v1", "title": "交互原型", "version": "1.0", "status": "accepted",
		"host_artifact": map[string]any{"slot": "prototype", "content_sha256": requestHash([]byte(htmlPrototype))},
		"representations": map[string]any{
			"html":     map[string]any{"slot": "prototype", "content_sha256": requestHash([]byte(htmlPrototype)), "present": true},
			"markdown": map[string]any{"slot": "prototype_markdown", "content_sha256": requestHash([]byte("# 原型说明")), "present": true},
		},
	})
	encoded, _ := json.Marshal(workspace)
	r.db.Model(&orm.WorkflowSlotRevision{}).Where("id = 'workspace-r1'").Update("content_snapshot", encoded)

	response, err := r.UpdateProductProjectMarkdown(ctx, "owner", "source", "prototype", ProductMarkdownUpdateRequest{
		BaseRevisionID: "prototype-md-r1", BaseRevision: 1, Markdown: "# 更新后的原型说明", IdempotencyKey: "edit-prototype-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	json.Unmarshal(response, &result)
	if result["html_synced"] != false || result["html_sync_required"] != true {
		t.Fatalf("prototype edit hid its sync requirement: %#v", result)
	}
	prototype, err := r.ProductProjectArtifact(ctx, "owner", "source", "prototype", "html")
	if err != nil || prototype["content"] != htmlPrototype || prototype["revision_id"] != "prototype-r1" {
		t.Fatalf("interactive HTML was overwritten: %#v %v", prototype, err)
	}
	summary, err := r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil {
		t.Fatal(err)
	}
	views := summary["project"].(map[string]any)["artifacts"].([]map[string]any)
	for _, view := range views {
		if view["stage"] == "prototype" && (view["stale"] != true || view["status"] != "draft") {
			t.Fatalf("prototype companion edit was not surfaced on the shared artifact: %#v", view)
		}
	}
}

func TestProductProjectOwnerAndConversationIsolation(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	nextID := productRelayTo(t, r, "source", "design", "private-project", 9)
	if _, err := r.ProductProjectArtifact(ctx, "another-owner", nextID, "direction"); !errors.Is(err, ErrPermissionDenied) {
		t.Fatalf("wrong owner: %v", err)
	}
	createTestConversation(t, r, "different-conversation", "owner")
	r.db.Model(&orm.WorkflowSession{}).Where("id = 'source'").Update("conversation_id", "different-conversation")
	preview, err := r.ProductProjectArtifact(ctx, "owner", nextID, "direction")
	if err != nil || preview["source_session_id"] != "" || preview["revision_id"] != "" {
		t.Fatalf("cross-conversation lineage leaked: %#v %v", preview, err)
	}
	if _, err := r.ProductProjectArtifact(ctx, "owner", nextID, "unknown"); err == nil {
		t.Fatal("accepted unsupported stage")
	}
}

func TestProductRelayReusesStagePreferencesAndDefaultsNewStage(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	for material, value := range map[string]string{"word_target": "2400", "execution_depth": "light", "reference_sample_choice": "provided", "reference_sample": "My direction template"} {
		resource, _, err := r.ImportInputResource(ctx, "owner", material+".txt", "text/plain", "sha256:"+requestHash([]byte(value)), []byte(value))
		if err != nil {
			t.Fatal(err)
		}
		r.db.Create(&InputBinding{ID: "pref-" + material, WorkflowSessionID: "source", MaterialID: material, ResourceType: "input_resource", ResourceID: resource.ID, ResourceRevision: resource.Revision, ContentHash: resource.ContentHash, Validity: "effective"})
	}
	nextID := productRelayTo(t, r, "source", "direction", "same-stage-prefs", 9)
	contents := productBoundContents(t, r, nextID)
	if contents["word_target"] != "2400" || contents["execution_depth"] != "light" || contents["reference_sample"] != "My direction template" || contents["reference_sample_choice"] != "provided" {
		t.Fatalf("same-stage preferences lost: %#v", contents)
	}
	approval := productObject(json.RawMessage(contents["stage_approval"]))
	if approval["request_context"] != "保留既有内容，只完善这个阶段" {
		t.Fatal("explicit stage request was not bound for the child")
	}

	// A prototype's not-applicable setting must never contaminate a later PRD.
	for stage, expected := range map[string]string{"prototype": "not-applicable", "prd": "6000"} {
		t.Run(stage, func(t *testing.T) {
			r := productProjectFixture(t)
			next := productRelayTo(t, r, "source", stage, "new-stage-default", 9)
			inputs := productBoundContents(t, r, next)
			if inputs["execution_depth"] != "auto" || inputs["word_target"] != expected {
				t.Fatalf("new stage requires redundant startup input: %#v", inputs)
			}
			wantSample := "none-confirmed"
			if stage == "prototype" {
				wantSample = "not-required"
			}
			if inputs["reference_sample_choice"] != wantSample || inputs["reference_sample"] != "" {
				t.Fatalf("unsafe sample inheritance: %#v", inputs)
			}
		})
	}
}

func productFinishFixtureStage(t *testing.T, r *Repository, session, stage, version, content string) {
	t.Helper()
	inputs := productBoundContents(t, r, session)
	workspace := productObject(json.RawMessage(inputs["workspace_seed"]))
	slot := ""
	for _, item := range productStages {
		if item.ID == stage {
			slot = item.Slot
		}
	}
	manifest := map[string]any{"artifact_id": session + "-manifest", "title": stage + " view", "version": version, "status": "reviewable", "eligible_next_stages": []string{"design", "prd", "prototype"}, "host_artifact": map[string]any{"slot": slot, "source_session_id": session, "content_sha256": requestHash([]byte(content))}}
	entries, _ := workspace["artifacts"].([]any)
	for _, item := range entries {
		entry, _ := item.(map[string]any)
		host, _ := entry["host_artifact"].(map[string]any)
		if host["slot"] == slot {
			entry["status"] = "superseded"
		}
	}
	workspace["artifacts"] = append(entries, manifest)
	workspace["current_run"] = map[string]any{"selected_stage": stage, "run_status": "awaiting-stage-confirmation"}
	for key, value := range map[string]any{"workspace_state": workspace, "stage_manifest": manifest, slot: content} {
		encoded, _ := json.Marshal(value)
		if err := r.db.Create(&orm.WorkflowSlotRevision{ID: session + ":" + key, SessionID: session, SlotID: key, Slot: key, Revision: 1, Selected: true, Validity: "effective", ContentSnapshot: encoded, CreatedAt: time.Now().UTC()}).Error; err != nil {
			t.Fatal(err)
		}
	}
	r.db.Model(&orm.WorkflowSession{}).Where("id = ?", session).Updates(map[string]any{"status": "completed", "state_version": 9})
}

func TestProductProjectDesignPRDPrototypeAreSharedViewsAcrossReentry(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	design := productRelayTo(t, r, "source", "design", "chain-design", 9)
	productFinishFixtureStage(t, r, design, "design", "1.0", "Shared design v1")
	prd := productRelayTo(t, r, design, "prd", "chain-prd", 9)
	productFinishFixtureStage(t, r, prd, "prd", "1.0", "Shared PRD v1")
	prototype := productRelayTo(t, r, prd, "prototype", "chain-prototype", 9)
	productFinishFixtureStage(t, r, prototype, "prototype", "1.0", "<!doctype html><html><body>Shared prototype</body></html>")
	returnDesign := productRelayTo(t, r, prototype, "design", "chain-return-design", 9)
	inputs := productBoundContents(t, r, returnDesign)
	if inputs["upstream_design"] != "Shared design v1" || inputs["upstream_prd"] != "Shared PRD v1" || !strings.Contains(inputs["upstream_prototype"], "Shared prototype") {
		t.Fatal("reentry did not automatically bind all project views")
	}
	summary, err := r.ProductRelaySummary(ctx, "owner", returnDesign)
	if err != nil {
		t.Fatal(err)
	}
	project := summary["project"].(map[string]any)
	if project["workspace_id"] != "stable-project" || len(project["artifacts"].([]map[string]any)) != 4 {
		t.Fatalf("shared stage view collection changed identity: %#v", project)
	}
	for stage, want := range map[string]string{"design": "Shared design v1", "prd": "Shared PRD v1", "prototype": "<!doctype html><html><body>Shared prototype</body></html>"} {
		preview, err := r.ProductProjectArtifact(ctx, "owner", returnDesign, stage)
		if err != nil || preview["content"] != want {
			t.Fatalf("lost %s preview: %#v %v", stage, preview, err)
		}
		if stage == "prototype" && preview["content_format"] != "html" {
			t.Fatal("prototype was not returned as a sandboxable HTML view")
		}
	}
	productFinishFixtureStage(t, r, returnDesign, "design", "1.1", "Shared design v2")
	returnPRD := productRelayTo(t, r, returnDesign, "prd", "chain-return-prd", 9)
	latest, err := r.ProductProjectArtifact(ctx, "owner", returnPRD, "design")
	if err != nil || latest["content"] != "Shared design v2" || latest["version"] != "1.1" || latest["source_session_id"] != returnDesign {
		t.Fatalf("latest repeated stage was not canonical: %#v %v", latest, err)
	}
	if productBoundContents(t, r, returnPRD)["upstream_design"] != "Shared design v2" {
		t.Fatal("next stage received stale repeated-stage content")
	}
	var conversations int64
	r.db.Model(&orm.Conversation{}).Count(&conversations)
	if conversations != 1 {
		t.Fatal("shared product process opened a new conversation")
	}
}

func TestProductProjectQuestionsAndDecisionsOnlyExposeCurrentVersions(t *testing.T) {
	r := productProjectFixture(t)
	ctx := context.Background()
	var revision orm.WorkflowSlotRevision
	r.db.First(&revision, "id = 'workspace-r1'")
	workspace := productObject(revision.ContentSnapshot)
	entries := workspace["artifacts"].([]any)
	previous := entries[0].(map[string]any)
	// Legacy draft versions were not always marked superseded. Numeric version
	// selection must still keep their resolved questions out of the current UI.
	newer := map[string]any{}
	for key, value := range previous {
		newer[key] = value
	}
	newer["version"] = "1.10"
	newer["open_questions"] = []any{map[string]any{"question_id": "Q2", "question": "Current question"}}
	workspace["artifacts"] = append(entries, newer)
	workspace["decisions"] = []any{map[string]any{"decision_id": "D1", "statement": "old accepted", "status": "accepted"}, map[string]any{"decision_id": "D1", "statement": "new pending", "status": "reopened"}}
	encoded, _ := json.Marshal(workspace)
	r.db.Model(&revision).Update("content_snapshot", encoded)
	summary, err := r.ProductRelaySummary(ctx, "owner", "source")
	if err != nil {
		t.Fatal(err)
	}
	project := summary["project"].(map[string]any)
	questions := project["open_questions"].([]map[string]any)
	decisions := project["decisions"].([]map[string]any)
	if len(questions) != 1 || questions[0]["question"] != "Current question" || len(decisions) != 1 || decisions[0]["statement"] != "new pending" {
		t.Fatalf("historical state leaked into current view: %#v", project)
	}
}
