// V0.8.2 UX-8: 通知按钮 (替代 TopBar 死按钮)
// 简化版: 拉 /api/insights/today, 显示高严重度未读数 badge
// 完整版可接 WebSocket / 站内通知, 留 V0.8.3+
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, AlertCircle, AlertTriangle, CheckCircle2, X } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";

interface Insight {
  severity: "info" | "warn" | "danger" | "success";
  title: string;
  message: string;
  category?: string;
}

const SEVERITY_STYLES: Record<string, { icon: any; color: string }> = {
  info: { icon: CheckCircle2, color: "text-sky-600" },
  success: { icon: CheckCircle2, color: "text-emerald-600" },
  warn: { icon: AlertTriangle, color: "text-amber-600" },
  danger: { icon: AlertCircle, color: "text-rose-600" },
};

export function NotificationsBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.insightsToday().then((d: any) => {
      const items: Insight[] = [];
      if (d?.insights) items.push(...d.insights);
      else if (Array.isArray(d)) items.push(...d);
      setInsights(items);
    }).catch(() => {});
  }, []);

  // ESC 关闭 + 点外关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const unread = insights.filter((i) => i.severity === "warn" || i.severity === "danger").length;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="p-1.5 rounded hover:bg-bg-elevated text-text-secondary relative"
        title="训练洞察"
        aria-label="通知"
      >
        <Bell size={14} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-80 bg-white border border-border rounded-xl shadow-xl z-50 max-h-[70vh] overflow-y-auto">
          <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
            <div className="text-sm font-semibold text-text-primary">训练洞察</div>
            <button
              onClick={() => {
                setOpen(false);
                navigate("/ai/hrv");
              }}
              className="text-xs text-accent-primary hover:underline"
            >
              查看全部 →
            </button>
          </div>
          {insights.length === 0 ? (
            <div className="p-6 text-center text-sm text-text-muted">
              <CheckCircle2 size={28} className="mx-auto mb-2 text-emerald-500" />
              没有需要关注的洞察
            </div>
          ) : (
            <div className="divide-y divide-border">
              {insights.map((it, i) => {
                const style = SEVERITY_STYLES[it.severity] || SEVERITY_STYLES.info;
                const Icon = style.icon;
                return (
                  <div key={i} className="px-4 py-3 hover:bg-bg-elevated/50 transition-colors">
                    <div className="flex items-start gap-2">
                      <Icon size={16} className={clsx("mt-0.5 flex-shrink-0", style.color)} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-text-primary">{it.title}</div>
                        <div className="text-xs text-text-muted mt-0.5 whitespace-pre-line">
                          {it.message}
                        </div>
                        {it.category && (
                          <div className="text-[10px] text-text-muted mt-1 uppercase tracking-wider">
                            {it.category}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
