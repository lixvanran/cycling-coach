// Chat Store — V0.8.0 拆分
// 3 mode 消息历史 (chatMessagesRag, chatMessagesWorkflow, chatMessagesChat)
// + 旧 chatMessages 字段保留作为默认 (chat 模式) 的别名, 向后兼容 ChatPage
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export type ChatMode = "rag" | "workflow" | "chat";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;          // 真实内容(不含 [THINK] 标签)
  thinking?: string;         // 思考过程
  timestamp: number;
  error?: string;
  mode?: ChatMode;           // V0.8.0: 标记消息所属 mode
}

interface ChatState {
  // V0.8.0: 3 mode 分别存
  chatMessagesRag: ChatMsg[];
  chatMessagesWorkflow: ChatMsg[];
  chatMessagesChat: ChatMsg[];

  // V0.8.0: 当前激活的 mode
  activeMode: ChatMode;

  // 旧字段 — 兼容旧 ChatPage
  chatMessages: ChatMsg[];        // == chatMessagesChat (shim 同步)
  isStreaming: boolean;
  addChatMessage: (m: ChatMsg) => void;
  updateLastAssistant: (patch: Partial<ChatMsg>) => void;
  clearChat: () => void;
  setStreaming: (b: boolean) => void;

  // V0.8.0 新 API
  appendMessage: (mode: ChatMode, msg: ChatMsg) => void;
  updateLastMessage: (mode: ChatMode, patch: Partial<ChatMsg>) => void;
  clearMessages: (mode: ChatMode) => void;
  setActiveMode: (m: ChatMode) => void;
}

const keyOf = (mode: ChatMode): "chatMessagesRag" | "chatMessagesWorkflow" | "chatMessagesChat" => {
  if (mode === "rag") return "chatMessagesRag";
  if (mode === "workflow") return "chatMessagesWorkflow";
  return "chatMessagesChat";
};

const syncLegacyMessages = (mode: ChatMode, list: ChatMsg[]): Partial<ChatState> => {
  // 让旧字段 chatMessages 始终等于 "chat" mode 的列表
  if (mode === "chat") return { chatMessages: list };
  return {};
};

export const useChatStore = create<ChatState>()(
  subscribeWithSelector((set, get) => ({
    chatMessagesRag: [],
    chatMessagesWorkflow: [],
    chatMessagesChat: [],
    // V0.9.0: 默认落在「训练答疑」(rag), 不是「随便聊聊」(chat)。
    //
    // 原来这里是 "chat" —— 而三个 tab 分别是:
    //   rag      → 训练答疑 (RAG 知识库 + 你的训练数据)  ← 招牌功能
    //   workflow → 战术规划
    //   chat     → 随便聊聊                              ← 最没差异化
    // 这个 store 没有 persist, 所以**默认值每次打开都生效**: 用户打开 AI 页
    // 看到的第一个界面是"随便聊聊"。对一个公路车教练产品来说, 落地在一个
    // 通用闲聊上, 等于把最核心的差异化能力藏在第三个 tab 后面。
    //
    // 这条 bug 之所以长期没人发现: 曾经有个测试断言过"默认 tab 是训练答疑",
    // 但它 import 了没装的 @testing-library, 从来没真正跑过 ——
    // 测试写的是对的意图, 产品却一直是错的。
    activeMode: "rag",

    // 旧字段 — 默认指向 chat mode
    chatMessages: [],
    isStreaming: false,

    // 旧 API (ChatPage.tsx 用) — 都默认操作 chat mode
    addChatMessage: (m) => {
      const list = [...get().chatMessagesChat, { ...m, mode: "chat" as ChatMode }];
      set({ chatMessagesChat: list, chatMessages: list });
    },
    updateLastAssistant: (patch) => {
      const msgs = [...get().chatMessagesChat];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], ...patch };
          break;
        }
      }
      set({ chatMessagesChat: msgs, chatMessages: msgs });
    },
    clearChat: () => {
      set({ chatMessagesChat: [], chatMessages: [] });
    },
    setStreaming: (b) => set({ isStreaming: b }),

    // 新 API
    appendMessage: (mode, msg) => {
      const k = keyOf(mode);
      const list = [...get()[k], { ...msg, mode }];
      set({ [k]: list, ...syncLegacyMessages(mode, list) } as any);
    },
    updateLastMessage: (mode, patch) => {
      const k = keyOf(mode);
      const msgs = [...get()[k]];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], ...patch };
          break;
        }
      }
      set({ [k]: msgs, ...syncLegacyMessages(mode, msgs) } as any);
    },
    clearMessages: (mode) => {
      const k = keyOf(mode);
      set({ [k]: [], ...syncLegacyMessages(mode, []) } as any);
    },
    setActiveMode: (m) => set({ activeMode: m }),
  }))
);
