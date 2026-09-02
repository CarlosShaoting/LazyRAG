import { act, renderHook, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Modal } from "antd";
import {
  ChatConversationsRequestActionEnum,
  ChatConversationsResponseFinishReasonEnum,
} from "@/api/generated/chatbot-client";
import { RoleTypes } from "@/modules/chat/constants/common";
import type { ChatInputImperativeProps } from "../../ChatInput";
import { useChatConversation } from "./useChatConversation";
import { useTaskCenterStore } from "@/modules/chat/store/taskCenter";

const { waitForRuntimeCapabilityMock } = vi.hoisted(() => ({
  waitForRuntimeCapabilityMock: vi.fn(),
}));

vi.mock("@/runtime/readiness", () => ({
  waitForRuntimeCapability: waitForRuntimeCapabilityMock,
}));

vi.mock("antd", () => ({
  Button: "button",
  message: {
    error: vi.fn(),
    warning: vi.fn(),
  },
  Modal: { confirm: vi.fn() },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../../ImageUpload", () => ({
  allowedImageTypes: [".png", ".jpg", ".jpeg"],
}));

vi.mock("@/modules/chat/utils/request", () => ({
  ChatServiceApi: () => ({}),
}));

vi.mock("@/modules/chat/utils/conversationActivity", () => ({
  emitConversationActivity: vi.fn(),
}));

vi.mock("./useChatScroll", () => ({
  useChatScroll: () => ({
    chatContentRef: { current: null },
    isMouseScrollingRef: { current: false },
    showScrollButton: false,
    inputHeight: 120,
    scrollToEnd: vi.fn(),
    scrollToEndImmediately: vi.fn(),
    handleScroll: vi.fn(),
    handleToBottom: vi.fn(),
    handleInputHeightChange: vi.fn(),
  }),
}));

describe("useChatConversation regeneration recovery", () => {
  beforeEach(() => {
    sessionStorage.clear();
    waitForRuntimeCapabilityMock.mockReset();
    waitForRuntimeCapabilityMock.mockResolvedValue(undefined);
    vi.mocked(Modal.confirm).mockClear();
    useTaskCenterStore.setState({
      activeConversationId: "",
      tasksByConversation: {},
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses freshly loaded history instead of a stale per-conversation cache", () => {
    const { result } = renderHook(() =>
      useChatConversation({
        canChat: true,
        onOpenSSE: vi.fn(),
        setIsChatContent: vi.fn(),
        clearStorePendingMessage: vi.fn(),
        clearCiteMessages: vi.fn(),
        chatInputRef: createRef<ChatInputImperativeProps>(),
        thinkingCollapseMap: new Map(),
        getUserEdit: () => undefined,
        t: (key) => key,
      }),
    );
    const first = [{ role: RoleTypes.ASSISTANT, delta: "cached answer" }];
    const second = [{ role: RoleTypes.ASSISTANT, delta: "server answer" }];

    act(() => {
      result.current.replaceMessageList("conversation-1", first);
      result.current.replaceMessageList("conversation-2", []);
      result.current.replaceMessageList("conversation-1", second);
    });

    expect(result.current.messageList).toEqual(second);
    expect(result.current.conversationMessagesCache.current.get("conversation-1"))
      .toEqual(second);
  });

  it("restores the previous answer and clears busy state when opening SSE rejects", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const onOpenSSE = vi.fn().mockRejectedValue(new Error("open failed"));
    const originalMessages = [
      {
        role: RoleTypes.USER,
        delta: "hello",
        inputs: [{ input_type: "text", text: "hello" }],
      },
      {
        role: RoleTypes.ASSISTANT,
        delta: "previous answer",
        history_id: "history-1",
        finish_reason:
          ChatConversationsResponseFinishReasonEnum.FinishReasonStop,
      },
    ];
    const { result } = renderHook(() =>
      useChatConversation({
        canChat: true,
        onOpenSSE,
        setIsChatContent: vi.fn(),
        clearStorePendingMessage: vi.fn(),
        clearCiteMessages: vi.fn(),
        chatInputRef: createRef<ChatInputImperativeProps>(),
        thinkingCollapseMap: new Map(),
        getUserEdit: () => undefined,
        t: (key) => key,
      }),
    );

    await act(async () => {
      result.current.replaceMessageList("conversation-1", originalMessages);
      await result.current.regenerate();
    });

    await waitFor(() => {
      expect(onOpenSSE).toHaveBeenCalledWith(
        originalMessages[0].inputs,
        ChatConversationsRequestActionEnum.ChatActionRegeneration,
        {},
        undefined,
      );
      expect(result.current.loading).toBe(false);
      expect(result.current.isStreaming).toBe(false);
      expect(result.current.activeStreamRef.current).toBe(false);
      expect(result.current.messageList).toEqual(originalMessages);
      expect(result.current.messageListRef.current).toEqual(originalMessages);
    });

    await act(async () => {
      await result.current.regenerate();
    });

    await waitFor(() => expect(onOpenSSE).toHaveBeenCalledTimes(2));
  });

  it("shows a setup card when a persisted workflow task contains a capability failure", async () => {
    renderHook(() =>
      useChatConversation({
        canChat: true,
        onOpenSSE: vi.fn(),
        setIsChatContent: vi.fn(),
        clearStorePendingMessage: vi.fn(),
        clearCiteMessages: vi.fn(),
        chatInputRef: createRef<ChatInputImperativeProps>(),
        thinkingCollapseMap: new Map(),
        getUserEdit: () => undefined,
        t: (key) => key,
      }),
    );
    const failure =
      'MEDIA_CAPABILITY_DEPENDENCY_MISSING '
      + '{"status":"blocked","workflow":"CREATE_ANIMATED_MEME",'
      + '"required":["video_generator"],"missing":[{"id":"video_generator",'
      + '"label":"视频生成模型","available":false,"settings_url":"/settings?section=models",'
      + '"reason":"尚未配置视频生成模型。"}],"message":"缺少视频生成模型。"}';

    act(() => {
      useTaskCenterStore.setState({
        activeConversationId: "conversation-capability",
        tasksByConversation: {
          "conversation-capability": [{
            task_id: "task-capability",
            conversation_id: "conversation-capability",
            title: "image-workflow:analyze_subject",
            agent_type: "workflow_step",
            mode: "auto",
            status: "failed",
            progress_pct: 100,
            artifacts: [],
            sources: [],
            artifact_streams: [],
            execution_log: [{ type: "tool_results", content: "", tool_results: [{
              tool_call_id: "tool-1",
              name: "check_image_workflow_capabilities",
              result: failure,
            }] }],
          }],
        },
      });
    });

    await waitFor(() => expect(Modal.confirm).toHaveBeenCalledTimes(1));
    expect(vi.mocked(Modal.confirm).mock.calls[0]?.[0]?.title)
      .toBe("chat.mediaCapabilitiesRequiredTitle");
  });
});
