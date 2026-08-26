// 功率曲线图 (MMP) — V0.3.4 升级
//
// 接受新接口(后端 /api/activities/{id}/power-curve 返回):
// {
//   points: [{duration_s, watts}],
//   ftp_estimate,
//   key_durations: {5s, 1min, 5min, 20min, 60min},
// }
// 也兼容旧 Record<string, number> 格式
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface PowerCurveNew {
  points?: { duration_s: number; watts: number }[];
  ftp_estimate?: number | null;
  key_durations?: Record<string, number | null>;
}

interface PowerCurveChartProps {
  // 新接口
  data?: PowerCurveNew;
  // 旧接口(兼容)
  powerCurve?: Record<string, number>;
  ftp?: number | null;
}

export function PowerCurveChart({ data, powerCurve, ftp }: PowerCurveChartProps) {
  // 统一转成 [{seconds, label, watts}]
  let points: { seconds: number; label: string; watts: number }[] = [];
  let inferredFtp: number | null = null;

  if (data?.points && data.points.length > 0) {
    points = data.points
      .filter((p) => p.watts && p.watts > 0)
      .map((p) => ({
        seconds: p.duration_s,
        label: formatDuration(p.duration_s),
        watts: p.watts,
      }))
      .sort((a, b) => a.seconds - b.seconds);
    inferredFtp = data.ftp_estimate ?? null;
  } else if (powerCurve && Object.keys(powerCurve).length > 0) {
    points = Object.entries(powerCurve)
      .map(([k, v]) => {
        const seconds = parseInt(k.replace("s", "")) || 0;
        return { seconds, label: formatDuration(seconds), watts: v };
      })
      .sort((a, b) => a.seconds - b.seconds);
  }

  const ftpLine = ftp ?? inferredFtp;

  if (points.length === 0) {
    return <div className="text-text-muted text-sm p-4">无功率数据</div>;
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={points} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#252b3b" />
          <XAxis
            dataKey="label"
            stroke="#5a6376"
            style={{ fontSize: 11, fontFamily: "monospace" }}
          />
          <YAxis
            stroke="#5a6376"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            unit="W"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1a2030",
              border: "1px solid #2e3548",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: "#e8ecf2" }}
            itemStyle={{ color: "#3b82f6" }}
            formatter={(v: number) => [`${v} W`, "平均功率"]}
          />
          {ftpLine && (
            <ReferenceLine
              y={ftpLine}
              stroke="#10b981"
              strokeDasharray="3 3"
              label={{ value: `FTP ${ftpLine}W`, position: "right", fill: "#10b981", fontSize: 10 }}
            />
          )}
          <Line
            type="monotone"
            dataKey="watts"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ fill: "#3b82f6", r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
      {/* 关键时长(5s/1min/5min/20min/60min) - 视觉化 */}
      {data?.key_durations && (
        <div className="grid grid-cols-5 gap-2 mt-3 pt-3 border-t border-border">
          {Object.entries(data.key_durations).map(([k, v]) => (
            <div key={k} className="text-center">
              <div className="text-[10px] text-text-muted">{k}</div>
              <div className="text-sm font-bold text-accent font-mono">
                {v ? `${v}W` : "—"}
              </div>
            </div>
          ))}
        </div>
      )}
      {inferredFtp && (
        <div className="mt-2 text-[10px] text-text-muted text-center">
          💡 估算 FTP <span className="text-emerald-300 font-bold">{inferredFtp}W</span>
          <span className="ml-1">(基于 20min 最佳功率 × 0.95)</span>
        </div>
      )}
    </div>
  );
}

function formatDuration(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}
