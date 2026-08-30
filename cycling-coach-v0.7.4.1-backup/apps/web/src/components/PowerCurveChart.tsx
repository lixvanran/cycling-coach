// 功率曲线图 (MMP) — V0.3.4 升级 + V0.7.1 加时间窗切换
//
// 接受新接口(后端 /api/activities/{id}/power-curve 返回):
// {
//   points: [{duration_s, watts}],
//   ftp_estimate,
//   key_durations: {5s, 1min, 5min, 20min, 60min},
// }
// 也兼容旧 Record<string, number> 格式
import { useState, useMemo } from "react";
import clsx from "clsx";
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

// V0.7.1: 时间窗预设 (训练学场景)
// 借鉴 Coggan 7 区 + Seiler 80/20 强度区间
const WINDOW_PRESETS: Record<string, { label: string; from: number; to: number; description: string }> = {
  all: { label: "全部", from: 0, to: 86400, description: "5s ~ 24h 全曲线" },
  sprint: { label: "短时爆发", from: 5, to: 60, description: "5s ~ 1min, 神经肌肉, 冲刺能力" },
  vo2: { label: "VO2 力量", from: 60, to: 300, description: "1 ~ 5min, VO2max, 5min 全力" },
  ftp: { label: "FTP 阈值", from: 300, to: 1800, description: "5 ~ 30min, 阈值, 20min 全力估 FTP" },
  endurance: { label: "耐力长时", from: 1800, to: 7200, description: "30min ~ 2h, 耐力, TT 比赛" },
  ultra: { label: "超长距离", from: 7200, to: 86400, description: "2h+, Gran Fondo 完赛能力" },
};

export function PowerCurveChart({ data, powerCurve, ftp }: PowerCurveChartProps) {
  const [windowKey, setWindowKey] = useState<keyof typeof WINDOW_PRESETS>("all");

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

  // V0.7.1: 按时间窗过滤
  const filteredPoints = useMemo(() => {
    const win = WINDOW_PRESETS[windowKey];
    if (!win) return points;
    if (windowKey === "all") return points;
    return points.filter((p) => p.seconds >= win.from && p.seconds <= win.to);
  }, [points, windowKey]);

  const ftpLine = ftp ?? inferredFtp;

  if (points.length === 0) {
    return <div className="text-text-muted text-sm p-4">无功率数据</div>;
  }

  return (
    <div>
      {/* V0.7.1: 时间窗切换按钮 */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {Object.entries(WINDOW_PRESETS).map(([k, w]) => (
          <button
            key={k}
            type="button"
            onClick={() => setWindowKey(k as keyof typeof WINDOW_PRESETS)}
            title={w.description}
            className={clsx(
              "px-2.5 py-1 rounded text-xs font-medium transition",
              windowKey === k
                ? "bg-accent-primary text-white shadow"
                : "bg-bg-input text-text-muted hover:bg-bg-hover hover:text-text-primary"
            )}
          >
            {w.label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={filteredPoints} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
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
