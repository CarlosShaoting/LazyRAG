package workflow

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/mux"
	"lazymind/core/common/orm"
)

func seedAuthoringSkill(t *testing.T, db *orm.DB) {
	t.Helper()
	for _, statement := range []string{
		`CREATE TABLE IF NOT EXISTS skills(id text primary key, owner_user_id text, skill_name text, head_revision_id text, deleted_at datetime)`,
		`CREATE TABLE IF NOT EXISTS skill_revisions(id text primary key, skill_id text, revision_no integer, tree_hash text)`,
		`CREATE TABLE IF NOT EXISTS skill_revision_entries(revision_id text, path text, entry_type text, blob_hash text, size integer, mime text, file_type text, binary boolean)`,
		`CREATE TABLE IF NOT EXISTS skill_blobs(hash text primary key, content blob)`,
		`INSERT INTO skills VALUES('skill-1','user-1','Pinned Skill','revision-1',NULL)`,
		`INSERT INTO skill_revisions VALUES('revision-1','skill-1',1,'tree-fixed')`,
		`INSERT INTO skill_blobs VALUES('blob-1','# Pinned Skill')`,
		`INSERT INTO skill_revision_entries VALUES('revision-1','SKILL.md','file','blob-1',14,'text/markdown','markdown',0)`,
	} {
		if err := db.Exec(statement).Error; err != nil {
			t.Fatal(err)
		}
	}
}

func TestAuthoringFixtureAndLazyMindDraftShareDeterministicDiagnostics(t *testing.T) {
	db := newHandlerTestDB(t)
	seedAuthoringSkill(t, db)
	fixtureReq := httptest.NewRequest(http.MethodGet, "/workflow-authoring/v1/fixture?tree_hash=tree-fixed", nil)
	fixtureRec := httptest.NewRecorder()
	GenerateAuthoringFixture(fixtureRec, fixtureReq)
	var fixtureEnvelope struct {
		Data struct {
			Files map[string]string `json:"files"`
		} `json:"data"`
	}
	if err := json.Unmarshal(fixtureRec.Body.Bytes(), &fixtureEnvelope); err != nil {
		t.Fatal(err)
	}
	filesJSON, _ := json.Marshal(fixtureEnvelope.Data.Files)
	createBody := `{"name":"Fixture","skill_id":"skill-1","revision_id":"revision-1","tree_hash":"tree-fixed","files":` + string(filesJSON) + `}`
	createReq := httptest.NewRequest(http.MethodPost, "/workflow-authoring/v1/drafts", strings.NewReader(createBody))
	createReq.Header.Set("X-User-Id", "user-1")
	createRec := httptest.NewRecorder()
	CreateAuthoringWorkflowDraft(createRec, createReq)
	if createRec.Code != http.StatusOK {
		t.Fatalf("create=%d %s", createRec.Code, createRec.Body.String())
	}
	var draft orm.WorkflowDraft
	if err := db.Where("created_by=?", "user-1").First(&draft).Error; err != nil {
		t.Fatal(err)
	}
	first := authoringDiagnosticsForDraft(db.DB, draft)
	second := authoringDiagnosticsForDraft(db.DB, draft)
	a, _ := json.Marshal(first)
	b, _ := json.Marshal(second)
	if string(a) != string(b) || !first.Valid {
		t.Fatalf("diagnostics not deterministic/valid: %s vs %s", a, b)
	}
	if draft.SourceSkillRevisionID != "revision-1" || draft.SourceSkillTreeHash != "tree-fixed" {
		t.Fatalf("snapshot not fixed: %#v", draft)
	}
}

func TestAuthoringFileUpdateUsesOptimisticVersion(t *testing.T) {
	db := newHandlerTestDB(t)
	now := time.Now().UTC()
	draft := orm.WorkflowDraft{ID: "draft-1", Name: "Draft", CreatedBy: "user-1", Version: 1, ScriptsContent: "{}", CreatedAt: now, UpdatedAt: now}
	if err := db.Create(&draft).Error; err != nil {
		t.Fatal(err)
	}
	call := func(version int) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodPut, "/workflow-authoring/v1/drafts/draft-1/files", strings.NewReader(`{"path":"plugin.yaml","content":"id: fixed","expected_version":`+strconv.Itoa(version)+`}`))
		req.Header.Set("X-User-Id", "user-1")
		req = mux.SetURLVars(req, map[string]string{"draft_id": "draft-1"})
		rec := httptest.NewRecorder()
		UpdateAuthoringWorkflowDraftFile(rec, req)
		return rec
	}
	if got := call(1); got.Code != http.StatusOK {
		t.Fatalf("update=%d %s", got.Code, got.Body.String())
	}
	if got := call(1); got.Code != http.StatusConflict {
		t.Fatalf("stale update=%d %s", got.Code, got.Body.String())
	}
}

func TestAuthoringSourceContainsNoModelInvocation(t *testing.T) {
	data, err := os.ReadFile("authoring_handlers.go")
	if err != nil {
		t.Fatal(err)
	}
	text := string(data)
	for _, forbidden := range []string{"core/algo", "modelconfig", "http://chat", "GenerateWorkflowStaged"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("implicit model dependency %q", forbidden)
		}
	}
}
