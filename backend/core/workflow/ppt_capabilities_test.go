package plugin

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"lazymind/core/common"
)

func TestPptExportCapabilitiesComesFromChat(t *testing.T) {
	chat := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/plugin/ppt/capabilities" {
			http.Error(w, "unexpected upstream path", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"editable_pptx":true,"mode":"editable","dependency_missing":false}`))
	}))
	defer chat.Close()

	t.Setenv("LAZYMIND_RUNTIME_MODE", "container")
	t.Setenv("LAZYMIND_CHAT_SERVICE_URL", chat.URL)
	// A conflicting value in core must not override chat's capability result.
	t.Setenv("LAZYMIND_OUTPUT_EDITABLE_PPT", "false")

	recorder := httptest.NewRecorder()
	PptExportCapabilities(recorder, httptest.NewRequest(http.MethodGet, "/plugins/ppt:capabilities", nil))

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
	var response common.APIResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	data, ok := response.Data.(map[string]any)
	if !ok {
		t.Fatalf("unexpected data: %#v", response.Data)
	}
	if enabled, _ := data["editable_pptx"].(bool); !enabled {
		t.Fatalf("editable_pptx = %#v, want true", data["editable_pptx"])
	}
	if mode, _ := data["mode"].(string); mode != "editable" {
		t.Fatalf("mode = %#v, want editable", data["mode"])
	}
}

func TestPptExportCapabilitiesReportsMissingLocalDependency(t *testing.T) {
	t.Setenv("LAZYMIND_RUNTIME_MODE", "local")
	t.Setenv("LAZYMIND_RUNTIME_ROOT", t.TempDir())

	recorder := httptest.NewRecorder()
	PptExportCapabilities(recorder, httptest.NewRequest(http.MethodGet, "/plugins/ppt:capabilities", nil))

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
	var response common.APIResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	data, ok := response.Data.(map[string]any)
	if !ok {
		t.Fatalf("unexpected data: %#v", response.Data)
	}
	if enabled, _ := data["editable_pptx"].(bool); enabled {
		t.Fatalf("editable_pptx = true, want false")
	}
	if missing, _ := data["dependency_missing"].(bool); !missing {
		t.Fatalf("dependency_missing = %#v, want true", data["dependency_missing"])
	}
}
