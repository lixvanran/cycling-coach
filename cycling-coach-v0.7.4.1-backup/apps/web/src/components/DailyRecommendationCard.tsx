// V0.7.3: 每日 AI 训练建议卡
// 借鉴 TrainingPeaks "Daily Workout" + WKO5 "Readiness"

import { useEffect, useState } from "react";
import {
  Sparkles,
  AlertTriangle,
  Info,
  Lightbulb,
  Activity,
  TrendingUp,
  TrendingDown,
  Zap,
  Target,
  Coffee,
  ChevronRight,
} from "lucide-react";
import clsx from "clsx";

interface Recommendation {
  category: "workout" | "warning" | "tip" | "lifestyle";
  priority: number;
  title: string;
  detail: string;
  action?: string;
  icon?: string;
}

interface DailyRecommendation {
  date: string;
  readiness_score: number;
  readiness_label: string;
  recommended_workout_type: string;
  recommended_intensity: string;
  target_tss: number;
  recommendations: Recommendation[];
  warnings: string[];
  signals_summary: {
    readiness_breakdown: Record<string, number>;
    tsb: number;
    ctl: number;
    atl: number;
    hrv_status: string;
    hrv_today?: number;
    phase: string;
    phase_label: string;
    weeks_to_race?: number;
  };
}

const WORKOUT_META: Record<string, { label: string; icon: any; color: string; tssHint: string }> = {
  vo2: { label: "VO2max", icon: Zap, color: "text-rose-600 bg-rose-50 border-rose-200", tssHint: "高强度日" },
  threshold: { label: "Threshold", icon: Target, color: "text-orange-600 bg-orange-50 border-orange-200", tssHint: "阈值日" },
  tempo: { label: "Tempo", icon: TrendingUp, color: "text-amber-600 bg-amber-50 border-amber-200", tssHint: "节奏日" },
  endurance: { label: "Endurance", icon: Activity, color: "text-emerald-600 bg-emerald-50 border-emerald-200", tssHint: "轻松日" },
  recovery: { label: "Recovery", icon: Coffee, color: "text-blue-600 bg-blue-50 border-blue-200", tssHint: "恢复日" },
  rest: { label: "Rest", icon: Coffee, color: "text-slate-600 bg-slate-50 border-slate-200", tssHint: "完全休息" },
};

const READINESS_STYLE: Record<string, { bg: string; text: string; ring: string; label: string }> = {
  "极佳": { bg: "bg-emerald-50", text: "text-emerald-700", ring: "ring-emerald-200", label: "极佳" },
  "良好": { bg: "bg-green-50", text: "text-green-700", ring: "ring-green-200", label: "良好" },
  "中等": { bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-200", label: "中等" },
  "低迷": { bg: "bg-orange-50", text: "text-orange-700", ring: "ring-orange-200", label: "低迷" },
  "危险": { bg: "bg-rose-50", text: "text-rose-700", ring: "ring-rose-200", label: "危险" },
};

const BREAKDOWN_META: Array<{ key: string; label: string; max: number; desc: string }> = [
  { key: "hrv", label: "HRV", max: 30, desc: "心率变异性" },
  { key: "acwr", label: "ACWR", max: 25, desc: "急慢性负荷比" },
  { key: "tsb", label: "TSB", max: 20, desc: "训练平衡" },
  { key: "phase", label: "阶段", max: 15, desc: "周期化适配" },
  { key: "rpe", label: "RPE", max: 10, desc: "主观疲劳 7d" },
];

export function DailyRecommendationCard() {
  const [data, setData] = useState<DailyRecommendation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/recommendations/today")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        <Sparkles className="w-4 h-4 inline mr-2 animate-pulse" />
        加载今日建议…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        无建议数据
      </div>
    );
  }

  const rStyle = READINESS_STYLE[data.readiness_label] || READINESS_STYLE["中等"];
  const wMeta = WORKOUT_META[data.recommended_workout_type] || WORKOUT_META.endurance;
  const WIcon = wMeta.icon;

  return (
    <div className={`rounded-2xl border ${rStyle.ring} ${rStyle.bg} p-4`}>
      {/* 顶部: 标题 + Readiness 大数字 */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className={`w-4 h-4 ${rStyle.text}`} />
            <span className="text-sm font-semibold text-slate-700">今日 AI 教练建议</span>
            <span className="text-[10px] text-slate-500">{data.date}</span>
          </div>
          <div className="text-[10px] text-slate-500">借鉴 TrainingPeaks / WKO5 · 综合 5 维数据</div>
        </div>
        <div className="text-right">
          <div className={`text-4xl font-bold font-mono ${rStyle.text}`}>
            {data.readiness_score}
          </div>
          <div className="text-[10px] text-slate-500 -mt-1">readiness</div>
          <div className={`text-xs font-medium ${rStyle.text}`}>{rStyle.label}</div>
        </div>
      </div>

      {/* 5 维 breakdown bar */}
      <div className="bg-white/60 rounded-lg p-2 mb-3">
        <div className="grid grid-cols-5 gap-1 text-[10px]">
          {BREAKDOWN_META.map((m) => {
            const v = data.signals_summary.readiness_breakdown?.[m.key] || 0;
            const pct = (v / m.max) * 100;
            const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-rose-500";
            return (
              <div key={m.key} className="text-center" title={`${m.label}: ${v}/${m.max} - ${m.desc}`}>
                <div className="font-medium text-slate-600">{m.label}</div>
                <div className="font-mono text-slate-700">{v}/{m.max}</div>
                <div className="w-full bg-slate-200 rounded-full h-1 mt-0.5">
                  <div className={`${color} h-1 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 推荐训练 */}
      <div className={`rounded-lg border ${wMeta.color} p-3 mb-3`}>
        <div className="flex items-start gap-2">
          <WIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold">{wMeta.label}</span>
              <span className="text-[10px] text-slate-600">· {wMeta.tssHint}</span>
              <span className="ml-auto text-[11px] font-mono text-slate-700">
                目标 TSS ~{data.target_tss}
              </span>
            </div>
            <div className="text-xs text-slate-700 leading-relaxed">
              {data.recommended_intensity}
            </div>
          </div>
        </div>
      </div>

      {/* 触发建议列表 */}
      {data.recommendations.length > 0 ? (
        <div className="space-y-2">
          <div className="text-[10px] text-slate-500 mb-1">触发建议 · 按优先级</div>
          {data.recommendations.slice(0, 5).map((r, i) => (
            <div
              key={i}
              className={clsx(
                "rounded-lg p-2 text-xs flex items-start gap-2",
                r.category === "warning"
                  ? "bg-rose-50 border border-rose-200"
                  : "bg-amber-50 border border-amber-200"
              )}
            >
              {r.category === "warning" ? (
                <AlertTriangle className="w-3.5 h-3.5 text-rose-600 flex-shrink-0 mt-0.5" />
              ) : (
                <Lightbulb className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="flex items-center gap-1">
                  <span className="font-medium text-slate-800">
                    {r.icon && <span className="mr-1">{r.icon}</span>}
                    {r.title}
                  </span>
                  <span className="ml-auto text-[9px] text-slate-500">P{r.priority}</span>
                </div>
                <div className="text-[11px] text-slate-600 leading-relaxed mt-0.5">
                  {r.detail}
                </div>
                {r.action && (
                  <div className="text-[11px] font-medium text-slate-700 mt-1 flex items-start gap-1">
                    <ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />
                    <span>{r.action}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-slate-500 italic text-center py-2">
          ✨ 一切指标正常, 按计划训练
        </div>
      )}
    </div>
  );
}
