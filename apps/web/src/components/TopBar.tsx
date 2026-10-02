// 顶部 Bar — V0.8.2
// 改动:
//   U-1 搜索框从死 input 改成 Cmd+K GlobalSearch 按钮
//   U-5 Mock 模式 indicator 从顶栏移除 (移去 /settings)
//   U-8 Bell 换成 NotificationsBell 组件, 显示未读洞察数
import { Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { GlobalSearch } from "./GlobalSearch";
import { NotificationsBell } from "./NotificationsBell";

export function TopBar() {
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    api.diagnose().then((d) => {
      setVersion(d.version);
    }).catch(() => {});
  }, []);

  return (
    <header className="h-12 bg-bg-base border-b border-border flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <GlobalSearch />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-text-muted">v{version}</span>
        <NotificationsBell />
        {/* V0.8.3 B3: 用户头像 — 砍渐变, 浅灰底 + 字母 (严肃风) */}
        <div className="w-8 h-8 rounded-full flex items-center justify-center bg-bg-subtle text-text-secondary border border-border text-xs font-semibold">
          R
        </div>
      </div>
    </header>
  );
}

// 保留 Cpu import 以防后续需要, 但目前 TopBar 不再展示 Mock 状态
// 如果需要给某处 (e.g. /settings 诊断) 用, 可以从 ./TopBar.MockBadge 引入
export function MockBadge() {
  const [mock, setMock] = useState<boolean | null>(null);
  useEffect(() => {
    api.diagnose().then((d) => setMock(d.m3_mock_mode)).catch(() => {});
  }, []);
  if (mock === null) return null;
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <Cpu size={12} className={mock ? "text-text-muted" : "text-accent-success"} />
      <span className={mock ? "text-text-muted" : "text-accent-success"}>
        {mock ? "Mock 模式" : "AI 在线"}
      </span>
    </div>
  );
}
