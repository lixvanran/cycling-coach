// Pa:HR Decoupling Card (V0.6.1 — GC 杀手锏)
import { Loader2, AlertCircle } from "lucide-react";
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

export interface DecouplingData {
  activity_id?: number;
  applicable: boolean;
  error?: string;
  duration_s?: number;
  decoupling_pct?: number;
  first_half?: { duration_s: number; avg_power: number; avg_hr: number; efficiency_factor: number };
  second_half?: { duration_s: number; avg_power: number; avg_hr: number; efficiency_factor: number };
  interpretation?: "excellent" | "normal" | "high" | "warning";
  interpretation_label?: string;
  color?: string;
  trend?: Array<{ start_s: number; end_s: number; decoupling_pct: number; first_ef: number; second_ef: number }>;
}

interface Props {
  data: DecouplingData | null | undefined;
  loading?: boolean;
}

const COLOR_MAP: Record<string, { bg: string; text: string; border: string }> = {
  excellent: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  normal: { bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200" },
  high: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  warning: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200" },
};

export function DecouplingCard({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="text-text-muted text-sm flex items-center gap-2 p-4">
        <Loader2 className="w-4 h-4 animate-spin" /> 加载 decoupling 数据…
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-text-muted text-sm p-4 text-center">
        无 Decoupling 数据
      </div>
    );
  }

  if (!data.applicable) {
    return (
      <div className="text-text-muted text-sm p-4 flex items-start gap-2 bg-slate-50 rounded-md">
        <AlertCircle className="w-4 h-4 mt-0.5" />
        <div>
          <div className="font-medium">不适用 (活动时长 &lt; 30min 或缺数据)</div>
          <div className="text-xs mt-1">
            Pa:HR Decoupling 需要 ≥ 30 分钟稳定输出 + 同步功率心率.
            {data.actual_samples && ` 当前 ${data.actual_samples} 个样本.`}
          </div>
        </div>
      </div>
    );
  }

  const c = COLOR_MAP[data.interpretation || "normal"] || COLOR_MAP.normal;
  const dec = data.decoupling_pct || 0;
  const absDec = Math.abs(dec);

  return (
    <div className="space-y-3">
      {/* 头部数字 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-text-muted">Pa:HR Decoupling</div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className={`text-3xl font-semibold font-mono ${c.text}`}>
              {dec > 0 ? "+" : ""}{dec.toFixed(1)}%
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${c.bg} ${c.text} border ${c.border}`}>
              {data.interpretation_label}
            </span>
          </div>
          <div className="text-xs text-text-muted mt-1">
            |decoupling| = {absDec.toFixed(1)}% · 活动 {(data.duration_s || 0) / 60 | 0}min
          </div>
        </div>

        {/* 前后半对比 */}
        <div className="text-xs space-y-1">
          {data.first_half && data.second_half && (
            <table className="text-xs">
              <thead className="text-text-muted">
                <tr>
                  <th className="text-right pr-2">段</th>
                  <th className="text-right pr-2">功率</th>
                  <th className="text-right pr-2">心率</th>
                  <th className="text-right pr-2">EF</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                <tr>
                  <td className="text-text-muted text-right pr-2">前半</td>
                  <td className="text-right pr-2">{data.first_half.avg_power}W</td>
                  <td className="text-right pr-2">{data.first_half.avg_hr}</td>
                  <td className="text-right pr-2">{data.first_half.efficiency_factor}</td>
                </tr>
                <tr>
                  <td className="text-text-muted text-right pr-2">后半</td>
                  <td className="text-right pr-2">{data.second_half.avg_power}W</td>
                  <td className="text-right pr-2">{data.second_half.avg_hr}</td>
                  <td className="text-right pr-2">{data.second_half.efficiency_factor}</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 训练学解读 */}
      <div className={`text-xs px-3 py-2 rounded-md ${c.bg} ${c.text} border ${c.border}`}>
        {data.interpretation === "excellent" && "有氧基础扎实: 长时间输出效率几乎不衰减, 这是 GC/TP 训练学标杆."}
        {data.interpretation === "normal" && "正常范围: 普通人 / 训练有素 都在这个区间, 注意补给."}
        {data.interpretation === "high" && "偏高: 糖原储备 / 水分 / 睡眠可能不足, 建议恢复后再高强度."}
        {data.interpretation === "warning" && "警告: 持续高 decoupling 是过度训练信号, 安排 1-2 天恢复日 + 监测."}
      </div>

      {/* 滑动趋势图 (如果有) */}
      {data.trend && data.trend.length > 0 && (
        <div>
          <div className="text-xs text-text-muted mb-1">滑动窗口 Decoupling (10min, 50% 重叠)</div>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data.trend} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#e2e8f0" />
              <XAxis
                dataKey="start_s"
                stroke="#86909d"
                style={{ fontSize: 10, fontFamily: "monospace" }}
                tickFormatter={(v) => `${(v / 60).toFixed(0)}m`}
              />
              <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} unit="%" />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(v) => `从 ${(v/60).toFixed(1)} min 开始`}
                formatter={(v: number) => [`${v > 0 ? "+" : ""}${v.toFixed(1)}%`, "decoupling"]}
              />
              <ReferenceArea y1={-5} y2={5} fill="#d1fae5" fillOpacity={0.3} />
              <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="2 2" />
              <Line type="monotone" dataKey="decoupling_pct" stroke="#3b82f6" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
