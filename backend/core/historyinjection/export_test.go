package historyinjection

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestDiscoverConversationWorkspacesSupportsNonPPTBuckets(t *testing.T) {
	uploadRoot := t.TempDir()
	conversationID := "conversation-image-1"
	workspace := filepath.Join(uploadRoot, "workflow-workspaces", "image-workflow", "owner-1",
		"animated_meme_sessions", conversationID)
	if err := os.MkdirAll(workspace, 0o755); err != nil {
		t.Fatal(err)
	}
	paths, err := discoverConversationWorkspaces(ExportOptions{
		WorkflowRef: "builtin:image-workflow",
		UploadRoot:  uploadRoot,
	}, "owner-1", conversationID)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"/var/lib/lazymind/uploads/workflow-workspaces/image-workflow/owner-1/animated_meme_sessions/conversation-image-1"}
	if !reflect.DeepEqual(paths, want) {
		t.Fatalf("workspace paths = %#v, want %#v", paths, want)
	}
}

func TestDiscoverConversationWorkspacesAllowsMissingWorkflowRoot(t *testing.T) {
	paths, err := discoverConversationWorkspaces(ExportOptions{
		WorkflowRef: "builtin:image-workflow",
		UploadRoot:  t.TempDir(),
	}, "owner-1", "conversation-image-1")
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 0 {
		t.Fatalf("workspace paths = %#v, want none", paths)
	}
}
