package workflow

import "testing"

func TestWorkflowChatModelOverrideKeepsOnlyNonSecretIdentity(t *testing.T) {
	got := workflowChatModelOverride(map[string]any{
		"llm": map[string]any{
			"source": "siliconflow", "model": "deepseek-ai/DeepSeek-V3",
			"base_url": "https://private.example/v1", "api_key": "SECRET",
		},
	})
	if got["source"] != "siliconflow" || got["model"] != "deepseek-ai/DeepSeek-V3" {
		t.Fatalf("override = %#v", got)
	}
	if len(got) != 2 {
		t.Fatalf("override contains unexpected fields: %#v", got)
	}
}

func TestWorkflowChatModelOverrideRejectsControlCharacters(t *testing.T) {
	got := workflowChatModelOverride(map[string]any{
		"llm": map[string]any{"source": "siliconflow", "model": "bad\nmodel"},
	})
	if got != nil {
		t.Fatalf("override = %#v, want nil", got)
	}
}
