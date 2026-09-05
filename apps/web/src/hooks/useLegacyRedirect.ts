// useLegacyRedirect — 旧 view 字符串 → 新 URL 路径
// 用法: 在 App 顶层或 Sidebar 里 useLegacyRedirect() 一次即可
//
// 旧 V0.7.8 是 view-based (setView("dashboard") 等), 切到 URL 路由后:
//   /dashboard   → /training
//   /coach       → /ai/chat
//   /activities  → /training/activities
//   等等
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// 旧 view → 新 URL 路径
// 注意: 旧系统没有 URL, "旧 URL" 是想象中的. 这里用 #dashboard hash 模拟历史书签
export const LEGACY_REDIRECTS: Record<string, string> = {
  // hash 形式 (兼容老的可能存在的 localStorage / bookmark)
  "#dashboard": "/training",
  "#activities": "/training/activities",
  "#activity-detail": "/training/activities",  // 单独 ID 没法重定向, 落到列表
  "#trends": "/training/trends",
  "#diary": "/training/diary",
  "#insights": "/ai/hrv",                       // insights → hrv (Insights 已合并到 HRV)
  "#chat": "/ai/chat",
  "#race-tactics": "/ai/race-tactics",
  "#calendar": "/plan/calendar",
  "#library": "/plan/workouts",                  // library → workouts (课程库)
  "#builder": "/plan",                            // 课程编排 = plan 根
  "#kb": "/data/knowledge",
  "#kb-search": "/data/knowledge",
  "#kb-category": "/data/knowledge",
  "#import": "/data/import",
  "#ftp-test": "/data/ftp-test",
  "#profile": "/settings",
  "#compare": "/training/activities",            // 对比页面暂时落到训练列表(占位)
  "#phases": "/plan/phases",
};

// 旧路径形式 (万一有人写了 HTML href)
export const LEGACY_PATHS: Record<string, string> = {
  "/dashboard": "/training",
  "/coach": "/ai/chat",
  "/activities": "/training/activities",
  "/trends": "/training/trends",
  "/diary": "/training/diary",
  "/chat": "/ai/chat",
  "/calendar": "/plan/calendar",
  "/library": "/plan/workouts",
  "/builder": "/plan",
  "/import": "/data/import",
  "/kb": "/data/knowledge",
  "/insights": "/ai/hrv",
  "/ftp-test": "/data/ftp-test",
  "/profile": "/settings",
  "/phases": "/plan/phases",
  "/race-tactics": "/ai/race-tactics",
};

export function useLegacyRedirect() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // 1) hash 形式
    if (typeof window !== "undefined" && window.location.hash) {
      const target = LEGACY_REDIRECTS[window.location.hash];
      if (target) {
        navigate(target, { replace: true });
        return;
      }
    }
    // 2) 旧路径形式
    const cleaned = location.pathname.replace(/\/$/, "") || "/";
    const target = LEGACY_PATHS[cleaned];
    if (target) {
      navigate(target, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // 只在挂载时检查一次
}
