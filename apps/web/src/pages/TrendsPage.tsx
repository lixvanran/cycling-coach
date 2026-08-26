// 长期趋势 (V0.6 Phase 3) — 对标 GoldenCheetah Trends 标签
// 4 个区域: 训练量 / 7 区分布 / 关键指标 / PMC + 同期对比
import { useEffect, useState, useMemo } from "react";
import {
  TrendingUp,
  Loader2,
  AlertCircle,
  X,
  Activity,
  Zap,
  Heart,
  Layers,
} from "lucide-react";
import { api } from "../lib/api";
import { ACWRChart } from "../components/ACWRChart";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";

const ZONE_COLORS: Record<string, string> = {
  Z1: "#9ca3af",
  Z2: "#3b82f6",
  Z3: "#10b981",
  Z4: "#f59e0b",
  Z5: "#ef4444",
  Z6: "#dc2626",
  Z7: "#7c2d12",
};

const DAYS_OPTIONS = [
  { value: 30, label: "近 30 天" },
  { value: 90, label: "近 90 天" },
  { value: 180, label: "近 6 个月" },
  { value: 365, label: "近 1 年" },
];

export function TrendsPage() {
  const [days, setDays] = useState(90);
  const [overview, setOverview] = useState<any>(null);
  const [acwr, setAcwr] = useState<any>(null);
  const [rpe, setRpe] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.trendsOverview(days),
      api.trendsAcwr(days),
      api.trendsRpe(days),
    ])
      .then(([ov, ac, rpe]) => {
        setOverview(ov);
        setAcwr(ac);
        setRpe(rpe);
      })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b border-border bg-bg-card flex items-center gap-3">
        <TrendingUp className="w-5 h-5 text-primary" />
        <h1 className="text-lg font-semibold text-text-primary">长期趋势</h1>
        <span className="text-xs text-text-muted ml-2">GoldenCheetah-style 周/月聚合</span>

        <div className="ml-auto flex gap-1">
          {DAYS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setDays(opt.value)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                days === opt.value
                  ? "bg-primary text-white"
                  : "bg-slate-100 text-text-muted hover:bg-slate-200"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {loading && (
          <div className="text-text-muted text-sm flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
          </div>
        )}

        {error && (
          <div className="panel border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5" />
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-auto">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {overview && <OverviewView overview={overview} />}
      </div>
    </div>
  );
}

function OverviewView({ overview }: { overview: any }) {
  const { volume, zones, metrics, pmc, yoy, days, weeks } = overview;

  return (
    <>
      {/* 顶部数据卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          icon={<Activity className="w-4 h-4" />}
          label="总训练量 (TSS)"
          value={volume.summary.total_tss.toLocaleString()}
          sub={`${weeks} 周 · 平均 ${volume.summary.avg_weekly_tss}/周`}
          yoy={yoy?.tss_change_pct}
        />
        <StatCard
          icon={<Zap className="w-4 h-4" />}
          label="总距离"
          value={`${volume.summary.total_distance_km.toFixed(0)} km`}
          sub={yoy?.distance_change_pct != null ? `同比 ${yoy.distance_change_pct > 0 ? "+" : ""}${yoy.distance_change_pct}%` : ""}
        />
        <StatCard
          icon={<Heart className="w-4 h-4" />}
          label="总时长"
          value={`${volume.summary.total_duration_h.toFixed(1)} h`}
          sub={`平均 ${(volume.summary.total_duration_h / Math.max(1, weeks)).toFixed(1)} h/周`}
        />
        <StatCard
          icon={<Layers className="w-4 h-4" />}
          label="活动数"
          value={volume.series.reduce((s: number, b: any) => s + b.activities, 0).toString()}
          sub={`${weeks} 周有数据`}
        />
      </div>

      {/* 1. 训练量趋势 (TSS 柱状图) */}
      {volume.series.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">训练量趋势 (TSS / 周)</div>
            <div className="text-xs text-text-muted">柱越高 = 周训练量越大</div>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={volume.series} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="key" stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number, n: string) => [v, n]}
                />
                <Bar dataKey="tss" fill="#6366f1" name="TSS" radius={[3, 3, 0, 0]} />
                <Bar dataKey="distance_km" fill="#10b981" name="距离 (km)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* 2. 7 区分布堆叠面积图 */}
      {zones.series.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">7 区分布时间变化</div>
            <div className="text-xs text-text-muted">堆叠 = 周总秒数, 颜色 = 7 区 Coggan</div>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={zones.series} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="key" stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} label={{ value: "秒", angle: -90, position: "insideLeft", style: { fontSize: 10, fill: "#86909d" } }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number, n: string) => [`${v}秒 (${(v / 60).toFixed(1)}min)`, n]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"].map((z) => (
                  <Area
                    key={z}
                    type="monotone"
                    dataKey={z}
                    stackId="1"
                    stroke={ZONE_COLORS[z]}
                    fill={ZONE_COLORS[z]}
                    name={z}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* 3. 关键指标趋势 (NP / IF) */}
      {metrics.series.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">关键指标趋势 (NP / IF / 平均心率)</div>
            <div className="text-xs text-text-muted">每周活动均值</div>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={metrics.series} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="key" stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <YAxis yAxisId="left" stroke="#3b82f6" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <YAxis yAxisId="right" orientation="right" stroke="#ef4444" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line yAxisId="left" type="monotone" dataKey="avg_normalized_power" stroke="#3b82f6" name="NP (W)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                <Line yAxisId="left" type="monotone" dataKey="avg_power" stroke="#10b981" name="平均功率 (W)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                <Line yAxisId="right" type="monotone" dataKey="avg_intensity_factor" stroke="#f59e0b" name="IF" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                <Line yAxisId="right" type="monotone" dataKey="avg_hr" stroke="#ef4444" name="平均心率 (bpm)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* 3.4 RPE 主观疲劳趋势 (V0.6.1 新增) */}
      {rpe && rpe.series && rpe.series.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              <span className="text-base">💪</span>
              RPE 主观疲劳趋势 (Borg CR-10)
            </div>
            <div className="text-xs text-text-muted">
              平均 {rpe.overall_avg} · 高强度日 {rpe.high_rpe_days} · 低强度日 {rpe.low_rpe_days}
            </div>
          </div>
          <div className="p-4">
            <div className="space-y-3">
              {/* 简化的滑动条: 每日 RPE */}
              <div className="space-y-1">
                {rpe.series.slice(-14).map((d: any) => (
                  <div key={d.date} className="flex items-center gap-2 text-xs">
                    <div className="w-20 text-text-muted font-mono">{d.date.slice(5)}</div>
                    <div className="flex-1 h-5 bg-slate-50 rounded relative overflow-hidden">
                      <div
                        className={`h-full rounded ${
                          d.avg_rpe >= 8 ? "bg-rose-300" :
                          d.avg_rpe >= 6 ? "bg-amber-300" :
                          d.avg_rpe >= 4 ? "bg-lime-300" :
                          "bg-emerald-300"
                        }`}
                        style={{ width: `${(d.avg_rpe / 10) * 100}%` }}
                      />
                    </div>
                    <div className="w-12 text-right font-mono font-semibold">{d.avg_rpe}</div>
                    <div className="w-16 text-text-muted text-[10px]">×{d.count}</div>
                  </div>
                ))}
              </div>
              <div className="text-xs text-text-muted pt-2 border-t border-border space-y-0.5">
                <div>📚 训练学解读: 7 天滑动 RPE 持续 &gt; 7 提示身体疲劳累积, 建议降量</div>
                <div>📊 理想范围: RPE/TSS 比值 ≈ 0.05-0.10 (主观 vs 客观负荷匹配)</div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 3.5 ACWR 急慢性负荷比 (V0.6.1 受伤风险预警) */}
      {acwr && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              ACWR 急慢性负荷比
            </div>
            <div className="text-xs text-text-muted">Gabbett 2016 学术标准 · 7d / 28d TSS</div>
          </div>
          <div className="p-4">
            <ACWRChart data={acwr} />
          </div>
        </section>
      )}

      {/* 4. PMC (CTL/ATL/TSB) — 复用已有数据 */}
      {pmc && pmc.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">PMC (Performance Management Chart)</div>
            <div className="text-xs text-text-muted">CTL = 长期负荷 · ATL = 短期疲劳 · TSB = 状态 = CTL - ATL</div>
          </div>
          <div className="p-4">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={pmc} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} tickFormatter={(d) => d.slice(5)} />
                <YAxis yAxisId="left" stroke="#3b82f6" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <YAxis yAxisId="right" orientation="right" stroke="#8b5cf6" style={{ fontSize: 10, fontFamily: "monospace" }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine yAxisId="right" y={0} stroke="#94a3b8" strokeDasharray="2 2" />
                <Line yAxisId="left" type="monotone" dataKey="ctl" stroke="#3b82f6" name="CTL" strokeWidth={2} dot={false} />
                <Line yAxisId="left" type="monotone" dataKey="atl" stroke="#f59e0b" name="ATL" strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="tsb" stroke="#8b5cf6" name="TSB" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {volume.series.length === 0 && (
        <div className="text-center text-text-muted py-12">
          <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>没有足够的数据. 上传更多 FIT 文件来查看趋势.</p>
        </div>
      )}
    </>
  );
}

function StatCard({ icon, label, value, sub, yoy }: { icon: React.ReactNode; label: string; value: string; sub: string; yoy?: number | null }) {
  return (
    <div className="panel p-3">
      <div className="flex items-center gap-2 text-text-muted text-xs">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-semibold text-text-primary mt-1">{value}</div>
      <div className="text-xs text-text-muted mt-0.5 flex items-center gap-2">
        {sub}
        {yoy != null && yoy !== 0 && (
          <span className={yoy > 0 ? "text-emerald-600" : "text-rose-600"}>
            {yoy > 0 ? "↑" : "↓"} {Math.abs(yoy)}%
          </span>
        )}
      </div>
    </div>
  );
}
