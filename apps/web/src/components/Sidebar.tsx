// 左侧导航栏(TrainingPeaks 风格)
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Bike,
  Upload,
  User,
  Calendar as CalendarIcon,
  Activity as ActivityIcon,
  MessageCircle,
  BookOpen,
  Hammer,
  Library,
  GitCompare,
  TrendingUp,
  Heart,
  Layers,
  NotebookPen,
  Gauge,
  type LucideIcon,
} from "lucide-react";
import { useAppStore, type View } from "../store/useAppStore";
import clsx from "clsx";

const items: Array<{ view: View; label: string; icon: LucideIcon }> = [
  { view: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { view: "calendar", label: "日历", icon: CalendarIcon },
  { view: "library", label: "课程库", icon: BookOpen },
  { view: "builder", label: "课程编排", icon: Hammer },
  { view: "kb", label: "知识库", icon: Library },
  { view: "activities", label: "训练", icon: Bike },
  { view: "compare", label: "对比", icon: GitCompare },
  { view: "trends", label: "趋势", icon: TrendingUp },
  { view: "insights", label: "训练洞察", icon: Heart },
  { view: "phases", label: "周期化", icon: Layers },
  { view: "diary", label: "训练日记", icon: NotebookPen },
  { view: "ftp-test", label: "FTP 测试", icon: Gauge },
  { view: "chat", label: "AI 教练", icon: MessageCircle },
  { view: "import", label: "导入", icon: Upload },
  { view: "profile", label: "个人画像", icon: User },
];

export function Sidebar() {
  const view = useAppStore((s) => s.view);
  const setView = useAppStore((s) => s.setView);

  return (
    <aside className="w-56 bg-bg-base border-r border-border flex flex-col h-full">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shadow-sm"
            style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)" }}
          >
            <ActivityIcon size={18} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-text-primary leading-none">Cycling Coach</div>
            <div className="text-xs text-text-muted mt-0.5">
              <VersionTag />
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.view}
              className={clsx("nav-link", view === item.view && "active")}
              onClick={() => setView(item.view)}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border">
        <div className="text-xs text-text-muted">数据不离开电脑</div>
        <div className="text-xs text-text-muted mt-0.5">本地优先 · 离线可用</div>
      </div>
    </aside>
  );
}

// V0.7.1: 版本号从后端 SSOT 拿, 避免前端硬编码
function VersionTag() {
  const [v, setV] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/version")
      .then((r) => r.json())
      .then((d) => setV(d.version))
      .catch(() => setV("?.?.?"));
  }, []);
  return <span>v{v ?? "..."}</span>;
}
