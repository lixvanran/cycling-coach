// HRV (心率变异性) 趋势卡 — V0.7.2 新加
// 借鉴 Plews 2013, Bellenger 2016, Buchheit 2014

import { useEffect, useState } from "react";
import { Activity, Heart, Moon, TrendingDown, TrendingUp, Minus } from "lucide-react";

interface HRVState {
  today_hrv: number | null;
  rolling_7d_avg: number | null;
  baseline_30d: number | null;
  delta_from_baseline: number | null;
  delta_pct: number | null;
  consecutive_low_days: number;
  status: "ok" | "caution" | "warning" | "insufficient_data";
  status_label: string;
  recommendation: string;
  series: Array<{ date: string; hrv_ms: number; sleep_h: number | null }>;
}

const STATUS_STYLE: Record<string, { bg: string; text: string; border: string; icon: any }> = {
  ok: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", icon: TrendingUp },
  caution: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", icon: TrendingDown },
  warning: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200", icon: TrendingDown },
  insufficient_data: { bg: "bg-slate-50", text: "text-slate-600", border: "border-slate-200", icon: Minus },
};

export function HRVCard() {
  const [data, setData] = useState<HRVState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/hrv/state")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        HRV 加载中…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        无 HRV 数据
      </div>
    );
  }

  const style = STATUS_STYLE[data.status] || STATUS_STYLE.insufficient_data;
  const Icon = style.icon;

  return (
    <div className={`rounded-2xl border ${style.border} ${style.bg} p-4`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <Heart className={`w-4 h-4 ${style.text}`} />
          <span className="text-sm font-semibold text-slate-700">HRV 趋势 (RMSSD)</span>
          <span className="text-[10px] text-slate-500 ml-1">Plews 2013 · Bellenger 2016</span>
        </div>
        {data.today_hrv !== null && (
          <div className="text-right">
            <div className={`text-2xl font-bold font-mono ${style.text}`}>
              {data.today_hrv.toFixed(0)}
              <span className="text-xs ml-0.5">ms</span>
            </div>
            <div className="text-[10px] text-slate-500">今日</div>
          </div>
        )}
      </div>

      {data.status === "insufficient_data" ? (
        <div className="text-xs text-slate-600 mt-2">{data.recommendation}</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-xs my-3">
            <div className="bg-white/60 rounded p-2">
              <div className="text-[10px] text-slate-500">7d 滑动</div>
              <div className="font-mono font-semibold">{data.rolling_7d_avg?.toFixed(1)} ms</div>
            </div>
            <div className="bg-white/60 rounded p-2">
              <div className="text-[10px] text-slate-500">30d baseline</div>
              <div className="font-mono font-semibold">{data.baseline_30d?.toFixed(1)} ms</div>
            </div>
            <div className="bg-white/60 rounded p-2">
              <div className="text-[10px] text-slate-500">Delta</div>
              <div className={`font-mono font-semibold ${(data.delta_from_baseline ?? 0) < -10 ? "text-rose-600" : (data.delta_from_baseline ?? 0) > 10 ? "text-emerald-600" : "text-slate-700"}`}>
                {data.delta_from_baseline! > 0 ? "+" : ""}{data.delta_from_baseline?.toFixed(1)} ({data.delta_pct?.toFixed(0)}%)
              </div>
            </div>
          </div>

          {/* HRV 趋势 sparkline */}
          {data.series.length > 0 && (
            <HRVSparkline series={data.series} baseline={data.baseline_30d ?? 60} />
          )}

          <div className="flex items-start gap-2 mt-3 pt-2 border-t border-slate-200/60">
            <Icon className={`w-3.5 h-3.5 mt-0.5 ${style.text}`} />
            <div>
              <div className={`text-xs font-medium ${style.text}`}>
                {data.status_label}
                {data.consecutive_low_days >= 2 && ` · 连续 ${data.consecutive_low_days} 天`}
              </div>
              <div className="text-[11px] text-slate-600 mt-0.5 leading-relaxed">
                {data.recommendation}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function HRVSparkline({ series, baseline }: { series: Array<{ date: string; hrv_ms: number; sleep_h: number | null }>; baseline: number }) {
  const W = 280;
  const H = 60;
  if (series.length < 2) return null;

  const ys = series.map((d) => d.hrv_ms);
  const yMin = Math.min(...ys, baseline) - 5;
  const yMax = Math.max(...ys, baseline) + 5;
  const xStep = W / (series.length - 1);

  const points = series.map((d, i) => ({
    x: i * xStep,
    y: H - ((d.hrv_ms - yMin) / (yMax - yMin)) * H,
    v: d.hrv_ms,
  }));

  const baselineY = H - ((baseline - yMin) / (yMax - yMin)) * H;

  const pathD = points.map((p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`)).join(" ");
  const areaD = `${pathD} L ${(series.length - 1) * xStep} ${H} L 0 ${H} Z`;

  return (
    <div className="bg-white/60 rounded p-1">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-12">
        <defs>
          <linearGradient id="hrvGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#6366f1" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        {/* baseline 参考线 */}
        <line
          x1="0"
          y1={baselineY}
          x2={W}
          y2={baselineY}
          stroke="#94a3b8"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <path d={areaD} fill="url(#hrvGrad)" />
        <path d={pathD} fill="none" stroke="#6366f1" strokeWidth="1.5" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={2} fill="#6366f1" />
        ))}
      </svg>
      <div className="flex items-center justify-between text-[9px] text-slate-500 mt-0.5">
        <span>{series[0]?.date.slice(5)}</span>
        <span className="text-slate-400">— 30d baseline —</span>
        <span>{series[series.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  );
}
