// 周期化阶段信号卡 — V0.7.2 新加
// 借鉴 Seiler 2010, Friel CTB, Jeukendrup 2018

import { useEffect, useState } from "react";
import { Gauge, Calendar, Flame, Minus, TrendingUp, AlertTriangle, Lightbulb } from "lucide-react";

interface PhaseSignals {
  avg_if_28d: number;
  freq_7d: number;
  streak_days: number;
  weeks_since_taper: number;
  polarized_score_28d: number;
  load_achievement_7d: number;
  warnings: string[];
  hints: string[];
}

const META: Array<{
  key: keyof PhaseSignals;
  label: string;
  unit?: string;
  good: (v: number) => boolean;
  ideal: string;
  format: (v: number) => string;
  icon: any;
}> = [
  {
    key: "avg_if_28d",
    label: "28d 平均 IF",
    good: (v) => v >= 0.7 && v <= 0.85,
    ideal: "0.70-0.85 (endurance / tempo)",
    format: (v) => v.toFixed(2),
    icon: Gauge,
  },
  {
    key: "freq_7d",
    label: "7d 训练频率",
    good: (v) => v >= 0.57 && v <= 0.71,
    ideal: "0.57-0.71 (4-5 天/周)",
    format: (v) => `${(v * 7).toFixed(1)} 天`,
    icon: Calendar,
  },
  {
    key: "streak_days",
    label: "连续训练",
    good: (v) => v <= 5,
    ideal: "≤ 5 天 (建议 1-2 休)",
    format: (v) => `${v} 天`,
    icon: Flame,
  },
  {
    key: "weeks_since_taper",
    label: "距上次减量",
    good: (v) => v <= 8,
    ideal: "≤ 8 周 (8-12 周应减量)",
    format: (v) => `${v} 周`,
    icon: Minus,
  },
  {
    key: "polarized_score_28d",
    label: "极化评分",
    good: (v) => v >= 0.6,
    ideal: "≥ 0.6 (Seiler 80/20)",
    format: (v) => v.toFixed(2),
    icon: TrendingUp,
  },
  {
    key: "load_achievement_7d",
    label: "7d 负荷达成",
    good: (v) => v >= 0.8 && v <= 1.2,
    ideal: "0.8-1.2 (80%-120%)",
    format: (v) => `${(v * 100).toFixed(0)}%`,
    icon: Gauge,
  },
];

export function PhaseSignalsCard() {
  const [data, setData] = useState<PhaseSignals | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/phases/signals")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        信号加载中…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        无信号数据
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-indigo-600" />
          <span className="text-sm font-semibold text-slate-700">周期化信号 (28d / 7d)</span>
        </div>
        <span className="text-[10px] text-slate-500">Seiler 2010 · Friel CTB</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {META.map((m) => {
          const v = data[m.key] as number;
          const ok = m.good(v);
          const Icon = m.icon;
          return (
            <div
              key={m.key}
              className={`rounded p-2 ${ok ? "bg-emerald-50 border border-emerald-200" : "bg-amber-50 border border-amber-200"}`}
              title={`理想: ${m.ideal}`}
            >
              <div className="flex items-center justify-between text-[10px] text-slate-500">
                <span className="flex items-center gap-1">
                  <Icon className="w-3 h-3" />
                  {m.label}
                </span>
                <span>{ok ? "✓" : "⚠"}</span>
              </div>
              <div className={`text-lg font-mono font-bold ${ok ? "text-emerald-700" : "text-amber-700"}`}>
                {m.format(v)}
              </div>
              <div className="text-[9px] text-slate-500 mt-0.5">{m.ideal}</div>
            </div>
          );
        })}
      </div>

      {(data.warnings.length > 0 || data.hints.length > 0) && (
        <div className="mt-3 pt-3 border-t border-slate-200 space-y-1.5">
          {data.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-rose-700">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{w}</span>
            </div>
          ))}
          {data.hints.map((h, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-amber-700">
              <Lightbulb className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{h}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
