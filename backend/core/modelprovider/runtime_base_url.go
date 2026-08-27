package modelprovider

import (
	"net/url"
	"strings"
)

// LazyLLMBaseURL normalizes self-hosted OpenAI-compatible endpoints to the
// API root expected by LazyLLM. Other providers keep their own URL contract.
func LazyLLMBaseURL(providerName, baseURL string) string {
	baseURL = strings.TrimSpace(baseURL)
	if normalizeProviderName(providerName) != "openai" {
		return baseURL
	}

	parsed, err := url.Parse(baseURL)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return baseURL
	}

	segments := strings.Split(strings.Trim(parsed.Path, "/"), "/")
	v1Index := -1
	for index, segment := range segments {
		if strings.EqualFold(segment, "v1") {
			v1Index = index
			break
		}
	}
	if v1Index >= 0 {
		parsed.Path = "/" + strings.Join(segments[:v1Index+1], "/") + "/"
	} else {
		parsed.Path = "/v1/"
	}
	parsed.RawPath = ""
	parsed.RawQuery = ""
	parsed.ForceQuery = false
	parsed.Fragment = ""
	return parsed.String()
}
