package modelprovider

// LazyLLMSource converts a catalog/display provider name into the source key
// registered by LazyLLM. Provider names stored by Core remain user-facing;
// only the value crossing the Core -> algorithm boundary is normalized.
func LazyLLMSource(providerName string) string {
	normalized := normalizeProviderName(providerName)
	aliases := map[string]string{
		"anthropic":     "claude",
		"bigmodel":      "glm",
		"moonshot":      "kimi",
		"tongyiqianwen": "qwen",
		"volcanoark":    "doubao",
		"volcengine":    "doubao",
		"zhipu":         "glm",
		"zhipuai":       "glm",
	}
	if source := aliases[normalized]; source != "" {
		return source
	}
	return normalized
}
