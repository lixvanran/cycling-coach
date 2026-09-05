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
    activeMode: "chat",

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
