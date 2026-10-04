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
import { renderDimension, READINESS_DIMENSIONS } from "../lib/readinessDisplay";
import clsx from "clsx";

interface Recommendation {
  // V0.9.0: 补 "info"。后端 recommendations.py 的 _insufficient_data_recommendation
  // 会用 category="info" 发"还不能算今日状态 / 还没有任何训练数据"这类引导。
  // 类型里漏了它, 于是组件里 `r.category === "info"` 被 tsc 判成永假分支 ——
  // 那些引导会落进 else, 用**警告色 + 警告图标**渲染。
  // 用户看到的却是"还没有任何训练数据"配一圈琥珀色警告条, 很像出了故障。
  category: "workout" | "warning" | "tip" | "lifestyle" | "info";
  priority: number;
  title: string;
  detail: string;
  action?: string;
  icon?: string;
}

interface DailyRecommendation {
  date: string;
  readiness_score: number | null; // V0.9.0: null = 数据不足算不出 (不是 0)
  readiness_label: string;
  recommended_workout_type: string;
  recommended_intensity: string;
  target_tss: number;
  recommendations: Recommendation[];
  warnings: string[];
  signals_summary: {
    readiness_breakdown: Record<string, number>;
    // V0.9.0: readiness 分数只代表**部分**维度。coverage 用来告诉用户
    // "这个分是基于哪几个维度算的"。没有它, 一个 2/5 维归一化出来的 67 分
    // 和一个五维齐全的 67 分看起来毫无区别 —— 但它们的可信度完全不同。
    readiness_coverage?: {
      available: string[];
      missing: string[];
      available_labels: string[];
      missing_labels: string[];
      n_available: number;
      n_total: number;
      complete: boolean;
    };
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
  vo2: { label: "VO2max", icon: Zap, color: "text-accent-danger bg-status-danger border-border", tssHint: "高强度日" },
  threshold: { label: "Threshold", icon: Target, color: "text-accent-warning bg-status-warning border-border", tssHint: "阈值日" },
  tempo: { label: "Tempo", icon: TrendingUp, color: "text-accent-warning bg-status-warning border-border", tssHint: "节奏日" },
  endurance: { label: "Endurance", icon: Activity, color: "text-accent-success bg-status-success border-border", tssHint: "轻松日" },
  recovery: { label: "Recovery", icon: Coffee, color: "text-accent-primary bg-status-info border-border", tssHint: "恢复日" },
  rest: { label: "Rest", icon: Coffee, color: "text-text-secondary bg-bg-subtle border-border", tssHint: "完全休息" },
};

// V0.9.0: 去掉 ring。5 个条目全都填 "", 而模板里 `${rStyle.ring}` 渲染出来
// 只是个空串 —— 纯装饰。同一轮我在 CalendarPage 写过"编个假值不如删掉",
// 这里就得一致, 不能一边删假值一边留假值。
const READINESS_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  "极佳": { bg: "bg-status-success", text: "text-accent-success", label: "极佳" },
  "良好": { bg: "bg-status-success", text: "text-accent-success", label: "良好" },
  "中等": { bg: "bg-status-warning", text: "text-accent-warning", label: "中等" },
  "低迷": { bg: "bg-status-warning", text: "text-accent-warning", label: "低迷" },
  "危险": { bg: "bg-status-danger", text: "text-accent-danger", label: "危险" },
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
      <div className="rounded border border-border bg-white p-4 text-sm text-text-secondary">
        <Sparkles className="w-4 h-4 inline mr-2 animate-pulse" />
        加载今日建议…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded border border-border bg-white p-4 text-sm text-text-secondary">
        无建议数据
      </div>
    );
  }

  const rStyle = READINESS_STYLE[data.readiness_label] || READINESS_STYLE["中等"];
  const wMeta = WORKOUT_META[data.recommended_workout_type] || WORKOUT_META.endurance;
  const WIcon = wMeta.icon;

  // V0.9.0: readiness_score 为 null = 数据不足, 算不出来。
  // 以前后端无数据时会给 82 分"极佳" + VO2max 高强度建议 ——
  // 新用户还没上传过一次训练就被告知"状态极佳", 纯误导。
  // 现在如实显示"数据不足", 并告诉他要做什么才能算。
  const hasScore = typeof data.readiness_score === "number";
  const cov = data.signals_summary?.readiness_coverage;
  const suff = (data.signals_summary as any)?.data_sufficiency;

  return (
    <div className={`rounded border ${rStyle.bg} p-4`}>
      {/* 顶部: 标题 + Readiness 大数字 */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className={`w-4 h-4 ${rStyle.text}`} />
            <span className="text-sm font-semibold text-text-secondary">今日 AI 教练建议</span>
            <span className="text-[10px] text-text-secondary">{data.date}</span>
          </div>
          <div className="text-[10px] text-text-secondary">
            {hasScore ? "借鉴 TrainingPeaks / WKO5 · 综合 5 维数据" : "数据不足，暂不评估状态"}
          </div>
        </div>
        <div className="text-right">
          {hasScore ? (
            <>
              <div className={`text-4xl font-bold font-mono ${rStyle.text}`}>
                {data.readiness_score}
              </div>
              <div className="text-[10px] text-text-secondary -mt-1">readiness</div>
              <div className={`text-xs font-medium ${rStyle.text}`}>{rStyle.label}</div>
              {/* V0.9.0: 分数只基于部分维度时, 必须写在分数正下方 ——
                  放大了看第一眼就能发现, 而不是要展开详情才知道。 */}
              {cov && !cov.complete && (
                <div className="text-[9px] text-text-secondary mt-0.5">
                  基于 {cov.n_available}/{cov.n_total} 维
                </div>
              )}
            </>
          ) : (
            <>
              <div className="text-2xl font-bold text-text-muted leading-tight">--</div>
              <div className="text-[10px] text-text-secondary -mt-1">readiness</div>
              <div className="text-xs font-medium text-text-muted">数据不足</div>
            </>
          )}
        </div>
      </div>

      {!hasScore && (
        <div className="bg-white/60 rounded p-3 mb-3 text-xs text-text-secondary leading-relaxed">
          <div className="font-medium text-text-primary mb-1">
            {suff?.n_activities === 0
              ? "还没有任何训练数据"
              : "训练数据还不够算状态"}
          </div>
          <div>
            {suff?.reasons?.length
              ? suff.reasons.join("; ")
              : "App 不会在数据不足时猜测你的状态"}
          </div>
          <div className="mt-1 text-text-muted">
            先去「数据 → 导入」上传 FIT 文件
          </div>
        </div>
      )}

      {/* 5 维 breakdown bar — 数据不足时不显示 (全 0 的条形图比不显示更误导) */}
      {hasScore && (
      <div className="bg-white/60 rounded p-2 mb-3">
        <div className="grid grid-cols-5 gap-1 text-[10px]">
          {READINESS_DIMENSIONS.map((d) => {
            const r = renderDimension(d.key, data.signals_summary.readiness_breakdown, d.max);
            return (
              <div
                key={d.key}
                className="text-center"
                title={r.has ? `${r.label}: ${r.scoreText} - ${r.pct.toFixed(0)}%` : `${r.label}: 无数据 — 参与不了本次评分（不是 0 分）。${r.missingHint}`}
              >
                <div className={`font-medium ${r.has ? "text-text-secondary" : "text-text-muted"}`}>
                  {r.label}
                  {!r.has && <div className="text-[9px] font-normal">无数据</div>}
                </div>
                <div className={`font-mono ${r.has ? "text-text-secondary" : "text-text-muted"}`}>
                  {r.scoreText}
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1 mt-0.5">
                  <div className={`${r.barClass} h-1 rounded-full transition-all`} style={{ width: `${r.pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* 推荐训练 — 数据不足时整块不显示 */}
      {hasScore && (
      <div className={`rounded border ${wMeta.color} p-3 mb-3`}>
        <div className="flex items-start gap-2">
          <WIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold">{wMeta.label}</span>
              <span className="text-[10px] text-text-secondary">· {wMeta.tssHint}</span>
              <span className="ml-auto text-[11px] font-mono text-text-secondary">
                目标 TSS ~{data.target_tss}
              </span>
            </div>
            <div className="text-xs text-text-secondary leading-relaxed">
              {data.recommended_intensity}
            </div>
          </div>
        </div>
      </div>
      )}

      {/* 触发建议列表 */}
      {data.recommendations.length > 0 ? (
        <div className="space-y-2">
          <div className="text-[10px] text-text-secondary mb-1">触发建议 · 按优先级</div>
          {data.recommendations.slice(0, 5).map((r, i) => (
            <div
              key={i}
              className={clsx(
                "rounded p-2 text-xs flex items-start gap-2 border border-border",
                r.category === "warning"
                  ? "bg-status-danger"
                  : r.category === "info"
                    ? "bg-bg-subtle"          // V0.9.0: info 类(数据不足提示)不该染成警告色
                    : r.category === "tip"
                      ? "bg-status-success/10"  // V0.9.0: tip 是"好消息"(如 HRV 优秀),
                                                // 落到 else 会渲染成琥珀警告色 —— 看着像在报警
                      : "bg-status-warning"
              )}
            >
              {r.category === "warning" ? (
                <AlertTriangle className="w-3.5 h-3.5 text-accent-danger flex-shrink-0 mt-0.5" />
              ) : r.category === "info" ? (
                <Info className="w-3.5 h-3.5 text-text-secondary flex-shrink-0 mt-0.5" />
              ) : r.category === "tip" ? (
                <Lightbulb className="w-3.5 h-3.5 text-accent-success flex-shrink-0 mt-0.5" />
              ) : (
                <Lightbulb className="w-3.5 h-3.5 text-accent-warning flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="flex items-center gap-1">
                  <span className="font-medium text-text-primary">
                    {r.icon && <span className="mr-1">{r.icon}</span>}
                    {r.title}
                  </span>
                  <span className="ml-auto text-[9px] text-text-secondary">P{r.priority}</span>
                </div>
                <div className="text-[11px] text-text-secondary leading-relaxed mt-0.5">
                  {r.detail}
                </div>
                {r.action && (
                  <div className="text-[11px] font-medium text-text-secondary mt-1 flex items-start gap-1">
                    <ChevronRight className="w-3 h-3 mt-0.5 flex-shrink-0" />
                    <span>{r.action}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-text-secondary italic text-center py-2">
          ✨ 一切指标正常, 按计划训练
        </div>
      )}
    </div>
  );
}
