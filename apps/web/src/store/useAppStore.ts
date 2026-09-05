// V0.8.0 Shim — useAppStore 已拆分为 3 个新 store:
//   - useUIStore    (ui.ts)
//   - useChatStore  (chat.ts)
//   - useAthleteStore (athlete.ts)
//
// 旧代码 (e.g. ChatPage.tsx) 仍 import { useAppStore } from "./useAppStore";
// 这里保留一个聚合 hook, 把字段映射到新 store, 避免一次大爆炸改动。
//
// 新代码请直接用 3 个新 store; 这个 shim 会随 V0.8.x 后续版本逐步退役。
import { useChatStore } from "./chat";
import { useUIStore } from "./ui";
import { useAthleteStore } from "./athlete";

export type View =
  | "dashboard" | "calendar" | "activities" | "activity-detail" | "import"
  | "profile" | "chat" | "library" | "builder" | "kb" | "kb-search"
  | "compare" | "trends" | "phases" | "ftp-test" | "insights" | "diary"
  | "race-tactics" | "race-tactics-detail" | "kb-category";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  timestamp: number;
  error?: string;
}

export interface LegacyAppState {
  // --- 已迁移到 URL 路由, 这里保留 stub, 不持久化 ---
  view: View;
  setView: (v: View) => void;
  selectedActivityId: number | null;
  setSelectedActivity: (id: number | null) => void;
  selectedKbCategory: string | null;
  setSelectedKbCategory: (p: string | null) => void;

  // --- chat (从 useChatStore 透传) ---
  chatMessages: ChatMsg[];
  isStreaming: boolean;
  addChatMessage: (m: ChatMsg) => void;
  updateLastAssistant: (patch: Partial<ChatMsg>) => void;
  clearChat: () => void;
  setStreaming: (b: boolean) => void;
}

// 旧 useAppStore 兼容 hook
// 注意: 因为 V0.8.0 已切到 URL 路由, view/selectedActivityId/selectedKbCategory
// 不再是单一来源. 这里用 noop 防止旧代码抛错, 但推荐新代码用 useNavigate().
export function useAppStore<T>(selector: (s: LegacyAppState) => T): T {
  // 拼一个 legacy 视图对象, 字段从新 store 取
  const view: View = "dashboard";
  const setView = (_v: View) => {
    // noop — 路由已接管, 旧 setView 失效
    // 旧 setView 调用的页面正在被路由改造, 此后会消失
  };
  const selectedActivityId: number | null = null;
  const setSelectedActivity = (_id: number | null) => {};
  const selectedKbCategory: string | null = null;
  const setSelectedKbCategory = (_p: string | null) => {};

  const chatMessages = useChatStore((s) => s.chatMessages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const addChatMessage = useChatStore((s) => s.addChatMessage);
  const updateLastAssistant = useChatStore((s) => s.updateLastAssistant);
  const clearChat = useChatStore((s) => s.clearChat);
  const setStreaming = useChatStore((s) => s.setStreaming);

  const legacy: LegacyAppState = {
    view,
    setView,
    selectedActivityId,
    setSelectedActivity,
    selectedKbCategory,
    setSelectedKbCategory,
    chatMessages,
    isStreaming,
    addChatMessage,
    updateLastAssistant,
    clearChat,
    setStreaming,
  };
  return selector(legacy);
}

// V0.8.0: 也支持 useAppStore.getState() 这种非 hook 调用 — 直接代理到新 store
useAppStore.getState = () => {
  const chat = useChatStore.getState();
  return {
    view: "dashboard" as View,
    setView: () => {},
    selectedActivityId: null,
    setSelectedActivity: () => {},
    selectedKbCategory: null,
    setSelectedKbCategory: () => {},
    chatMessages: chat.chatMessages,
    isStreaming: chat.isStreaming,
    addChatMessage: chat.addChatMessage,
    updateLastAssistant: chat.updateLastAssistant,
    clearChat: chat.clearChat,
    setStreaming: chat.setStreaming,
  };
};

// V0.8.0: 重新导出 3 个新 store, 方便新代码直接拿
// (TypeScript 不允许重复声明, 用 export type 区分类型, value 用 export { } from)
export { useUIStore } from "./ui";
export type { UIState, Theme } from "./ui";
export { useChatStore } from "./chat";
export type { ChatMsg as NewChatMsg, ChatMode } from "./chat";
export { useAthleteStore } from "./athlete";
export type { AthleteProfile, ActivitySummaryItem } from "./athlete";
