// 今日训练状态卡(PMC Today)
// V0.8.3 B3: TP 老钱风 — 状态用左侧 border-l-4 + 浅色背景, 不用霓虹/ring
//   绿=状态好/巅峰, 黄=累积疲劳/平衡, 红=过训, 蓝=减量
import type { PMCToday } from "../lib/types";

interface Props {
  today: PMCToday | null;
  loading?: boolean;
}

// V0.8.3 B3: 浅色主题下的状态色, 用 bg-status-* (淡) + border-l-4 (深)
const STATUS_MAP: Record<string, {
  bg: string;
  border: string;
  text: string;
  emoji: string;
  label: string;
}> = {
  green: {
    bg: "bg-status-success",
    border: "border-l-success",
    text: "text-accent-success",
    emoji: "✨",
    label: "巅峰状态",
  },
  yellow: {
    bg: "bg-status-warning",
    border: "border-l-warning",
    text: "text-accent-warning",
    emoji: "⚖️",
    label: "累积疲劳",
  },
  red: {
    bg: "bg-status-danger",
    border: "border-l-danger",
    text: "text-accent-danger",
    emoji: "🔴",
    label: "过训警告",
  },
  blue: {
    bg: "bg-status-info",
    border: "border-l-info",
    text: "text-text-secondary",
    emoji: "🧊",
    label: "减量恢复",
  },
};

export function PMCStatusCard({ today, loading }: Props) {
  if (loading) {
    return (
      <div className="metric-card border-l-4 border-l-text-muted animate-pulse">
        <div className="h-4 w-24 bg-bg-subtle rounded mb-3" />
        <div className="h-8 w-32 bg-bg-subtle rounded" />
      </div>
    );
  }

  if (!today) {
    return (
      <div className="metric-card border-l-4 border-l-text-muted">
        <div className="text-text-muted text-sm">暂无 PMC 数据</div>
      </div>
    );
  }

  const status = STATUS_MAP[today.status_color] || STATUS_MAP.yellow;
  const tsbStr = (today.tsb >= 0 ? "+" : "") + today.tsb.toFixed(1);
  const rampStr =
    (today.ramp_rate >= 0 ? "+" : "") + today.ramp_rate.toFixed(2);

  return (
    <div className={`metric-card border-l-4 ${status.border} ${status.bg}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-text-secondary text-xs uppercase tracking-wider font-semibold">
          今日训练状态 · PMC
        </div>
        <div className="text-2xl">{status.emoji}</div>
      </div>

      <div className="flex items-baseline gap-2 mb-3">
        <div className={`text-4xl font-bold tabular-nums font-mono ${status.text}`}>
          {tsbStr}
        </div>
        <div className="text-text-muted text-sm font-medium">TSB</div>
      </div>

      <div className={`text-base font-medium ${status.text} mb-4`}>
        {today.status_label || status.label}
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <Stat label="CTL" value={today.ctl.toFixed(1)} hint="42d EWMA" />
        <Stat label="ATL" value={today.atl.toFixed(1)} hint="7d EWMA" />
        <Stat label="趋势" value={rampStr} hint="TSS/wk" />
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="bg-white border border-border rounded px-2 py-1.5">
      <div className="text-text-muted text-[10px] uppercase tracking-wide">{label}</div>
      <div className="text-text-primary font-semibold tabular-nums font-mono">{value}</div>
      <div className="text-text-muted text-[10px]">{hint}</div>
    </div>
  );
}