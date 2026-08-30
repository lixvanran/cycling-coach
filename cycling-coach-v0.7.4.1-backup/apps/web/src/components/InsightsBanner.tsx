// 训练洞察告警 Banner — 顶部通知, 集成 Dashboard
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  X,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { InsightsToday, Insight } from "../lib/types";

const SEVERITY_CONFIG = {
  alert: {
    icon: AlertTriangle,
    bg: "bg-rose-50",
    border: "border-rose-300",
    text: "text-rose-700",
    label: "严重",
  },
  warning: {
    icon: AlertCircle,
    bg: "bg-amber-50",
    border: "border-amber-300",
    text: "text-amber-700",
    label: "注意",
  },
  info: {
    icon: Info,
    bg: "bg-emerald-50",
    border: "border-emerald-300",
    text: "text-emerald-700",
    label: "提示",
  },
};

const CATEGORY_LABEL: Record<string, string> = {
  load: "训练负荷",
  recovery: "身体状态",
  distribution: "强度分布",
  race: "比赛准备",
  ftp: "FTP 测试",
  phase: "周期阶段",
};

export function InsightsBanner() {
  const [data, setData] = useState<InsightsToday | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    api.insightsToday().then(setData).catch(() => setData(null));
  }, []);

  if (dismissed || !data || data.insights.length === 0) return null;

  const top = data.insights[0];
  const topConfig = SEVERITY_CONFIG[top.severity];
  const TopIcon = topConfig.icon;
  const more = data.insights.length - 1;

  return (
    <div className={clsx("rounded-md border-2 p-3 space-y-2", topConfig.bg, topConfig.border)}>
      {/* 头部: 最高严重度 + 简述 */}
      <div className="flex items-start gap-3">
        <TopIcon className={clsx("w-5 h-5 mt-0.5 flex-shrink-0", topConfig.text)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={clsx("text-xs font-semibold px-1.5 py-0.5 rounded", topConfig.text, "bg-white/60")}>
              {topConfig.label}
            </span>
            <span className="text-xs text-text-muted">{CATEGORY_LABEL[top.category]}</span>
            {data.summary.health_score < 85 && (
              <span className="text-xs text-text-muted">
                健康分 {data.summary.health_score} ({data.summary.health_label})
              </span>
            )}
          </div>
          <div className="font-semibold text-sm mt-1">{top.title}</div>
          <div className="text-xs text-text-muted mt-0.5 leading-relaxed">{top.description}</div>
          {top.metric_value && (
            <div className="text-xs font-mono text-text-primary mt-1">{top.metric_value}</div>
          )}
          <div className="text-xs mt-2 px-2 py-1.5 rounded bg-white/60">
            <span className="font-semibold text-text-primary">建议: </span>
            <span className="text-text-primary">{top.recommendation}</span>
          </div>
          {top.academic_source && (
            <div className="text-[10px] text-text-muted mt-1 italic">📚 {top.academic_source}</div>
          )}
        </div>
        <div className="flex flex-col gap-1">
          {more > 0 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-text-muted hover:text-text-primary flex items-center gap-1"
            >
              {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {more} 条
            </button>
          )}
          <button
            onClick={() => setDismissed(true)}
            className="p-0.5 rounded hover:bg-white/60"
            title="关闭"
          >
            <X className="w-3.5 h-3.5 text-text-muted" />
          </button>
        </div>
      </div>

      {/* 展开: 列出其他 */}
      {expanded && more > 0 && (
        <div className="border-t border-current/20 pt-2 space-y-2">
          {data.insights.slice(1).map((ins) => (
            <InsightRow key={ins.id} insight={ins} />
          ))}
        </div>
      )}
    </div>
  );
}

function InsightRow({ insight }: { insight: Insight }) {
  const config = SEVERITY_CONFIG[insight.severity];
  const Icon = config.icon;
  return (
    <div className={clsx("p-2 rounded border", config.bg, config.border, "bg-white/40")}>
      <div className="flex items-start gap-2">
        <Icon className={clsx("w-3.5 h-3.5 mt-0.5 flex-shrink-0", config.text)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <span className={clsx("font-semibold", config.text)}>{config.label}</span>
            <span className="text-text-muted">{CATEGORY_LABEL[insight.category]}</span>
          </div>
          <div className="text-sm font-medium mt-0.5">{insight.title}</div>
          {insight.metric_value && (
            <div className="text-[10px] font-mono text-text-muted mt-0.5">{insight.metric_value}</div>
          )}
          <div className="text-xs text-text-primary mt-0.5">{insight.recommendation}</div>
        </div>
      </div>
    </div>
  );
}

// Dashboard 顶部健康分卡片
export function InsightsHealthCard() {
  const [data, setData] = useState<InsightsToday | null>(null);

  useEffect(() => {
    api.insightsToday().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;
  const score = data.summary.health_score;
  const color = score >= 85 ? "emerald" : score >= 60 ? "amber" : "rose";

  return (
    <div className={clsx(
      "panel p-3 border-l-4",
      color === "emerald" ? "border-emerald-400" :
      color === "amber" ? "border-amber-400" :
      "border-rose-400"
    )}>
      <div className="text-xs text-text-muted flex items-center gap-1">
        <Sparkles className="w-3 h-3" /> 训练健康分
      </div>
      <div className={clsx(
        "text-3xl font-bold font-mono mt-1",
        color === "emerald" ? "text-emerald-600" :
        color === "amber" ? "text-amber-600" :
        "text-rose-600"
      )}>
        {score}
        <span className="text-sm text-text-muted ml-1">/ 100</span>
      </div>
      <div className="text-xs text-text-muted mt-1">
        {data.summary.health_label}
        {data.summary.alert > 0 && ` · ${data.summary.alert} 严重`}
        {data.summary.warning > 0 && ` · ${data.summary.warning} 注意`}
      </div>
      <div className="text-[10px] text-text-muted mt-1">
        CTL {data.pcm.ctl} · TSB {data.pcm.tsb} · ramp {data.pcm.ramp_rate}
      </div>
    </div>
  );
}
