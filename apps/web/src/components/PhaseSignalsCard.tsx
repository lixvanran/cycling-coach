// 周期化阶段信号卡 — V0.7.2 新加
// 借鉴 Seiler 2010, Friel CTB, Jeukendrup 2018

import { useEffect, useState } from "react";
import { Gauge, Calendar, Flame, Minus, TrendingUp, AlertTriangle, Lightbulb } from "lucide-react";

interface PhaseSignals {
  // 🔴 V0.9.0-06: 这几个字段算不出来时是 **null**, 不是 0。
  // 0 看起来像真实测量值 —— 界面会拿 0.00 去对照"理想 0.70-0.85"
  // 判成红色警告, 甚至生成"增加 Z1-Z2 比例"这种凭空来的训练处方。
  //
  // streak_days / weeks_since_taper 保持 number: 对零数据用户来说
  // "0 天连续训练"是**真的**(他确实一天没练), 那个 0 是诚实的。
  data_sufficient?: boolean;
  avg_if_28d: number | null;
  freq_7d: number | null;
  streak_days: number;
  weeks_since_taper: number;
  polarized_score_28d: number | null;
  load_achievement_7d: number | null;
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
      <div className="rounded border border-border bg-white p-4 text-sm text-text-secondary">
        信号加载中…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded border border-border bg-white p-4 text-sm text-text-secondary">
        无信号数据
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-accent-primary" />
          <span className="text-sm font-semibold text-text-secondary">周期化信号 (28d / 7d)</span>
        </div>
        <span className="text-[10px] text-text-secondary">Seiler 2010 · Friel CTB</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {META.map((m) => {
          const raw = data[m.key] as number | null;
          // ⚠️ V0.9.0-06: 算不出来时不能判"好/坏"。
          // 以前这里 raw 是 0, `good(0)` 返回 false → 黄色警告 + "0.00",
          // 让零数据用户以为自己的极化/IF 不达标。
          const v = raw as number;
          const known = raw !== null && raw !== undefined;
          const ok = known ? m.good(v) : null;
          const Icon = m.icon;
          return (
            <div
              key={m.key}
              className={`rounded p-2 border border-border ${
                ok === null ? "bg-white" : ok ? "bg-status-success" : "bg-status-warning"
              }`}
              title={`理想: ${m.ideal}`}
            >
              <div className="flex items-center justify-between text-[10px] text-text-secondary">
                <span className="flex items-center gap-1">
                  <Icon className="w-3 h-3" />
                  {m.label}
                </span>
                {/* 缺失时不给 ✓/⚠ —— 那是对"没有数据"的评价, 不是对人的 */}
                <span>{ok === null ? "—" : ok ? "✓" : "⚠"}</span>
              </div>
              <div
                className={`text-lg font-mono font-bold ${
                  ok === null ? "text-text-muted" : ok ? "text-accent-success" : "text-accent-warning"
                }`}
              >
                {known ? m.format(v) : "无数据"}
              </div>
              <div className="text-[9px] text-text-secondary mt-0.5">{m.ideal}</div>
            </div>
          );
        })}
      </div>

      {(data.warnings.length > 0 || data.hints.length > 0) && (
        <div className="mt-3 pt-3 border-t border-border space-y-1.5">
          {data.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-accent-danger">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{w}</span>
            </div>
          ))}
          {data.hints.map((h, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-accent-warning">
              <Lightbulb className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{h}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
