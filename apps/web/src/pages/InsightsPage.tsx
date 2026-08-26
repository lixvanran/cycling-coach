// 周复盘页 — Friel Weekly Review
import { useEffect, useState } from "react";
import {
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  Clock,
  Mountain,
  Heart,
  Calendar,
  ArrowRight,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from "recharts";
import clsx from "clsx";
import { api } from "../lib/api";
import type { WeeklyReview, InsightsToday } from "../lib/types";

const ZONE_COLORS = [
  "#86efac", "#10b981", "#fde68a", "#fbbf24",
  "#fca5a5", "#f87171", "#dc2626",
];

export function InsightsPage() {
  const [weekly, setWeekly] = useState<WeeklyReview | null>(null);
  const [today, setToday] = useState<InsightsToday | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.insightsWeekly(), api.insightsToday()])
      .then(([w, t]) => {
        setWeekly(w);
        setToday(t);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-text-muted text-sm">加载中...</div>
      </div>
    );
  }

  if (!weekly || !today) {
    return (
      <div className="p-6">
        <div className="text-text-muted text-sm">暂无数据</div>
      </div>
    );
  }

  const tssChange = weekly.comparison.tss_change;
  const trend = tssChange > 20 ? "up" : tssChange < -20 ? "down" : "stable";
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
  const trendColor = trend === "up" ? "text-amber-600" : trend === "down" ? "text-emerald-600" : "text-text-muted";

  // 强度分布 (Z1-Z7)
  const zoneData = Object.entries(weekly.this_week.zone_pct).map(([zone, pct], i) => ({
    zone,
    pct,
    color: ZONE_COLORS[i],
  }));

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-accent" />
          训练洞察 & 周复盘
        </h1>
        <p className="text-sm text-text-muted mt-1">
          借鉴 Joe Friel Weekly Review + Tim Gabbett 训练负荷管理 + Stephen Seiler 80/20
        </p>
      </div>

      {/* 顶部 3 卡: 健康分 / 今日洞察数 / 训练量趋势 */}
      <div className="grid grid-cols-3 gap-4">
        <div className={clsx(
          "panel p-4 border-l-4",
          today.summary.health_score >= 85 ? "border-emerald-400" :
          today.summary.health_score >= 60 ? "border-amber-400" :
          "border-rose-400"
        )}>
          <div className="text-xs text-text-muted">训练健康分</div>
          <div className={clsx(
            "text-4xl font-bold font-mono mt-1",
            today.summary.health_score >= 85 ? "text-emerald-600" :
            today.summary.health_score >= 60 ? "text-amber-600" :
            "text-rose-600"
          )}>
            {today.summary.health_score}
            <span className="text-base text-text-muted ml-1">/ 100</span>
          </div>
          <div className="text-xs text-text-muted mt-1">
            {today.summary.health_label}
            {today.summary.alert > 0 && ` · ${today.summary.alert} 严重`}
            {today.summary.warning > 0 && ` · ${today.summary.warning} 注意`}
          </div>
        </div>

        <div className="panel p-4 border-l-4 border-blue-400">
          <div className="text-xs text-text-muted">今日洞察</div>
          <div className="text-4xl font-bold font-mono mt-1 text-blue-600">
            {today.insights.length}
          </div>
          <div className="text-xs text-text-muted mt-1">
            严重 {today.summary.alert} · 注意 {today.summary.warning} · 提示 {today.summary.info}
          </div>
        </div>

        <div className="panel p-4 border-l-4 border-purple-400">
          <div className="text-xs text-text-muted">本周 TSS 趋势</div>
          <div className="flex items-center gap-2 mt-1">
            <TrendIcon className={clsx("w-5 h-5", trendColor)} />
            <div className={clsx("text-2xl font-bold font-mono", trendColor)}>
              {tssChange > 0 ? "+" : ""}{tssChange.toFixed(0)}
            </div>
            <span className="text-xs text-text-muted">
              ({weekly.comparison.tss_change_pct?.toFixed(1)}%)
            </span>
          </div>
          <div className="text-xs text-text-muted mt-1">vs 上周</div>
        </div>
      </div>

      {/* 本周 vs 上周 详细对比 */}
      <section className="panel">
        <div className="panel-header">
          <div className="text-sm font-medium">本周 vs 上周</div>
          <div className="text-xs text-text-muted">数据驱动复盘 (Friel 6 项检查)</div>
        </div>
        <div className="grid grid-cols-2 gap-4 p-4">
          {/* 本周 */}
          <div>
            <div className="text-xs text-text-muted mb-2 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> 本周
            </div>
            <div className="space-y-2">
              <WeekStat icon={Activity} label="训练次数" value={`${weekly.this_week.count} 次`} color="blue" />
              <WeekStat icon={Clock} label="总时长" value={`${weekly.this_week.duration_h.toFixed(1)} h`} color="emerald" />
              <WeekStat icon={Mountain} label="总距离" value={`${weekly.this_week.distance_km.toFixed(1)} km`} color="sky" />
              <WeekStat icon={TrendingUp} label="总 TSS" value={`${weekly.this_week.tss.toFixed(0)}`} color="amber" />
              {weekly.this_week.avg_rpe && (
                <WeekStat icon={Heart} label="平均 RPE" value={`${weekly.this_week.avg_rpe.toFixed(1)}`} color="rose" />
              )}
            </div>
          </div>
          {/* 上周 */}
          <div>
            <div className="text-xs text-text-muted mb-2">上周</div>
            <div className="space-y-2">
              <WeekStat icon={Activity} label="训练次数" value={`${weekly.last_week.count} 次`} color="blue" muted />
              <WeekStat icon={Clock} label="总时长" value={`${weekly.last_week.duration_h.toFixed(1)} h`} color="emerald" muted />
              <WeekStat icon={Mountain} label="总距离" value={`${weekly.last_week.distance_km.toFixed(1)} km`} color="sky" muted />
              <WeekStat icon={TrendingUp} label="总 TSS" value={`${weekly.last_week.tss.toFixed(0)}`} color="amber" muted />
              {weekly.last_week.avg_rpe && (
                <WeekStat icon={Heart} label="平均 RPE" value={`${weekly.last_week.avg_rpe.toFixed(1)}`} color="rose" muted />
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 强度分布 (Seiler 80/20) */}
      <section className="panel">
        <div className="panel-header">
          <div className="text-sm font-medium">本周强度分布 (7 区 Coggan)</div>
          <div className="text-xs text-text-muted">
            目标: Z1+Z2 ≈ 80% · Z5+ ≈ 20% · Z3+Z4 ≈ 0% (避免灰色地带)
          </div>
        </div>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={zoneData}>
              <XAxis dataKey="zone" stroke="#86909d" style={{ fontSize: 12, fontFamily: "monospace" }} />
              <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [`${v.toFixed(1)}%`, "占比"]}
              />
              <Bar dataKey="pct" isAnimationActive={false}>
                {zoneData.map((d, i) => (
                  <Cell key={i} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-3 text-xs text-text-muted leading-relaxed">
            {weekly.this_week.zone_pct.Z1 + weekly.this_week.zone_pct.Z2 > 75 ? (
              <span className="text-emerald-600">✓ 低强度占比高, 训练分布健康</span>
            ) : weekly.this_week.zone_pct.Z3 + weekly.this_week.zone_pct.Z4 > 25 ? (
              <span className="text-amber-600">⚠ Z3+Z4 偏多, 灰色地带, 建议调整训练配比</span>
            ) : weekly.this_week.zone_pct.Z5 + weekly.this_week.zone_pct.Z6 + weekly.this_week.zone_pct.Z7 > 25 ? (
              <span className="text-amber-600">⚠ 高强度偏多, 累积疲劳风险</span>
            ) : (
              <span>分布可接受</span>
            )}
          </div>
        </div>
      </section>

      {/* 下周建议 */}
      <section className="panel p-4 bg-blue-50/50 border-blue-200">
        <div className="flex items-center gap-2 mb-2">
          <ArrowRight className="w-4 h-4 text-blue-600" />
          <div className="text-sm font-semibold text-blue-700">下周计划建议</div>
        </div>
        <div className="text-sm text-text-primary leading-relaxed">
          {weekly.next_week_advice}
        </div>
      </section>

      {/* 今日详细洞察 */}
      {today.insights.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium">今日详细洞察 ({today.insights.length})</div>
            <div className="text-xs text-text-muted">按严重度排序</div>
          </div>
          <div className="p-4 space-y-2">
            {today.insights.map((i) => (
              <div key={i.id} className={clsx(
                "p-3 rounded-md border",
                i.severity === "alert" ? "bg-rose-50 border-rose-200" :
                i.severity === "warning" ? "bg-amber-50 border-amber-200" :
                "bg-emerald-50 border-emerald-200"
              )}>
                <div className="flex items-start gap-2">
                  <div className={clsx(
                    "px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
                    i.severity === "alert" ? "bg-rose-200 text-rose-800" :
                    i.severity === "warning" ? "bg-amber-200 text-amber-800" :
                    "bg-emerald-200 text-emerald-800"
                  )}>
                    {i.severity}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{i.title}</div>
                    {i.metric_value && (
                      <div className="text-xs font-mono text-text-muted mt-0.5">{i.metric_value}</div>
                    )}
                    <div className="text-xs text-text-primary mt-1">{i.description}</div>
                    <div className="text-xs mt-2 px-2 py-1 rounded bg-white/60">
                      <span className="font-semibold">建议: </span>{i.recommendation}
                    </div>
                    {i.academic_source && (
                      <div className="text-[10px] text-text-muted mt-1 italic">📚 {i.academic_source}</div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function WeekStat({ icon: Icon, label, value, color, muted }: any) {
  return (
    <div className={clsx(
      "flex items-center justify-between px-3 py-1.5 rounded",
      muted ? "bg-slate-50" : `bg-${color}-50`
    )}>
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Icon className="w-3.5 h-3.5" />
        <span>{label}</span>
      </div>
      <div className="text-sm font-semibold font-mono">{value}</div>
    </div>
  );
}
