import { describe, expect, it } from "vitest";
import type { ListModelProviderGroupModelsOpenAPIItem } from "@/api/generated/core-client";
import {
  getRecommendedCapabilities,
  recommendWelcomeModels,
  type AvailableWelcomeModels,
} from "./modelRecommendation";

function model(
  id: string,
  name: string,
  overrides: Partial<ListModelProviderGroupModelsOpenAPIItem> = {},
): ListModelProviderGroupModelsOpenAPIItem {
  return {
    id,
    name,
    model_type: "llm",
    provider_name: "Provider",
    group_name: "Default",
    base_url: "https://example.com",
    user_model_provider_id: "provider",
    user_model_provider_group_id: "group",
    is_default: true,
    is_editable: false,
    ...overrides,
  };
}

function available(): AvailableWelcomeModels {
  return {
    llm: [
      model("fast", "model-flash", { max_input_tokens: "32K" }),
      model("quality", "model-pro", { max_input_tokens: "1M" }),
    ],
    embed_main: [model("embed", "text-embedding", { model_type: "embed" })],
    text2image: [model("image", "image-pro", { model_type: "text2image" })],
  };
}

describe("welcome model recommendations", () => {
  it("keeps unrelated model types out of the lightweight recommendation", () => {
    expect(getRecommendedCapabilities("general_office", ["daily_qa_writing"]))
      .toEqual(["llm"]);
    expect(getRecommendedCapabilities("design_creative", ["knowledge_enterprise_qa"]))
      .toEqual(["llm", "embed_main", "text2image"]);
  });

  it("balances speed and cost for everyday work and quality for deep work", () => {
    expect(recommendWelcomeModels(available(), "general_office", ["daily_qa_writing"])[0].model.id)
      .toBe("fast");
    expect(recommendWelcomeModels(available(), "student_researcher", ["deep_analysis_research"])[0].model.id)
      .toBe("quality");
    expect(recommendWelcomeModels(available(), "student_researcher", [])[0].model.id)
      .toBe("quality");
  });

  it("preserves an already selected model while an interrupted onboarding is retried", () => {
    expect(recommendWelcomeModels(
      available(),
      "general_office",
      ["daily_qa_writing"],
      { llm: "quality" },
    )[0].model.id).toBe("quality");
  });
});
