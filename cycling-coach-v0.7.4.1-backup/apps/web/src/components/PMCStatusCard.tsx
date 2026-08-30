// 今日训练状态卡(PMC Today)
// 颜色映射:绿=状态好/巅峰,黄=累积疲劳/平衡,红=过训,蓝=减量
import type { PMCToday } from "../lib/types";

interface Props {
  today: PMCToday | null;
  loading?: boolean;
}

const COLOR_MAP: Record<string, { bg: string; ring: string; text: string; emoji: string }> = {
  green: {
    bg: "bg-emerald-500/10",
    ring: "ring-emerald-500/40",
    text: "text-emerald-300",
    emoji: "✨",
  },
  yellow: {
    bg: "bg-amber-500/10",
    ring: "ring-amber-500/40",
    text: "text-amber-300",
    emoji: "⚖️",
  },
  red: {
    bg: "bg-red-500/15",
    ring: "ring-red-500/50",
    text: "text-red-300",
    emoji: "🔴",
  },
  blue: {
    bg: "bg-sky-500/10",
    ring: "ring-sky-500/40",
    text: "text-sky-300",
    emoji: "🧊",
  },
};

export function PMCStatusCard({ today, loading }: Props) {
  if (loading) {
    return (
      <div className="rounded-2xl bg-bg-elevated p-5 ring-1 ring-white/5 animate-pulse">
        <div className="h-4 w-24 bg-white/10 rounded mb-3" />
        <div className="h-8 w-32 bg-white/10 rounded" />
      </div>
    );
  }

  if (!today) {
    return (
      <div className="rounded-2xl bg-bg-elevated p-5 ring-1 ring-white/5">
        <div className="text-text-muted text-sm">暂无 PMC 数据</div>
      </div>
    );
  }

  const color = COLOR_MAP[today.status_color] || COLOR_MAP.yellow;
  const tsbStr = (today.tsb >= 0 ? "+" : "") + today.tsb.toFixed(1);
  const rampStr =
    (today.ramp_rate >= 0 ? "+" : "") + today.ramp_rate.toFixed(2);

  return (
    <div className={`rounded-2xl ${color.bg} p-5 ring-1 ${color.ring}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-text-muted text-xs uppercase tracking-wider">
          今日训练状态 · PMC
        </div>
        <div className="text-2xl">{color.emoji}</div>
      </div>

      <div className="flex items-baseline gap-2 mb-4">
        <div className={`text-4xl font-bold tabular-nums ${color.text}`}>
          {tsbStr}
        </div>
        <div className="text-text-muted text-sm">TSB</div>
      </div>

      <div className={`text-base font-medium ${color.text} mb-4`}>
        {today.status_label}
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
    <div className="bg-white/5 rounded-lg px-2 py-1.5">
      <div className="text-text-muted text-[10px] uppercase tracking-wide">{label}</div>
      <div className="text-text-primary font-semibold tabular-nums">{value}</div>
      <div className="text-text-muted text-[10px]">{hint}</div>
    </div>
  );
}
