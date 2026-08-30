// 活动对比 (V0.6 GoldenCheetah 对标)
// 流程: 1) 多选活动 (checkbox 列表) 2) 调 compare API 3) 显示指标表 + MMP 叠加图
import { useEffect, useState, useMemo } from "react";
import { GitCompare, Loader2, AlertCircle, Check, X } from "lucide-react";
import { api } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#84cc16"];

interface CompareActivity {
  id: number;
  name: string;
  start_time: string | null;
  duration_s: number;
  duration_str: string;
  distance_km: number;
  avg_power: number | null;
  avg_hr: number | null;
  avg_cadence: number | null;
  tss: number | null;
  tss_per_hour: number;
  metrics: Record<string, number | null>;
  mmp: Record<string, number>;
  zones: Record<string, number>;
}

export function ComparePage() {
  const setView = useAppStore((s) => s.setView);
  const setSelectedId = useAppStore((s) => s.setSelectedActivity);

  const [allActivities, setAllActivities] = useState<any[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [compare, setCompare] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);

  useEffect(() => {
    setLoadingList(true);
    api.listActivities({ limit: 200 })
      .then((d: any) => setAllActivities(d.activities || []))
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingList(false));
  }, []);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 10) {
        next.add(id);
      }
      return next;
    });
  };

  const doCompare = async () => {
    if (selected.size < 1) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.compareActivities(Array.from(selected));
      setCompare(data);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  // MMP 叠加图数据: 把多个活动的 MMP 折成 Recharts 格式
  // { duration_s: 5, "Ride 1": 480, "Ride 2": 500, ... }
  const mmpChartData = useMemo(() => {
    if (!compare?.activities) return [];
    const durations = ["5s", "30s", "60s", "120s", "300s", "600s", "1200s", "3600s"];
    const durSeconds: Record<string, number> = {
      "5s": 5, "30s": 30, "60s": 60, "120s": 120,
      "300s": 300, "600s": 600, "1200s": 1200, "3600s": 3600,
    };
    return durations
      .filter((d) => compare.activities.some((a: CompareActivity) => a.mmp[d] != null))
      .map((d) => {
        const row: any = { duration_s: durSeconds[d], label: d };
        compare.activities.forEach((a: CompareActivity, i: number) => {
          row[`act_${i}`] = a.mmp[d] ?? null;
        });
        return row;
      });
  }, [compare]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="px-6 py-4 border-b border-border bg-bg-card flex items-center gap-3">
        <GitCompare className="w-5 h-5 text-primary" />
        <h1 className="text-lg font-semibold text-text-primary">活动对比</h1>
        <span className="text-xs text-text-muted ml-2">最多 10 个活动</span>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 1. 活动多选 */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">选择要对比的活动</div>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              已选 {selected.size} / 10
              {selected.size > 0 && (
                <button
                  className="ml-2 text-xs text-primary hover:underline"
                  onClick={() => setSelected(new Set())}
                >
                  清空
                </button>
              )}
            </div>
          </div>
          <div className="p-4">
            {loadingList ? (
              <div className="text-text-muted text-sm">加载活动列表…</div>
            ) : allActivities.length === 0 ? (
              <div className="text-text-muted text-sm">还没有活动, 先去"导入"页上传 FIT/TCX/GPX</div>
            ) : (
              <div className="space-y-1 max-h-72 overflow-y-auto">
                {allActivities.map((a) => {
                  const isSelected = selected.has(a.id);
                  return (
                    <label
                      key={a.id}
                      className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-primary/10 border border-primary/30"
                          : "hover:bg-slate-50 border border-transparent"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(a.id)}
                        className="rounded"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-text-primary truncate">
                          {a.start_time?.slice(0, 10) || "—"} · {a.id}
                        </div>
                        <div className="text-xs text-text-muted">
                          {a.duration_s ? `${Math.round(a.duration_s / 60)}min` : "—"}
                          {a.distance_m ? ` · ${(a.distance_m / 1000).toFixed(1)}km` : ""}
                          {a.normalized_power ? ` · NP ${a.normalized_power}W` : ""}
                        </div>
                      </div>
                      {isSelected && <Check className="w-4 h-4 text-primary" />}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
          <div className="px-4 py-3 border-t border-border flex justify-end">
            <button
              onClick={doCompare}
              disabled={selected.size < 1 || loading}
              className="btn-primary px-4 py-1.5 text-sm flex items-center gap-2 disabled:opacity-40"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompare className="w-4 h-4" />}
              对比 ({selected.size})
            </button>
          </div>
        </section>

        {error && (
          <div className="panel border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5" />
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-auto"><X className="w-4 h-4" /></button>
          </div>
        )}

        {/* 2. 指标对比表 */}
        {compare && (
          <section className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">关键指标对比</div>
              <div className="text-xs text-text-muted">共 {compare.comparison.count} 个活动</div>
            </div>
            <div className="p-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-text-muted font-medium py-2 pr-3 w-32">指标</th>
                    {compare.activities.map((a: CompareActivity, i: number) => (
                      <th
                        key={a.id}
                        className="text-left font-medium py-2 px-2 cursor-pointer hover:bg-slate-50"
                        style={{ color: COLORS[i % COLORS.length] }}
                        onClick={() => {
                          setSelectedId(a.id);
                          setView("activity-detail");
                        }}
                      >
                        <div className="truncate max-w-[140px]">{a.name}</div>
                        <div className="text-xs text-text-muted font-normal">{a.start_time?.slice(0, 10)}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compare.comparison.metrics_table.map((row: any) => {
                    const bestIdx = compare.comparison.best_by_metric
                      ? Object.entries(compare.comparison.best_by_metric).find(([_k, v]) => {
                          // 反向找 row 对应的指标 key
                          const reverseMap: Record<string, string> = {
                            "NP (W)": "normalized_power",
                            "TSS": "tss",
                            "TSS/h": "tss_per_hour",
                            "5s 峰值 (W)": "5s",
                            "1min 峰值 (W)": "60s",
                            "5min 峰值 (W)": "300s",
                            "20min 峰值 (W)": "1200s",
                          };
                          return reverseMap[row.label] === _k;
                        })?.[1] as number | undefined
                      : undefined;
                    return (
                      <tr key={row.label} className="border-b border-border/50">
                        <td className="py-1.5 pr-3 text-text-muted">{row.label}</td>
                        {row.values.map((v: any, i: number) => (
                          <td
                            key={i}
                            className={`py-1.5 px-2 font-mono text-xs ${
                              bestIdx === i ? "bg-emerald-50 text-emerald-700 font-semibold" : ""
                            }`}
                          >
                            {v ?? <span className="text-text-muted">—</span>}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 3. MMP 叠加图 */}
        {compare && mmpChartData.length > 0 && (
          <section className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">MMP 曲线叠加 (各时长最大平均功率)</div>
              <div className="text-xs text-text-muted">GoldenCheetah-style Critical Power 模型</div>
            </div>
            <div className="p-4">
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={mmpChartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="duration_s"
                    type="number"
                    scale="log"
                    domain={[5, 3600]}
                    ticks={[5, 30, 60, 120, 300, 600, 1200, 3600]}
                    tickFormatter={(v) => v < 60 ? `${v}s` : v < 3600 ? `${v / 60}min` : `${v / 3600}h`}
                    stroke="#86909d"
                    style={{ fontSize: 11, fontFamily: "monospace" }}
                  />
                  <YAxis stroke="#86909d" style={{ fontSize: 11, fontFamily: "monospace" }} unit="W" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(255,255,255,0.95)",
                      border: "1px solid rgba(15,23,42,0.12)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    labelFormatter={(v: number) => `${v < 60 ? v + "s" : v < 3600 ? v / 60 + "min" : v / 3600 + "h"}`}
                    formatter={(v: number, n: string) => v != null ? [`${v}W`, n] : ["—", n]}
                  />
                  <Legend />
                  {compare.activities.map((a: CompareActivity, i: number) => (
                    <Line
                      key={a.id}
                      type="monotone"
                      dataKey={`act_${i}`}
                      name={a.name}
                      stroke={COLORS[i % COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
