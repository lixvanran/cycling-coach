// Zustand 全局 store
import { create } from "zustand";

export type View = "dashboard" | "calendar" | "activities" | "activity-detail" | "import" | "profile" | "chat" | "library" | "builder" | "kb" | "kb-search" | "compare" | "trends" | "phases" | "ftp-test" | "insights" | "diary" | "kb-category";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;          // 真实内容(不含 [THINK] 标签)
  thinking?: string;         // 思考过程
  timestamp: number;
  error?: string;
}

interface AppState {
  view: View;
  selectedActivityId: number | null;
  selectedKbCategory: string | null;
  setView: (v: View) => void;
  setSelectedActivity: (id: number | null) => void;
  setSelectedKbCategory: (p: string | null) => void;

  // Chat
  chatMessages: ChatMsg[];
  isStreaming: boolean;
  addChatMessage: (m: ChatMsg) => void;
  updateLastAssistant: (patch: Partial<ChatMsg>) => void;
  clearChat: () => void;
  setStreaming: (b: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  view: "dashboard",
  selectedActivityId: null,
  selectedKbCategory: null,
  setView: (v) => set({ view: v }),
  setSelectedActivity: (id) => set({ selectedActivityId: id }),
  setSelectedKbCategory: (p) => set({ selectedKbCategory: p }),

  chatMessages: [],
  isStreaming: false,
  addChatMessage: (m) => set((s) => ({ chatMessages: [...s.chatMessages, m] })),
  updateLastAssistant: (patch) =>
    set((s) => {
      const msgs = [...s.chatMessages];
      // 找最后一个 assistant 消息
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], ...patch };
          break;
        }
      }
      return { chatMessages: msgs };
    }),
  clearChat: () => set({ chatMessages: [] }),
  setStreaming: (b) => set({ isStreaming: b }),
}));
