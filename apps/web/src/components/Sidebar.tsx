// 左侧导航栏 (TrainingPeaks 风格) — V0.8.2
// 改动:
//   U-6 标签清晰化: "训练洞察" → "HRV / 训练健康", "FTP 测试" → "FTP 校准"
//   U-7 分组: 5 大类 (训练 / AI 教练 / 计划 / 数据 / 设置), 视觉分组
//   U-17 占位: 底部预留"最近活动"入口
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
  Activity as _ActivityIcon,
  MessageCircle,
  BookOpen,
  Hammer,
  Library,
  TrendingUp,
  Heart,
  Layers,
  NotebookPen,
  Gauge,
  type LucideIcon, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import clsx from "clsx";

interface NavItem {
  to: string;             // 路径
  label: string;
  icon: LucideIcon;
}

// V0.8.2: 分 5 组 (训练 / AI 教练 / 计划 / 数据 / 设置)
const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "训练",
    items: [
      { to: "/training", label: "Dashboard", icon: LayoutDashboard },
      { to: "/training/activities", label: "训练", icon: Bike },
      { to: "/training/trends", label: "趋势", icon: TrendingUp },
      { to: "/training/diary", label: "训练日记", icon: NotebookPen },
    ],
  },
  {
    title: "AI 教练",
    items: [
      { to: "/ai/chat", label: "AI 教练", icon: MessageCircle },
      { to: "/ai/race-tactics", label: "比赛战术", icon: Trophy },
      { to: "/ai/hrv", label: "HRV / 训练健康", icon: Heart },
    ],
  },
  {
    title: "计划",
    items: [
      { to: "/plan", label: "计划", icon: Hammer },
      { to: "/plan/calendar", label: "日历", icon: CalendarIcon },
      { to: "/plan/workouts", label: "课程库", icon: BookOpen },
      { to: "/plan/phases", label: "周期化", icon: Layers },
    ],
  },
  {
    title: "数据",
    items: [
      { to: "/data/import", label: "导入", icon: Upload },
      { to: "/data/knowledge", label: "知识库", icon: Library },
      { to: "/data/ftp-test", label: "FTP 校准", icon: Gauge },
      { to: "/data/trust", label: "数据可信度", icon: ShieldCheck },
    ],
  },
  {
    title: "设置",
    items: [
      { to: "/settings", label: "个人画像", icon: User },
    ],
  },
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
          {/* V0.8.3 B3: Logo 去渐变 → 纯蓝底 + monogram "CC" (TP 老钱风) */}
          <div
            className="w-9 h-9 rounded flex items-center justify-center bg-accent-primary text-white font-bold text-sm tracking-tight"
          >
            CC
          </div>
          <div>
            <div className="text-sm font-semibold text-text-primary leading-none">Cycling Coach</div>
            <div className="text-xs text-text-muted mt-0.5">
              <VersionTag />
            </div>
          </div>
        </div>
      </div>

      {/* Nav (分组) */}
      <nav className="flex-1 px-2 py-3 space-y-3 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <div className="px-3 mb-1 text-[10px] font-semibold text-text-muted uppercase tracking-wider">
              {group.title}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isKb = item.to === "/data/knowledge";
                return (
                  <div
                    key={item.to}
                    className={clsx("relative", isKb && "group")}
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
                        className="absolute left-full top-0 ml-1 w-56 bg-white border-2 border-border rounded shadow-sm z-50 py-1.5"
                        onMouseEnter={() => setKbHover(true)}
                        onMouseLeave={() => setKbHover(false)}
                      >
                        <div className="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wider">
                          知识库分类
                        </div>
                        <button
                          onClick={() => navigate("/data/knowledge")}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-bg-subtle transition-colors"
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
                            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-bg-subtle hover:text-accent transition-colors group/cat"
                          >
                            <span className="text-text-primary group-hover/cat:text-accent font-medium flex-1 truncate">
                              {cat.name}
                            </span>
                            <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-bold tabular-nums",
                              cat.doc_count > 50 ? "bg-status-info text-accent-primary" :
                              cat.doc_count > 20 ? "bg-status-warning text-accent-warning" :
                              cat.doc_count > 5 ? "bg-status-info text-accent-primary" :
                              "bg-bg-subtle text-text-muted"
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
            </div>
          </div>
        ))}
      </nav>

      {/* 底部: 状态条 (V0.8.2 U-5: Mock 模式 indicator 从顶栏移到这里) */}
      <SidebarStatus />
    </aside>
  );
}

// 状态条 (Mock 模式 / 数据版本)
function SidebarStatus() {
  const [mock, setMock] = useState<boolean | null>(null);
  useEffect(() => {
    api.diagnose().then((d) => setMock(d.m3_mock_mode)).catch(() => {});
  }, []);
  if (mock === null) return null;
  return (
    <div className="px-4 py-2 border-t border-border">
      <div className="text-[10px] text-text-muted flex items-center gap-1.5">
        <span className={clsx("w-1.5 h-1.5 rounded-full", mock ? "bg-accent-warning" : "bg-status-success")} />
        {mock ? "Mock 模式 (未配 API key)" : "AI 在线"}
      </div>
    </div>
  );
}

// 版本号 (V0.7.1 SSOT)
function VersionTag() {
  const [v, setV] = useState<string>("");
  useEffect(() => {
    api.version().then((r: any) => setV(r.version || "")).catch(() => {});
  }, []);
  return <span>{v ? `v${v}` : "v..."}</span>;
}
