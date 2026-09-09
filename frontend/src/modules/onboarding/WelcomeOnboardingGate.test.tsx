import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ListModelProviderGroupModelsOpenAPIItem } from "@/api/generated/core-client";
import WelcomeOnboardingGate from "./WelcomeOnboardingGate";

const mocks = vi.hoisted(() => ({
  fetchPreferences: vi.fn(),
  patchPreferences: vi.fn(),
  getSelectedModels: vi.fn(),
  getModels: vi.fn(),
  putSelectedModels: vi.fn(),
}));

const labels: Record<string, string> = {
  "welcomeOnboarding.eyebrow": "欢迎使用 LazyMind",
  "welcomeOnboarding.title": "让 LazyMind 更懂你的工作方式",
  "welcomeOnboarding.subtitle": "介绍",
  "welcomeOnboarding.skip": "跳过，直接开始",
  "welcomeOnboarding.identityTitle": "你的身份",
  "welcomeOnboarding.identityHint": "单选",
  "welcomeOnboarding.identities.engineering_technology": "研发或技术",
  "welcomeOnboarding.identities.design_creative": "设计或创意",
  "welcomeOnboarding.tasksTitle": "你常用 LazyMind 做什么？",
  "welcomeOnboarding.tasksHint": "多选",
  "welcomeOnboarding.tasks.knowledge_enterprise_qa": "知识库或企业资料问答",
  "welcomeOnboarding.tasks.image_generation_design": "图片生成和创意设计",
  "welcomeOnboarding.recommendation.title": "为你推荐的模型配置",
  "welcomeOnboarding.recommendation.hint": "推荐说明",
  "welcomeOnboarding.recommendation.recommended": "推荐",
  "welcomeOnboarding.recommendation.capabilities.llm": "对话模型",
  "welcomeOnboarding.recommendation.capabilities.embed_main": "知识库 Embedding",
  "welcomeOnboarding.recommendation.capabilities.text2image": "图片生成模型",
  "welcomeOnboarding.recommendation.reasons.balanced": "均衡推荐",
  "welcomeOnboarding.recommendation.reasons.quality": "效果优先",
  "welcomeOnboarding.recommendation.reasons.knowledge": "知识库推荐",
  "welcomeOnboarding.recommendation.reasons.image": "图片推荐",
  "welcomeOnboarding.recommendation.missingTitle": "缺少模型",
  "welcomeOnboarding.recommendation.missingDescription": "缺少能力",
  "welcomeOnboarding.recommendation.separator": "、",
  "welcomeOnboarding.moreModels": "展示更多模型",
  "welcomeOnboarding.moreModelsHint": "进入设置",
  "welcomeOnboarding.start": "使用推荐配置并开始",
  "welcomeOnboarding.messages.saved": "保存成功",
  "welcomeOnboarding.messages.saveFailed": "保存失败",
  "welcomeOnboarding.messages.skipNotSaved": "跳过状态未保存",
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => labels[key] || key.split(".").at(-1) || key,
  }),
}));

vi.mock("@/components/LanguageSwitcher", () => ({ default: () => null }));

vi.mock("@/modules/user/uiPreferencesApi", () => ({
  fetchUserUiPreferences: mocks.fetchPreferences,
  patchUserUiPreferences: mocks.patchPreferences,
}));

vi.mock("@/modules/modelProvider/api", () => ({
  modelProvidersApi: {
    apiCoreModelProvidersSelectedModelsGet: mocks.getSelectedModels,
    apiCoreModelProvidersModelsGet: mocks.getModels,
    apiCoreModelProvidersSelectedModelsPut: mocks.putSelectedModels,
  },
  unwrapModelProviderData: (payload: unknown) => {
    if (payload && typeof payload === "object" && "data" in payload) {
      return (payload as { data: unknown }).data;
    }
    return payload;
  },
}));

