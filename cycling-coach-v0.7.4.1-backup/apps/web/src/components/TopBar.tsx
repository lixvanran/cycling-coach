// 顶部 Bar
import { Bell, Search, Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function TopBar() {
  const [mockMode, setMockMode] = useState<boolean | null>(null);
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    api.diagnose().then((d) => {
      setMockMode(d.m3_mock_mode);
      setVersion(d.version);
    }).catch(() => {});
  }, []);

  return (
    <header className="h-12 bg-bg-base border-b border-border flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="搜索训练…"
            className="bg-bg-input border border-border rounded-md pl-8 pr-3 py-1.5 text-sm text-text-primary placeholder-text-muted w-72 focus:outline-none focus:border-accent-primary"
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        {mockMode !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <Cpu size={12} className={mockMode ? "text-text-muted" : "text-accent-success"} />
            <span className={mockMode ? "text-text-muted" : "text-accent-success"}>
              {mockMode ? "Mock 模式" : "AI 在线"}
            </span>
          </div>
        )}
        <span className="text-xs text-text-muted">v{version}</span>
        <button className="p-1.5 rounded hover:bg-bg-elevated text-text-secondary">
          <Bell size={14} />
        </button>
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shadow-sm"
          style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)" }}
        >
          R
        </div>
      </div>
    </header>
  );
}
