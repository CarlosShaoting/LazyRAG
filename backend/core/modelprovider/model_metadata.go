package modelprovider

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"lazymind/core/common"
)

const (
	modelMetadataTimeout      = 5 * time.Second
	modelMetadataMaxBodyBytes = 4 << 20
)

var modelContextWindowFields = []string{
	"max_input_tokens",
	"max_model_len",
	"context_length",
	"max_context_length",
}

// discoverModelMaxInputTokens reads context-window metadata exposed by an
// OpenAI-compatible GET /models endpoint. vLLM publishes max_model_len here.
// Discovery is best effort: callers keep supporting providers that only expose
// model ids and rely on the process-level fallback when metadata is absent.
func discoverModelMaxInputTokens(
	ctx context.Context,
	providerName, baseURL, apiKey, modelName string,
) (*string, error) {
	endpoint := modelMetadataEndpoint(providerName, baseURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if apiKey = strings.TrimSpace(apiKey); apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := (&http.Client{Timeout: modelMetadataTimeout}).Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("model metadata endpoint returned HTTP %d", resp.StatusCode)
	}

	decoder := json.NewDecoder(io.LimitReader(resp.Body, modelMetadataMaxBodyBytes))
	decoder.UseNumber()
	var payload struct {
		Data []map[string]any `json:"data"`
	}
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode model metadata: %w", err)
	}

	wanted := strings.TrimSpace(modelName)
	for _, item := range payload.Data {
		id, _ := item["id"].(string)
		if strings.TrimSpace(id) != wanted {
			continue
		}
		for _, field := range modelContextWindowFields {
			if value := normalizeDiscoveredContextWindow(item[field]); value != nil {
				return value, nil
			}
		}
		return nil, nil
	}
	return nil, nil
}

func modelMetadataEndpoint(providerName, baseURL string) string {
	base := strings.TrimSpace(LazyLLMBaseURL(providerName, baseURL))
	if strings.HasSuffix(strings.TrimRight(base, "/"), "/models") {
		return base
	}
	return common.JoinURL(base, "models")
}

func normalizeDiscoveredContextWindow(value any) *string {
	var normalized string
	switch typed := value.(type) {
	case json.Number:
		parsed, err := typed.Int64()
		if err != nil || parsed <= 0 {
			return nil
		}
		normalized = typed.String()
	case string:
		normalized = strings.ToUpper(strings.TrimSpace(typed))
	default:
		return nil
	}
	if len(normalized) > 16 || !maxInputTokensPattern.MatchString(normalized) {
		return nil
	}
	return &normalized
}
