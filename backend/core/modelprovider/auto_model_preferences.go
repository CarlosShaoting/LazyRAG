package modelprovider

import (
	"strings"

	"lazymind/core/common/orm"
)

var autoModelSlots = []struct {
	ModelKey     string
	CatalogTypes []string
}{
	{ModelKey: "llm", CatalogTypes: []string{"llm"}},
	{ModelKey: "vlm", CatalogTypes: []string{"vlm"}},
	{ModelKey: "embed_main", CatalogTypes: []string{"embed"}},
	// The UI presents text generation and editable image models in one image-generator
	// slot. An image_editing selection is mirrored to image_generator by the runtime.
	{ModelKey: "image_generator", CatalogTypes: []string{"text2image", "image_editing"}},
}

// preferredFreeAutoModelNames is intentionally conservative: entries are models that the
// provider's official pricing or model documentation currently identifies as zero-cost.
// Providers that only grant expiring trial credits are not listed here. If a preferred model
// is absent from the locally seeded catalog, auto-selection retains the catalog-order fallback.
//
// Revalidate when updating the catalog:
//   - https://docs.bigmodel.cn/cn/guide/start/model-overview
//   - https://siliconflow.cn/pricing
var preferredFreeAutoModelNames = map[string]map[string][]string{
	"glm": {
		"llm":             {"GLM-4.7-Flash", "GLM-4.5-Flash", "GLM-4-Flash-250414"},
		"vlm":             {"GLM-4.6V-Flash", "GLM-4.1V-Thinking-Flash", "GLM-4V-Flash"},
		"image_generator": {"CogView-3-Flash"},
	},
	"siliconflow": {
		"llm": {
			"THUDM/GLM-Z1-9B-0414",
			"Qwen/Qwen3-8B",
			"deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
			"Qwen/Qwen2.5-7B-Instruct",
		},
		"vlm":             {"Qwen/Qwen3.5-4B", "THUDM/GLM-4.1V-9B-Thinking"},
		"embed_main":      {"BAAI/bge-m3", "BAAI/bge-large-zh-v1.5"},
		"image_generator": {"Kwai-Kolors/Kolors"},
	},
}

// The Token Plan endpoint has a separate catalog surface and is free during its public beta.
// Keep these preferences endpoint-scoped so the classic SenseNova endpoint does not select a
// Token Plan-only model.
var sensenovaTokenPlanAutoModelNames = map[string][]string{
	"llm":             {"sensenova-6.8-flash-lite", "sensenova-6.7-flash-lite"},
	"image_generator": {"sensenova-u1-fast", "sensenova-u1.5-lite"},
}

func preferredAutoModel(
	providerName, baseURL, slotKey string,
	catalogTypes []string,
	models []orm.UserModelProviderGroupModel,
) (orm.UserModelProviderGroupModel, bool) {
	typeSet := make(map[string]struct{}, len(catalogTypes))
	for _, modelType := range catalogTypes {
		typeSet[strings.ToLower(strings.TrimSpace(modelType))] = struct{}{}
	}
	candidates := make([]orm.UserModelProviderGroupModel, 0, len(models))
	for _, model := range models {
		if _, ok := typeSet[strings.ToLower(strings.TrimSpace(model.ModelType))]; ok {
			candidates = append(candidates, model)
		}
	}
	if len(candidates) == 0 {
		return orm.UserModelProviderGroupModel{}, false
	}

	preferences := preferredFreeAutoModelNames[strings.ToLower(strings.TrimSpace(providerName))][slotKey]
	if strings.EqualFold(strings.TrimSpace(providerName), "SenseNova") &&
		normalizeBaseURLForCompare(baseURL) == normalizeBaseURLForCompare(sensenovaNewPlatformBaseURL) {
		preferences = sensenovaTokenPlanAutoModelNames[slotKey]
	}
	for _, preferredName := range preferences {
		for _, candidate := range candidates {
			if strings.EqualFold(strings.TrimSpace(candidate.Name), preferredName) {
				return candidate, true
			}
		}
	}
	return candidates[0], true
}
