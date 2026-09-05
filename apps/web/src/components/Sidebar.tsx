// 左侧导航栏(TrainingPeaks 风格) — V0.8.0 URL 路由版
import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Trophy,
  ChevronRight,
  Bike,
  Upload,
  User,
  Calendar as CalendarIcon,
  Activity as ActivityIcon,
  MessageCircle,
  BookOpen,
  Hammer,
  Library,
  TrendingUp,
  Heart,
  Layers,
  NotebookPen,
  Gauge,
  type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import clsx from "clsx";

// V0.8.0 路由版 — 每项 = 路径前缀, 用于 NavLink active 判断
interface NavItem {
  to: string;             // 路径
  label: string;
  icon: LucideIcon;
}

const items: NavItem[] = [
  { to: "/training", label: "Dashboard", icon: LayoutDashboard },
  { to: "/training/activities", label: "训练", icon: Bike },
  { to: "/training/trends", label: "趋势", icon: TrendingUp },
  { to: "/training/diary", label: "训练日记", icon: NotebookPen },
  { to: "/ai/chat", label: "AI 教练", icon: MessageCircle },
  { to: "/ai/race-tactics", label: "比赛战术", icon: Trophy },
  { to: "/ai/hrv", label: "训练洞察", icon: Heart },
  { to: "/plan", label: "计划", icon: Hammer },
  { to: "/plan/calendar", label: "日历", icon: CalendarIcon },
  { to: "/plan/workouts", label: "课程库", icon: BookOpen },
  { to: "/plan/phases", label: "周期化", icon: Layers },
  { to: "/data/import", label: "导入", icon: Upload },
  { to: "/data/knowledge", label: "知识库", icon: Library },
  { to: "/data/ftp-test", label: "FTP 测试", icon: Gauge },
  { to: "/settings", label: "个人画像", icon: User },
];

export function Sidebar() {
  const navigate = useNavigate();
  // V0.7.5.1: KB 二级菜单 hover 状态 + 顶级分类
  const [kbHover, setKbHover] = useState(false);
  const [kbCats, setKbCats] = useState<{ name: string; path: string; doc_count: number }[]>([]);
  useEffect(() => {
    api.kbCategories().then((r) => {
      const tops = (r.categories || [])
        .filter((c: any) => c.path.split("/").length === 1)
        .map((c: any) => ({ name: c.name, path: c.path, doc_count: c.doc_count || 0 }));
      setKbCats(tops);
    }).catch(() => {});
  }, []);

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
          const isKb = item.to === "/data/knowledge";
          return (
            <div
              key={item.to}
              className={clsx(
                "relative",
                isKb && "group"
              )}
              onMouseEnter={() => isKb && setKbHover(true)}
              onMouseLeave={() => isKb && setKbHover(false)}
            >
              <NavLink
                to={item.to}
                end={item.to === "/training" || item.to === "/plan" || item.to === "/settings" || item.to === "/ai/chat"}
                className={({ isActive }) =>
                  clsx("nav-link", isActive && "active")
                }
              >
                <Icon size={16} />
                <span className="flex-1">{item.label}</span>
                {isKb && <ChevronRight size={12} className="opacity-50" />}
              </NavLink>
              {/* V0.7.5.1: KB hover 二级菜单 — 8 个顶级分类 */}
              {isKb && kbHover && kbCats.length > 0 && (
                <div
                  className="absolute left-full top-0 ml-1 w-56 bg-white border-2 border-border rounded-lg shadow-xl z-50 py-1.5"
                  onMouseEnter={() => setKbHover(true)}
                  onMouseLeave={() => setKbHover(false)}
                >
                  <div className="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wider">
                    知识库分类
                  </div>
                  <button
                    onClick={() => navigate("/data/knowledge")}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-bg-elevated transition-colors"
                  >
                    <span className="text-text-primary font-medium flex-1">📚 全部</span>
                    <span className="text-[10px] text-text-muted tabular-nums">
                      {kbCats.reduce((s, c) => s + c.doc_count, 0)}
                    </span>
                  </button>
                  <div className="border-t border-border my-1" />
                  {kbCats.map((cat) => (
                    <button
                      key={cat.path}
                      onClick={() => navigate(`/data/knowledge?category=${encodeURIComponent(cat.path)}`)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-bg-elevated hover:text-accent transition-colors group/cat"
                    >
                      <span className="text-text-primary group-hover/cat:text-accent font-medium flex-1 truncate">
                        {cat.name}
                      </span>
                      <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-bold tabular-nums",
                        cat.doc_count > 50 ? "bg-fuchsia-100 text-fuchsia-700" :
                        cat.doc_count > 20 ? "bg-amber-100 text-amber-700" :
                        cat.doc_count > 5 ? "bg-sky-100 text-sky-700" :
                        "bg-bg-input text-text-muted"
                      )}>
                        {cat.doc_count}
                      </span>
                    </button>
                  ))}
                </div>
              )}
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
