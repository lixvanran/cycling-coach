// Dashboard 主页 — V0.3 加 PMC + 今日状态卡
import { useEffect, useState } from "react";
import { Activity, Clock, Flame, Mountain, RefreshCw } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { PMCChart } from "../components/PMCChart";
import { PMCStatusCard } from "../components/PMCStatusCard";
import { api } from "../lib/api";
import type {
  DashboardOverview,
  Athlete,
  PMCSeries,
  PMCToday,
} from "../lib/types";
import { useAppStore } from "../store/useAppStore";

const RANGE_OPTIONS = [
  { value: 30, label: "30 天" },
  { value: 90, label: "90 天" },
  { value: 180, label: "半年" },
  { value: 365, label: "一年" },
];

export function Dashboard() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [pmc, setPMC] = useState<PMCSeries | null>(null);
  const [pmcToday, setPMCToday] = useState<PMCToday | null>(null);
  const [pmcDays, setPmcDays] = useState(90);
  const [rebuilding, setRebuilding] = useState(false);
  const [loading, setLoading] = useState(true);
  const setView = useAppStore((s) => s.setView);

  const refresh = async () => {
    setLoading(true);
    try {
      const [o, a, p, pt] = await Promise.all([
        api.getOverview(),
        api.getAthlete(),
        api.getPMC(pmcDays),
        api.getPMCToday(),
      ]);
      setOverview(o);
      setAthlete(a);
      setPMC(p);
      setPMCToday(pt);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pmcDays]);

  if (loading && !overview) {
    return <div className="p-6 text-text-muted">加载中…</div>;
  }

  if (!overview || overview.total_activities === 0) {
    return <EmptyState onImport={() => setView("import")} />;
  }

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await api.rebuildPMC();
      await refresh();
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            欢迎回来,{athlete?.name || "Rider"}
          </h1>
          <p className="text-sm text-text-muted mt-1">
            这是你目前的训练概览。继续坚持。
          </p>
        </div>
        <button
          onClick={handleRebuild}
          disabled={rebuilding}
          className="btn-ghost flex items-center gap-1.5 text-xs"
        >
          <RefreshCw size={12} className={rebuilding ? "animate-spin" : ""} />
          {rebuilding ? "重建中..." : "重建 PMC"}
        </button>
      </div>

      {/* V0.3:PMC 状态卡 + 概览(顶部高优) */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <PMCStatusCard today={pmcToday} loading={loading} />

        <div className="lg:col-span-2 panel p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm uppercase tracking-wider text-text-secondary">
              本周训练
            </h2>
            <span className="text-xs text-text-muted">最后 7 天</span>
          </div>
          <div className="grid grid-cols-4 gap-3 mt-3">
            <MetricCard
              label="训练次数"
              value={overview.this_week.activities}
              unit="次"
            />
            <MetricCard
              label="距离"
              value={overview.this_week.distance_km}
              unit="km"
            />
            <MetricCard
              label="时长"
              value={overview.this_week.duration_h}
              unit="h"
            />
            <MetricCard
              label="TSS"
              value={overview.this_week.tss}
              unit=""
              accent="primary"
              hint="训练压力"
            />
          </div>
        </div>
      </section>

      {/* V0.3:PMC 主图(全宽) */}
      <section className="panel p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Performance Management Chart
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              CTL 慢性负荷(42d EWMA)· ATL 急性负荷(7d EWMA)· TSB 状态 = CTL − ATL
            </p>
          </div>
          <div className="flex gap-1 bg-bg-input rounded-lg p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setPmcDays(opt.value)}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${
                  pmcDays === opt.value
                    ? "bg-accent-primary text-white"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <PMCChart series={pmc?.series || []} height={300} />
      </section>

      {/* 训练洞察告警 (V0.7 新增) — 高严重度优先 */}
      <InsightsBanner />

      {/* 累计 */}
      <section>
        <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-3">累计</h2>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <MetricCard label="总训练" value={overview.total_activities} unit="次" />
          <MetricCard label="总距离" value={overview.total_distance_km} unit="km" />
          <MetricCard label="总时长" value={overview.total_duration_h} unit="h" />
          <MetricCard label="总 TSS" value={overview.total_tss} accent="warning" />
          <InsightsHealthCard />
        </div>
      </section>

      {/* 最近 7 天 */}
      <section>
        <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-3">最近 7 天</h2>
        <div className="panel p-4">
          <div className="grid grid-cols-7 gap-2">
            {overview.last_7_days.map((d, i) => (
              <div key={i} className="text-center">
                <div className="text-xs text-text-muted mb-2">
                  {new Date(d.date).toLocaleDateString("zh-CN", { weekday: "short" })}
                </div>
                <div className="h-24 bg-bg-input rounded flex items-end justify-center p-1">
                  <div
                    className="w-full bg-accent-primary rounded-sm"
                    style={{
                      height: `${Math.min(100, (d.tss / Math.max(1, ...overview.last_7_days.map(x => x.tss))) * 100)}%`,
                    }}
                  />
                </div>
                <div className="text-xs font-mono text-text-primary mt-1">{d.tss}</div>
                <div className="text-[10px] text-text-muted">{d.distance_km}km</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 快速操作 */}
      <section>
        <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-3">快速操作</h2>
        <div className="flex gap-3">
          <button onClick={() => setView("import")} className="btn-primary">
            <Activity size={14} />
            导入训练数据
          </button>
          <button onClick={() => setView("activities")} className="btn-ghost">
            查看所有训练
          </button>
        </div>
      </section>
    </div>
  );
}

function EmptyState({ onImport }: { onImport: () => void }) {
  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="w-16 h-16 rounded-full bg-bg-elevated mx-auto mb-4 flex items-center justify-center">
          <Activity size={28} className="text-text-muted" />
        </div>
        <h2 className="text-xl font-semibold text-text-primary mb-2">还没有训练数据</h2>
        <p className="text-sm text-text-muted mb-6">
          上传一个 FIT 文件,或者先生成一些示例训练看看效果。
        </p>
        <button onClick={onImport} className="btn-primary">
          开始训练 →
        </button>
      </div>
    </div>
  );
}
