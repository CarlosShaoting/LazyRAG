import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button, Spin, message } from "antd";
import {
  BarChartOutlined,
  BookOutlined,
  BulbOutlined,
  CheckOutlined,
  CodeOutlined,
  CustomerServiceOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  GlobalOutlined,
  HighlightOutlined,
  IdcardOutlined,
  PictureOutlined,
  ProjectOutlined,
  ReadOutlined,
  RocketOutlined,
  SolutionOutlined,
  TeamOutlined,
  TranslationOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type {
  ListModelProviderGroupModelsOpenAPIItem,
  SelectedModelOpenAPIItem,
  UserUIPreferencesOpenAPIResponse,
} from "@/api/generated/core-client";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { modelProvidersApi, unwrapModelProviderData } from "@/modules/modelProvider/api";
import { CHAT_HOME_PATH } from "@/modules/chat/constants/chat";
import { fetchUserUiPreferences, patchUserUiPreferences } from "@/modules/user/uiPreferencesApi";
import logoImage from "@/public/Lazy.png";
import {
  WELCOME_IDENTITIES,
  WELCOME_TASKS,
  getRecommendedCapabilities,
  recommendWelcomeModels,
  type AvailableWelcomeModels,
  type RecommendedModel,
  type RecommendedModelCapability,
  type WelcomeIdentity,
  type WelcomeTask,
} from "./modelRecommendation";
import "./index.scss";

interface WelcomeOnboardingGateProps {
  children: ReactNode;
  enabled: boolean;
  userKey: string;
}

interface WelcomeBootstrap {
  available: AvailableWelcomeModels;
  currentModelIDs: Partial<Record<RecommendedModelCapability, string>>;
  identity: WelcomeIdentity | "";
  tasks: WelcomeTask[];
}

type GateState =
  | { status: "idle"; userKey: string }
  | { status: "loading"; userKey: string }
  | { status: "hidden"; userKey: string }
  | { status: "visible"; userKey: string; bootstrap: WelcomeBootstrap };

const MODEL_CAPABILITIES: RecommendedModelCapability[] = [
  "llm",
  "embed_main",
  "text2image",
];
const silentOptions = { silentError: true } as never;

const identityIcons: Record<WelcomeIdentity, ReactNode> = {
  product_operations: <ProjectOutlined />,
  engineering_technology: <CodeOutlined />,
  design_creative: <HighlightOutlined />,
  marketing_content: <EditOutlined />,
  sales_customer_service: <CustomerServiceOutlined />,
  management_function: <TeamOutlined />,
  student_researcher: <ExperimentOutlined />,
  general_office: <SolutionOutlined />,
  other: <UserOutlined />,
  prefer_not_to_say: <IdcardOutlined />,
};

const taskIcons: Record<WelcomeTask, ReactNode> = {
  daily_qa_writing: <BulbOutlined />,
  summary_translation: <TranslationOutlined />,
  deep_analysis_research: <ReadOutlined />,
  documents_presentations_spreadsheets: <FileTextOutlined />,
  data_analysis_processing: <BarChartOutlined />,
  image_generation_design: <PictureOutlined />,
  knowledge_enterprise_qa: <BookOutlined />,
  other: <GlobalOutlined />,
};

const capabilityIcons: Record<RecommendedModelCapability, ReactNode> = {
  llm: <RocketOutlined />,
  embed_main: <BookOutlined />,
  text2image: <PictureOutlined />,
};

function isWelcomeIdentity(value: string): value is WelcomeIdentity {
  return (WELCOME_IDENTITIES as readonly string[]).includes(value);
}

function isWelcomeTask(value: string): value is WelcomeTask {
  return (WELCOME_TASKS as readonly string[]).includes(value);
}

async function loadWelcomeBootstrap(): Promise<{
  bootstrap?: WelcomeBootstrap;
  hidden: boolean;
}> {
  const [preferences, selectedResponse] = await Promise.all([
    fetchUserUiPreferences(silentOptions),
    modelProvidersApi.apiCoreModelProvidersSelectedModelsGet(silentOptions),
  ]);
  const selections = unwrapModelProviderData<{ selections?: SelectedModelOpenAPIItem[] }>(
    selectedResponse.data,
  ).selections || [];

  if (preferences.welcome_onboarding_completed) {
    return { hidden: true };
  }

  // Older local installations may have a model selection but no UI-preference row.
  // Treat those as established users and persist the compatibility decision once.
  if (!preferences.updated_at && selections.length > 0) {
    void patchUserUiPreferences({ welcome_onboarding_completed: true }).catch(() => undefined);
    return { hidden: true };
  }

  const modelResults = await Promise.allSettled(
    MODEL_CAPABILITIES.map((modelType) =>
      modelProvidersApi.apiCoreModelProvidersModelsGet(
        { modelType },
        silentOptions,
      ),
    ),
  );
  const available = MODEL_CAPABILITIES.reduce<AvailableWelcomeModels>(
    (result, capability, index) => {
      const response = modelResults[index];
      result[capability] = response.status === "fulfilled"
        ? unwrapModelProviderData<{ models?: ListModelProviderGroupModelsOpenAPIItem[] }>(
            response.value.data,
          ).models || []
        : [];
      return result;
    },
    { llm: [], embed_main: [], text2image: [] },
  );
  const currentModelIDs = selections.reduce<
    Partial<Record<RecommendedModelCapability, string>>
  >((result, selection) => {
    if (MODEL_CAPABILITIES.includes(selection.model_key as RecommendedModelCapability)) {
      result[selection.model_key as RecommendedModelCapability] = selection.model_id;
    }
    return result;
  }, {});
  const identity = isWelcomeIdentity(preferences.welcome_identity || "")
    ? preferences.welcome_identity as WelcomeIdentity
    : "";
  const tasks = (preferences.welcome_tasks || []).filter(isWelcomeTask);

  return {
    hidden: false,
    bootstrap: { available, currentModelIDs, identity, tasks },
  };
}

function recommendationLabel(capability: RecommendedModelCapability, t: (key: string) => string) {
  return t(`welcomeOnboarding.recommendation.capabilities.${capability}`);
}

function RecommendedModelCard({ recommendation }: { recommendation: RecommendedModel }) {
  const { t } = useTranslation();
  const { capability, model, reason } = recommendation;
  return (
    <article className="welcome-recommendation-card">
      <span className={`welcome-recommendation-icon is-${capability}`} aria-hidden="true">
        {capabilityIcons[capability]}
      </span>
      <div className="welcome-recommendation-copy">
        <div className="welcome-recommendation-heading">
          <span>{recommendationLabel(capability, t)}</span>
          <em>{t("welcomeOnboarding.recommendation.recommended")}</em>
        </div>
        <strong>{model.name}</strong>
        <small>{model.provider_name}{model.group_name ? ` · ${model.group_name}` : ""}</small>
        <p>{t(`welcomeOnboarding.recommendation.reasons.${reason}`)}</p>
      </div>
    </article>
  );
}

function WelcomeOnboardingPage({
  bootstrap,
  onDone,
}: {
  bootstrap: WelcomeBootstrap;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [identity, setIdentity] = useState<WelcomeIdentity | "">(bootstrap.identity);
  const [tasks, setTasks] = useState<WelcomeTask[]>(bootstrap.tasks);
  const [saving, setSaving] = useState<"recommended" | "skip" | "settings" | null>(null);
  const recommendedModels = useMemo(
    () => recommendWelcomeModels(
      bootstrap.available,
      identity,
      tasks,
      bootstrap.currentModelIDs,
    ),
    [bootstrap.available, bootstrap.currentModelIDs, identity, tasks],
  );
  const requestedCapabilities = useMemo(
    () => getRecommendedCapabilities(identity, tasks),
    [identity, tasks],
  );
  const missingCapabilities = requestedCapabilities.filter(
    (capability) => !recommendedModels.some((item) => item.capability === capability),
  );
  const hasChatRecommendation = recommendedModels.some((item) => item.capability === "llm");

  const preferencePatch = () => ({
    welcome_onboarding_completed: true,
    welcome_identity: identity,
    welcome_tasks: tasks,
  });

  const finishAndOpenChat = () => {
    onDone();
    navigate(CHAT_HOME_PATH, { replace: true });
  };

  const handleSkip = async () => {
    setSaving("skip");
    try {
      await patchUserUiPreferences({
        welcome_onboarding_completed: true,
        welcome_identity: "",
        welcome_tasks: [],
      });
    } catch {
      message.warning(t("welcomeOnboarding.messages.skipNotSaved"));
    } finally {
      setSaving(null);
      finishAndOpenChat();
    }
  };

  const handleMoreModels = async () => {
    setSaving("settings");
    try {
      await patchUserUiPreferences(preferencePatch());
    } catch {
      message.warning(t("welcomeOnboarding.messages.skipNotSaved"));
    } finally {
      setSaving(null);
      onDone();
      navigate("/settings?section=models");
    }
  };

  const handleUseRecommended = async () => {
    if (!hasChatRecommendation) return;
    setSaving("recommended");
    try {
      await modelProvidersApi.apiCoreModelProvidersSelectedModelsPut({
        setSelectedModelsOpenAPIRequest: {
          selections: recommendedModels.map(({ capability, model }) => ({
            model_key: capability,
            model_id: model.id,
          })),
        },
      });
      await patchUserUiPreferences(preferencePatch());
      message.success(t("welcomeOnboarding.messages.saved"));
      finishAndOpenChat();
    } catch {
      message.error(t("welcomeOnboarding.messages.saveFailed"));
    } finally {
      setSaving(null);
    }
  };

  const toggleTask = (task: WelcomeTask) => {
    setTasks((current) => current.includes(task)
      ? current.filter((item) => item !== task)
      : [...current, task]);
  };

  const logoSrc =
    (import.meta.env as ImportMetaEnv & { VITE_APP_LOGO?: string }).VITE_APP_LOGO ||
    logoImage;

  return (
    <main className="welcome-onboarding-page">
      <header className="welcome-onboarding-topbar">
        <div className="welcome-onboarding-brand">
          <img src={logoSrc} alt="" />
          <span>LazyMind</span>
        </div>
        <div className="welcome-onboarding-top-actions">
          <LanguageSwitcher />
          <Button
            type="text"
            loading={saving === "skip"}
            disabled={saving !== null && saving !== "skip"}
            onClick={() => void handleSkip()}
          >
            {t("welcomeOnboarding.skip")}
          </Button>
        </div>
      </header>

      <div className="welcome-onboarding-scroll">
        <section className="welcome-onboarding-shell" aria-labelledby="welcome-onboarding-title">
          <div className="welcome-onboarding-hero">
            <span>{t("welcomeOnboarding.eyebrow")}</span>
            <h1 id="welcome-onboarding-title">{t("welcomeOnboarding.title")}</h1>
            <p>{t("welcomeOnboarding.subtitle")}</p>
          </div>

          <section className="welcome-choice-section" aria-labelledby="welcome-identity-title">
            <div className="welcome-section-heading">
              <span>1</span>
              <div>
                <h2 id="welcome-identity-title">{t("welcomeOnboarding.identityTitle")}</h2>
                <p>{t("welcomeOnboarding.identityHint")}</p>
              </div>
            </div>
            <div className="welcome-choice-grid is-identity">
              {WELCOME_IDENTITIES.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={identity === item ? "is-selected" : ""}
                  aria-pressed={identity === item}
                  onClick={() => setIdentity(item)}
                >
                  <span aria-hidden="true">{identityIcons[item]}</span>
                  {t(`welcomeOnboarding.identities.${item}`)}
                  {identity === item ? <CheckOutlined className="welcome-choice-check" /> : null}
                </button>
              ))}
            </div>
          </section>

          <section className="welcome-choice-section" aria-labelledby="welcome-tasks-title">
            <div className="welcome-section-heading">
              <span>2</span>
              <div>
                <h2 id="welcome-tasks-title">{t("welcomeOnboarding.tasksTitle")}</h2>
                <p>{t("welcomeOnboarding.tasksHint")}</p>
              </div>
            </div>
            <div className="welcome-choice-grid is-task">
              {WELCOME_TASKS.map((item) => {
                const selected = tasks.includes(item);
                return (
                  <button
                    key={item}
                    type="button"
                    className={selected ? "is-selected" : ""}
                    aria-pressed={selected}
                    onClick={() => toggleTask(item)}
                  >
                    <span aria-hidden="true">{taskIcons[item]}</span>
                    {t(`welcomeOnboarding.tasks.${item}`)}
                    {selected ? <CheckOutlined className="welcome-choice-check" /> : null}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="welcome-recommendation-section" aria-labelledby="welcome-recommendation-title">
            <div className="welcome-section-heading">
              <span>3</span>
              <div>
                <h2 id="welcome-recommendation-title">{t("welcomeOnboarding.recommendation.title")}</h2>
                <p>{t("welcomeOnboarding.recommendation.hint")}</p>
              </div>
            </div>
            {recommendedModels.length > 0 ? (
              <div className="welcome-recommendation-grid">
                {recommendedModels.map((recommendation) => (
                  <RecommendedModelCard
                    key={recommendation.capability}
                    recommendation={recommendation}
                  />
                ))}
              </div>
            ) : null}
            {missingCapabilities.length > 0 ? (
              <div className="welcome-recommendation-missing" role="status">
                <span><BulbOutlined /></span>
                <p>
                  <strong>{t("welcomeOnboarding.recommendation.missingTitle")}</strong>
                  {t("welcomeOnboarding.recommendation.missingDescription", {
                    capabilities: missingCapabilities
                      .map((capability) => recommendationLabel(capability, t))
                      .join(t("welcomeOnboarding.recommendation.separator")),
                  })}
                </p>
              </div>
            ) : null}
          </section>

          <footer className="welcome-onboarding-footer">
            <div>
              <Button
                type="link"
                loading={saving === "settings"}
                disabled={saving !== null && saving !== "settings"}
                onClick={() => void handleMoreModels()}
              >
                {t("welcomeOnboarding.moreModels")}
              </Button>
              <span>{t("welcomeOnboarding.moreModelsHint")}</span>
            </div>
            <Button
              type="primary"
              size="large"
              icon={<RocketOutlined />}
              loading={saving === "recommended"}
              disabled={!hasChatRecommendation || (saving !== null && saving !== "recommended")}
              onClick={() => void handleUseRecommended()}
            >
              {t("welcomeOnboarding.start")}
            </Button>
          </footer>
        </section>
      </div>
    </main>
  );
}

export default function WelcomeOnboardingGate({
  children,
  enabled,
  userKey,
}: WelcomeOnboardingGateProps) {
  const [state, setState] = useState<GateState>({ status: "idle", userKey: "" });

  useEffect(() => {
    if (!enabled || !userKey) return;
    let cancelled = false;
    setState({ status: "loading", userKey });
    void loadWelcomeBootstrap()
      .then((result) => {
        if (cancelled) return;
        setState(result.hidden || !result.bootstrap
          ? { status: "hidden", userKey }
          : { status: "visible", userKey, bootstrap: result.bootstrap });
      })
      .catch(() => {
        // Onboarding is optional. A preference/model API outage must not block chat.
        if (!cancelled) setState({ status: "hidden", userKey });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, userKey]);

  if (!enabled || !userKey) return children;
  if (state.userKey !== userKey || state.status === "idle" || state.status === "loading") {
    return (
      <div className="welcome-onboarding-loading">
        <Spin size="large" />
        <span>LazyMind</span>
      </div>
    );
  }
  if (state.status !== "visible") return children;
  return (
    <WelcomeOnboardingPage
      bootstrap={state.bootstrap}
      onDone={() => setState({ status: "hidden", userKey })}
    />
  );
}
