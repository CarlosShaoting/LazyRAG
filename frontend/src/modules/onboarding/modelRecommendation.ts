import type { ListModelProviderGroupModelsOpenAPIItem } from "@/api/generated/core-client";

export const WELCOME_IDENTITIES = [
  "product_operations",
  "engineering_technology",
  "design_creative",
  "marketing_content",
  "sales_customer_service",
  "management_function",
  "student_researcher",
  "general_office",
  "other",
  "prefer_not_to_say",
] as const;

export const WELCOME_TASKS = [
  "daily_qa_writing",
  "summary_translation",
  "deep_analysis_research",
  "documents_presentations_spreadsheets",
  "data_analysis_processing",
  "image_generation_design",
  "knowledge_enterprise_qa",
  "other",
] as const;

export type WelcomeIdentity = (typeof WELCOME_IDENTITIES)[number];
export type WelcomeTask = (typeof WELCOME_TASKS)[number];
export type RecommendedModelCapability = "llm" | "embed_main" | "text2image";
export type RecommendationReason = "balanced" | "quality" | "knowledge" | "image";

export interface RecommendedModel {
  capability: RecommendedModelCapability;
  model: ListModelProviderGroupModelsOpenAPIItem;
  reason: RecommendationReason;
}

export type AvailableWelcomeModels = Record<
  RecommendedModelCapability,
  ListModelProviderGroupModelsOpenAPIItem[]
>;

const QUALITY_MODEL_MARKERS = [
  "gpt-5",
  "opus",
  "sonnet",
  "reasoner",
  "deepseek-r1",
  "qwen3-max",
  "qwen3.5",
  "glm-5",
  "pro",
  "max",
];

const FAST_VALUE_MODEL_MARKERS = [
  "flash",
  "mini",
  "lite",
  "small",
  "haiku",
  "turbo",
  "free",
];

const ENGINEERING_MODEL_MARKERS = ["coder", "code", "devstral", "deepseek-v3"];

const QUALITY_FIRST_TASKS = new Set<WelcomeTask>([
  "deep_analysis_research",
  "documents_presentations_spreadsheets",
  "data_analysis_processing",
  "knowledge_enterprise_qa",
]);
const QUALITY_FIRST_IDENTITIES = new Set<WelcomeIdentity>([
  "engineering_technology",
  "design_creative",
  "marketing_content",
  "student_researcher",
]);

// Keep this metadata-only v1 heuristic isolated so effect, reliability,
// latency, and price scores can replace the proxies when that data is exposed.

function prefersQuality(identity: WelcomeIdentity | "", tasks: WelcomeTask[]) {
  return (identity !== "" && QUALITY_FIRST_IDENTITIES.has(identity)) ||
    tasks.some((task) => QUALITY_FIRST_TASKS.has(task));
}

function includesMarker(value: string, markers: string[]) {
  const normalized = value.toLowerCase();
  return markers.some((marker) => normalized.includes(marker));
}

function parseContextSize(value?: string | null) {
  const normalized = String(value || "").trim().toUpperCase();
  const match = normalized.match(/^(\d+(?:\.\d+)?)([KM])?$/);
  if (!match) return 0;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return 0;
  if (match[2] === "M") return amount * 1_000_000;
  if (match[2] === "K") return amount * 1_000;
  return amount;
}

function scoreModel(
  model: ListModelProviderGroupModelsOpenAPIItem,
  capability: RecommendedModelCapability,
  identity: WelcomeIdentity | "",
  tasks: WelcomeTask[],
  currentModelID?: string,
) {
  if (currentModelID && model.id === currentModelID) return 10_000;

  const searchable = model.name;
  let score = model.is_default ? 40 : 0;

  if (capability === "llm") {
    const qualityFirst = prefersQuality(identity, tasks);
    if (includesMarker(searchable, QUALITY_MODEL_MARKERS)) {
      score += qualityFirst ? 24 : 9;
    }
    if (includesMarker(searchable, FAST_VALUE_MODEL_MARKERS)) {
      score += qualityFirst ? 5 : 20;
    }
    if (
      identity === "engineering_technology" &&
      includesMarker(searchable, ENGINEERING_MODEL_MARKERS)
    ) {
      score += 16;
    }
    const contextSize = parseContextSize(model.max_input_tokens);
    if (contextSize > 0) {
      score += Math.min(14, Math.log2(Math.max(1, contextSize / 8_000)) * 3);
    }
  }

  return score;
}

function pickModel(
  models: ListModelProviderGroupModelsOpenAPIItem[],
  capability: RecommendedModelCapability,
  identity: WelcomeIdentity | "",
  tasks: WelcomeTask[],
  currentModelID?: string,
) {
  return [...models].sort((left, right) => {
    const scoreDifference =
      scoreModel(right, capability, identity, tasks, currentModelID) -
      scoreModel(left, capability, identity, tasks, currentModelID);
    if (scoreDifference !== 0) return scoreDifference;
    return `${left.provider_name}\u0000${left.name}\u0000${left.id}`.localeCompare(
      `${right.provider_name}\u0000${right.name}\u0000${right.id}`,
    );
  })[0];
}

export function getRecommendedCapabilities(
  identity: WelcomeIdentity | "",
  tasks: WelcomeTask[],
): RecommendedModelCapability[] {
  const capabilities: RecommendedModelCapability[] = ["llm"];
  if (tasks.includes("knowledge_enterprise_qa")) {
    capabilities.push("embed_main");
  }
  if (identity === "design_creative" || tasks.includes("image_generation_design")) {
    capabilities.push("text2image");
  }
  return capabilities;
}

export function recommendWelcomeModels(
  available: AvailableWelcomeModels,
  identity: WelcomeIdentity | "",
  tasks: WelcomeTask[],
  currentModelIDs: Partial<Record<RecommendedModelCapability, string>> = {},
): RecommendedModel[] {
  const qualityFirst = prefersQuality(identity, tasks);
  return getRecommendedCapabilities(identity, tasks).flatMap((capability) => {
    const model = pickModel(
      available[capability],
      capability,
      identity,
      tasks,
      currentModelIDs[capability],
    );
    if (!model) return [];
    const reason: RecommendationReason = capability === "embed_main"
      ? "knowledge"
      : capability === "text2image"
        ? "image"
        : qualityFirst
          ? "quality"
          : "balanced";
    return [{ capability, model, reason }];
  });
}