function model(id: string, name: string, modelType: string): ListModelProviderGroupModelsOpenAPIItem {
  return {
    id,
    name,
    model_type: modelType,
    provider_name: "Test Provider",
    group_name: "Verified",
    base_url: "https://example.com",
    user_model_provider_id: "provider",
    user_model_provider_group_id: "group",
    is_default: true,
    is_editable: false,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
}

function renderGate() {
  return render(
    <MemoryRouter initialEntries={["/agent/chat/home"]}>
      <LocationProbe />
      <WelcomeOnboardingGate enabled userKey="user-1">
        <div>Main chat</div>
      </WelcomeOnboardingGate>
    </MemoryRouter>,
  );
}

describe("WelcomeOnboardingGate", () => {
  beforeEach(() => {
    mocks.fetchPreferences.mockReset().mockResolvedValue({
      welcome_onboarding_completed: false,
      welcome_identity: "",
      welcome_tasks: [],
      updated_at: "2026-09-09T00:00:00Z",
    });
    mocks.patchPreferences.mockReset().mockResolvedValue({});
    mocks.getSelectedModels.mockReset().mockResolvedValue({ data: { selections: [] } });
    mocks.getModels.mockReset().mockImplementation(({ modelType }: { modelType: string }) => {
      const models: Record<string, ListModelProviderGroupModelsOpenAPIItem[]> = {
        llm: [model("llm-fast", "chat-flash", "llm")],
        embed_main: [model("embed", "embedding-model", "embed")],
        text2image: [model("image", "image-model", "text2image")],
      };
      return Promise.resolve({ data: { models: models[modelType] || [] } });
    });
    mocks.putSelectedModels.mockReset().mockResolvedValue({ data: { selections: [] } });
  });

  it("does not interrupt users who already completed onboarding", async () => {
    mocks.fetchPreferences.mockResolvedValue({
      welcome_onboarding_completed: true,
      welcome_identity: "",
      welcome_tasks: [],
      updated_at: "2026-09-09T00:00:00Z",
    });
    renderGate();
    expect(await screen.findByText("Main chat")).toBeInTheDocument();
    expect(mocks.getModels).not.toHaveBeenCalled();
  });

  it("updates related recommendations and saves them with role and tasks", async () => {
    renderGate();
    expect(await screen.findByText("让 LazyMind 更懂你的工作方式")).toBeInTheDocument();
    expect(screen.getByText("chat-flash")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /设计或创意/ }));
    fireEvent.click(screen.getByRole("button", { name: /知识库或企业资料问答/ }));

    expect(screen.getByText("image-model")).toBeInTheDocument();
    expect(screen.getByText("embedding-model")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /使用推荐配置并开始/ }));

    await waitFor(() => {
      expect(mocks.putSelectedModels).toHaveBeenCalledWith({
        setSelectedModelsOpenAPIRequest: {
          selections: [
            { model_key: "llm", model_id: "llm-fast" },
            { model_key: "embed_main", model_id: "embed" },
            { model_key: "text2image", model_id: "image" },
          ],
        },
      });
      expect(mocks.patchPreferences).toHaveBeenCalledWith({
        welcome_onboarding_completed: true,
        welcome_identity: "design_creative",
        welcome_tasks: ["knowledge_enterprise_qa"],
      });
    });
    expect(await screen.findByText("Main chat")).toBeInTheDocument();
  }, 15_000);

  it("lets a new user skip directly to chat", async () => {
    renderGate();
    await screen.findByText("让 LazyMind 更懂你的工作方式");
    fireEvent.click(screen.getByRole("button", { name: "跳过，直接开始" }));

    await waitFor(() => {
      expect(mocks.patchPreferences).toHaveBeenCalledWith({
        welcome_onboarding_completed: true,
        welcome_identity: "",
        welcome_tasks: [],
      });
    });
    expect(await screen.findByText("Main chat")).toBeInTheDocument();
    expect(mocks.putSelectedModels).not.toHaveBeenCalled();
  });

  it("opens full model settings from show more models", async () => {
    renderGate();
    await screen.findByText("让 LazyMind 更懂你的工作方式");
    fireEvent.click(screen.getByRole("button", { name: "展示更多模型" }));

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/settings?section=models");
      expect(mocks.patchPreferences).toHaveBeenCalledWith({
        welcome_onboarding_completed: true,
        welcome_identity: "",
        welcome_tasks: [],
      });
    });
  });
});
