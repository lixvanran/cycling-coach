// ACWR 急慢性负荷比图 (V0.6.1)
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
} from "recharts";

export interface ACWRData {
  today: { date: string; acute: number; chronic: number; acwr: number; zone: string } | null;
  weekly_change: number | null;
  risk: "low" | "medium" | "high";
  risk_label: string;
  recommendation: string;
  series: Array<{ date: string; acute: number; chronic: number; acwr: number; zone: string }>;
  windows: { acute_days: number; chronic_days: number };
}

interface Props {
  data: ACWRData | null | undefined;
}

const RISK_COLOR: Record<string, string> = {
  low: "text-emerald-600",
  medium: "text-amber-600",
  high: "text-rose-600",
};

const RISK_BG: Record<string, string> = {
  low: "bg-emerald-50 border-emerald-200",
  medium: "bg-amber-50 border-amber-200",
  high: "bg-rose-50 border-rose-200",
};

export function ACWRChart({ data }: Props) {
  if (!data) return <div className="text-text-muted text-sm">无 ACWR 数据</div>;

  const today = data.today;
  const series = data.series || [];

  return (
    <div className="space-y-3">
      {/* V0.7.1: 学术说明 — 区分 ACWR chronic (28d 简单平均) vs PMC CTL (42d EWMA) */}
      <div className="text-[10px] text-text-muted bg-amber-50/60 border border-amber-200/40 rounded px-2 py-1 leading-relaxed">
        <strong>ACWR 急慢性负荷比 (Gabbett 2016)</strong>: 7d 急性 TSS / 28d 慢性 TSS (简单均值)
        <br />
        <span className="text-amber-700">注意</span>: 与 PMC 的 CTL (42d EWMA) 是不同概念, 不可混用
      </div>

      {/* 头部状态卡 */}
      {today && (
        <div className={`px-3 py-2 rounded-md border ${RISK_BG[data.risk]}`}>
          <div className="flex items-center gap-3">
            <div>
              <div className="text-xs text-text-muted">今日 ACWR (7d / 28d)</div>
              <div className={`text-2xl font-bold font-mono ${RISK_COLOR[data.risk]}`}>
                {today.acwr.toFixed(2)}
              </div>
            </div>
            <div className="flex-1">
              <div className={`text-sm font-semibold ${RISK_COLOR[data.risk]}`}>{data.risk_label}</div>
              <div className="text-xs text-text-muted mt-0.5">{data.recommendation}</div>
            </div>
            {data.weekly_change != null && (
              <div className="text-right">
                <div className="text-xs text-text-muted">周环比</div>
                <div className={`text-sm font-mono ${data.weekly_change > 0.2 ? "text-rose-600" : data.weekly_change < -0.2 ? "text-amber-600" : "text-emerald-600"}`}>
                  {data.weekly_change > 0 ? "+" : ""}{data.weekly_change.toFixed(2)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ACWR 趋势图 */}
      {series.length > 0 && (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={series} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="date"
              stroke="#86909d"
              style={{ fontSize: 10, fontFamily: "monospace" }}
              tickFormatter={(d) => d.slice(5)}
            />
            <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} domain={[0, 2.5]} />
            <Tooltip
              contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
              formatter={(v: number, n: string) => [
                typeof v === "number" ? v.toFixed(2) : v,
                n,
              ]}
            />
            {/* Sweet spot 区 (0.8-1.3) */}
            <ReferenceArea y1={0.8} y2={1.3} fill="#d1fae5" fillOpacity={0.4} />
            {/* Caution 区 (1.3-1.5) */}
            <ReferenceArea y1={1.3} y2={1.5} fill="#fef3c7" fillOpacity={0.4} />
            {/* Danger 区 (1.5+) */}
            <ReferenceArea y1={1.5} y2={2.5} fill="#fecaca" fillOpacity={0.4} />
            <ReferenceLine y={0.8} stroke="#10b981" strokeDasharray="3 3" label={{ value: "0.8 偏低", position: "insideTopLeft", style: { fontSize: 9, fill: "#10b981" } }} />
            <ReferenceLine y={1.3} stroke="#10b981" strokeDasharray="3 3" label={{ value: "1.3 偏高", position: "insideTopLeft", style: { fontSize: 9, fill: "#10b981" } }} />
            <ReferenceLine y={1.5} stroke="#dc2626" strokeDasharray="3 3" label={{ value: "1.5 危险", position: "insideTopLeft", style: { fontSize: 9, fill: "#dc2626" } }} />
            <Line type="monotone" dataKey="acwr" stroke="#3b82f6" strokeWidth={2.5} dot={false} isAnimationActive={false} name="ACWR" />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="text-xs text-text-muted leading-relaxed">
        <div>📊 <span className="font-medium">ACWR</span> = 急性负荷 (7d avg TSS) / 慢性负荷 (28d avg TSS)</div>
        <div>📚 学术来源: <a href="https://pubmed.ncbi.nlm.nih.gov/27125412/" className="text-primary hover:underline" target="_blank" rel="noreferrer">Gabbett 2016</a> · Sweet spot 0.8-1.3 受伤风险最低, &gt;1.5 风险飙升</div>
      </div>
    </div>
  );
}
