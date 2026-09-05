// UI Store — V0.8.0 拆分
// 侧栏开合 / 主题 / 弹窗 / toast
// 旧 useAppStore 的 view/selectedActivityId 等路由状态不再存这里(改成 URL 路由)
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export type Theme = "light" | "dark";

export interface UIState {
  // 侧栏
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  // 主题
  theme: Theme;
  setTheme: (t: Theme) => void;

  // 全局弹窗(轻量)
  modal: { kind: string; payload?: any } | null;
  setModal: (m: UIState["modal"]) => void;

  // toast 顶层桥接(实际 toast 由 components/Toast.tsx 的 _listeners 跑,
  // 这里暴露一个 flag 让订阅者能 react to 新 toast)
  toastTick: number;
  pingToast: () => void;
}

export const useUIStore = create<UIState>()(
  subscribeWithSelector((set) => ({
    sidebarOpen: true,
    theme: "light",
    modal: null,
    toastTick: 0,
    toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    setSidebarOpen: (open) => set({ sidebarOpen: open }),
    setTheme: (t) => set({ theme: t }),
    setModal: (m) => set({ modal: m }),
    pingToast: () => set((s) => ({ toastTick: s.toastTick + 1 })),
  }))
);
