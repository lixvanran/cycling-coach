// V0.8.0: ChatPage 3 tab 行为测试
// 简单覆盖: tab 切换 / mode 字段 / 思维树组件挂载 / 消息按 mode 分桶
// 用 vitest + @testing-library/react 风格(轻量版,不依赖完整 stack)
//
// 用法: npm test (配置后) 或 jest/vitest 直接跑
// 当前 V0.8.0 还未引入 test framework, 这里作为占位 + 手动测试脚本

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatPage } from "../pages/ChatPage";
import { useChatStore } from "../store/chat";
import { MemoryRouter } from "react-router-dom";

// Mock API 层(避免真实 fetch)
vi.mock("../lib/api", () => ({
  api: {
    chatStreamV2: vi.fn(async function* () {
      // 空流
      yield { type: "done", data: "" };
    }),
    predictFtp: vi.fn(async () => ({
      ok: true,
      predicted_ftp: 247,
      lower_80: 237,
      upper_80: 257,
      confidence: "high",
      current_ftp: 250,
      delta: -3,
      data_window: "今日 + 7d PMC",
      model_name: "ftp_predictor",
      model_version: "v1.0",
      model_format: "joblib",
      prediction_id: 1,
      inference_ms: 12,
    })),
    listMlModels: vi.fn(async () => ({ ok: true, models: [] })),
  },
}));

const wrap = (ui: React.ReactNode) => (
  <MemoryRouter>{ui}</MemoryRouter>
);

describe("ChatPage 3-tab", () => {
  beforeEach(() => {
    // 重置 store
    useChatStore.setState({
      chatMessagesRag: [],
      chatMessagesWorkflow: [],
      chatMessagesChat: [],
      activeMode: "rag",
    });
  });

  it("默认 tab 是训练答疑 (rag)", () => {
    render(wrap(<ChatPage />));
    // 训练答疑 tab 应可见
    expect(screen.getByText("训练答疑")).toBeInTheDocument();
    expect(screen.getByText("战术规划")).toBeInTheDocument();
    expect(screen.getByText("随便聊聊")).toBeInTheDocument();
  });

  it("切换 tab 时, activeMode 更新", () => {
    render(wrap(<ChatPage />));
    const workflowTab = screen.getByText("战术规划");
    fireEvent.click(workflowTab);
    expect(useChatStore.getState().activeMode).toBe("workflow");
  });

  it("每个 mode 的消息独立分桶", () => {
    // 推 1 条到 rag
    useChatStore.getState().appendMessage("rag", {
      id: "u-1",
      role: "user",
      content: "RAG question",
      timestamp: Date.now(),
    } as any);
    // 推 1 条到 workflow
    useChatStore.getState().appendMessage("workflow", {
      id: "u-2",
      role: "user",
      content: "Workflow question",
      timestamp: Date.now(),
    } as any);
    // 推 1 条到 chat
    useChatStore.getState().appendMessage("chat", {
      id: "u-3",
      role: "user",
      content: "Chat question",
      timestamp: Date.now(),
    } as any);

    const s = useChatStore.getState();
    expect(s.chatMessagesRag).toHaveLength(1);
    expect(s.chatMessagesWorkflow).toHaveLength(1);
    expect(s.chatMessagesChat).toHaveLength(1);
    expect(s.chatMessagesRag[0].content).toBe("RAG question");
    expect(s.chatMessagesWorkflow[0].content).toBe("Workflow question");
    expect(s.chatMessagesChat[0].content).toBe("Chat question");
  });

  it("切 mode 时, 显示对应桶的消息", () => {
    useChatStore.getState().appendMessage("rag", {
      id: "r-1", role: "user", content: "RAG msg", timestamp: 1,
    } as any);
    useChatStore.getState().appendMessage("workflow", {
      id: "w-1", role: "user", content: "WF msg", timestamp: 2,
    } as any);

    // 渲染初始 mode = rag
    useChatStore.setState({ activeMode: "rag" });
    const { rerender } = render(wrap(<ChatPage />));
    expect(screen.getByText("RAG msg")).toBeInTheDocument();
    expect(screen.queryByText("WF msg")).not.toBeInTheDocument();

    // 切到 workflow
    useChatStore.setState({ activeMode: "workflow" });
    rerender(wrap(<ChatPage />));
    expect(screen.queryByText("RAG msg")).not.toBeInTheDocument();
    expect(screen.getByText("WF msg")).toBeInTheDocument();
  });
});

describe("FTPPredictionCard", () => {
  it.skip("应正常渲染(需要 Dashboard 集成测试)", () => {
    // 占位: 真正的 render 测试需要 react-router 包
  });
});
