// V0.8.2 平台抽象层 (Architecture: 包裝预留)
//
// 目的: 让 web 模式 和未来 desktop 模式 (Tauri/Electron) 用同一套 API
// 当前 web 模式: 大部分 capability 是 stub (no-op 或 web API fallback)
// 未来 desktop 模式: Tauri 启动时会在 window.__CYCLING_COACH_PLATFORM__ 注入真实实现
//
// 设计原则:
// 1. 默认 web 模式不引入新依赖 (Tauri/Electron 都不引)
// 2. 平台能力 detect + 软失败: 不支持就 fallback, 不抛错
// 3. 接口稳定: 上层 (page/component) 只调 platform.cap.*, 不直接判断环境
// 4. desktop 集成点集中在 1 个文件 (platform.ts), 改 1 处即可切换实现
//
// V0.8.3.1 P1: 当前 web 模式只用了 useAppEnv() (App.tsx:13), 返回 "web" 是 no-op
//   暂保留是因为:
//   - desktop roadmap (V0.8.4 候选): Tauri 打包, 单 .exe 安装
//   - 1 个 file 就把 capability 全部 expose, 改 1 处可切实现
//   - 删了的话等真做 desktop 时要重新设计抽象层
//
// 不需要的 cleanup:
//   - 如果 V0.9 之前 desktop 不开始做, 整个文件应该删掉
//   - 截至 V0.8.3.1 此文件与现有 web 代码解耦, 没产生 runtime overhead

// =============== 类型定义 ===============

export type AppEnv = "web" | "desktop" | "tauri" | "electron";
export type Platform = "darwin" | "win32" | "linux" | "unknown";

export interface Capabilities {
  // 文件系统 (desktop 可用 OS dialog, web 只能用 <input type=file>)
  openFile: (options?: { accept?: string }) => Promise<File | null>;
  saveFile: (options?: { defaultName?: string; content?: string }) => Promise<void>;

  // 系统通知
  notify: (title: string, body: string) => Promise<void>;

  // 应用生命周期
  quit: () => Promise<void>;
  getVersion: () => Promise<string>;

  // 全局快捷键 (注册 Cmd+Q 等系统级快捷键)
  registerShortcut: (key: string, callback: () => void) => () => void;

  // 系统集成
  openExternal: (url: string) => Promise<void>;
  setWindowTitle: (title: string) => Promise<void>;
}

export interface PlatformInfo {
  env: AppEnv;
  platform: Platform;
  version: string;
  /** desktop 模式才有的: 应用数据目录 (sqlite/log/config 都放这) */
  appDataDir?: string;
}

// =============== 当前实现: web 模式 (stub + web API) ===============

const webCapabilities: Capabilities = {
  // <input type=file> 模拟"打开文件"
  openFile: async (options) => {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      if (options?.accept) input.accept = options.accept;
      input.style.display = "none";
      document.body.appendChild(input);
      input.onchange = () => {
        const file = input.files?.[0] ?? null;
        document.body.removeChild(input);
        resolve(file);
      };
      input.oncancel = () => {
        document.body.removeChild(input);
        resolve(null);
      };
      input.click();
    });
  },
  // web 不能真正保存文件, 用 <a download> 模拟
  saveFile: async (options) => {
    if (!options?.content) return;
    const blob = new Blob([options.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = options.defaultName ?? "download.txt";
    a.click();
    URL.revokeObjectURL(url);
  },
  // web 用 Notification API
  notify: async (title, body) => {
    if ("Notification" in window) {
      if (Notification.permission === "granted") {
        new Notification(title, { body });
      } else if (Notification.permission !== "denied") {
        const p = await Notification.requestPermission();
        if (p === "granted") new Notification(title, { body });
      }
    }
  },
  quit: async () => {
    // web 没有 quit 概念, 关 tab
    window.close();
  },
  getVersion: async () => {
    // 从 /api/version 拿 (backend 是 SSOT)
    try {
      const r = await fetch("/api/version");
      const d = await r.json();
      return d.version ?? "unknown";
    } catch {
      return "unknown";
    }
  },
  // web 不能注册系统快捷键, 但能绑 DOM 事件
  registerShortcut: (key, callback) => {
    const handler = (e: KeyboardEvent) => {
      // 简单 key match: "Cmd+K" / "Ctrl+S" 等
      const isMac = navigator.platform.toLowerCase().includes("mac");
      const wantsMeta = key.toLowerCase().includes("cmd") || key.toLowerCase().includes("meta");
      const wantsCtrl = key.toLowerCase().includes("ctrl");
      if (wantsMeta && e.metaKey && !isMac) return;
      if (wantsCtrl && e.ctrlKey && isMac) return;
      if (e.key.toLowerCase() === key.split("+").pop()?.toLowerCase()) {
        callback();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  },
  // web 用 window.open
  openExternal: async (url) => {
    window.open(url, "_blank", "noopener,noreferrer");
  },
  // web 不能改浏览器 tab 标题, 但能改 document.title
  setWindowTitle: async (title) => {
    document.title = title;
  },
};

// =============== Desktop 注入点 ===============
// 未来 Tauri 启动时, 会调用此函数注入真实实现
// 例 (Tauri 集成代码):
//   window.__CYCLING_COACH_PLATFORM__ = {
//     capabilities: { openFile: ..., notify: ..., ... },
//     info: { env: "tauri", platform: "darwin", version: "0.8.2" }
//   };

declare global {
  interface Window {
    __CYCLING_COACH_PLATFORM__?: {
      capabilities: Partial<Capabilities>;
      info: Partial<PlatformInfo>;
    };
  }
}

function detectPlatform(): { caps: Capabilities; info: PlatformInfo } {
  // 优先用 desktop 注入
  if (typeof window !== "undefined" && window.__CYCLING_COACH_PLATFORM__) {
    const override = window.__CYCLING_COACH_PLATFORM__;
    const merged: Capabilities = { ...webCapabilities, ...override.capabilities };
    const info: PlatformInfo = {
      env: override.info.env ?? "web",
      platform: override.info.platform ?? detectPlatformOnly(),
      version: override.info.version ?? "unknown",
      appDataDir: override.info.appDataDir,
    };
    return { caps: merged, info };
  }
  // fallback: web
  return {
    caps: webCapabilities,
    info: {
      env: "web",
      platform: detectPlatformOnly(),
      version: "unknown",
    },
  };
}

function detectPlatformOnly(): Platform {
  if (typeof navigator === "undefined") return "unknown";
  const p = navigator.platform?.toLowerCase() ?? "";
  if (p.includes("mac")) return "darwin";
  if (p.includes("win")) return "win32";
  if (p.includes("linux")) return "linux";
  return "unknown";
}

// =============== 单例 + React Hook ===============

let _instance: { caps: Capabilities; info: PlatformInfo } | null = null;

export function getPlatform() {
  if (!_instance) _instance = detectPlatform();
  return _instance;
}

export function usePlatform() {
  return getPlatform();
}

export function useAppEnv(): AppEnv {
  return getPlatform().info.env;
}

export function useIsDesktop(): boolean {
  return getPlatform().info.env !== "web";
}

// =============== 测试 / dev 工具 ===============

// 仅 dev 模式可调用: 重置 platform cache (HMR 用)
export function _resetPlatformCacheForDev() {
  _instance = null;
}

if (typeof window !== "undefined") {
  // 调试用: 浏览器 console 里能查
  (window as any).__cycling_coach_platform__ = getPlatform;
}