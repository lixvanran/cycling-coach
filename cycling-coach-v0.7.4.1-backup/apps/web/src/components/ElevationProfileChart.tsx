// 海拔剖面图 (V0.6.1 增强) — 对标 Strava/GC/TP 都有
// 显示整段活动海拔变化, 含累计爬升标记
import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
  Label,
} from "recharts";
import type { Sample } from "../lib/types";

interface Props {
  samples: Sample[];
  height?: number;
  showClimbMarkers?: boolean;
}

export function ElevationProfileChart({ samples, height = 200, showClimbMarkers = true }: Props) {
  const data = useMemo(() => {
    if (!samples) return [];
    return samples
      .filter((s) => s.elevation != null)
      .map((s) => ({
        t: s.t_offset,
        tMin: +(s.t_offset / 60).toFixed(2),
        km: 0,  // 距离需要从 samples 推算, 这里简化为 0 (X 轴用时间)
        elev: s.elevation,
      }));
  }, [samples]);

  // 找主要爬升段 (海拔差 > 10m 连续 30s+)
  const climbSegments = useMemo(() => {
    if (!data.length || !showClimbMarkers) return [];
    const segs: Array<{ tMin: number; gain: number; peak: number }> = [];
    let i = 0;
    while (i < data.length) {
      // 找连续上升段
      const start = data[i];
      let j = i + 1;
      let peak = start.elev ?? 0;
      let gain = 0;
      while (j < data.length) {
        const cur = data[j].elev ?? 0;
        const prev = data[j - 1].elev ?? 0;
        const diff = cur - prev;
        if (diff > 0.3) {
          // 上升趋势
          gain += diff;
          peak = Math.max(peak, cur);
          j++;
        } else {
          break;
        }
      }
      if (gain >= 10 && j - i >= 30) {
        segs.push({ tMin: data[i].tMin ?? 0, gain: Math.round(gain), peak: Math.round(peak) });
      }
      i = j;
    }
    return segs;
  }, [data, showClimbMarkers]);

  if (!data.length) {
    return (
      <div className="text-text-muted text-sm p-4 text-center">
        无海拔数据 (该 FIT 文件不含 GPS / 气压计)
      </div>
    );
  }

  const elevMin = Math.min(...data.map((d) => d.elev ?? 0));
  const elevMax = Math.max(...data.map((d) => d.elev ?? 0));
  const totalGain = data.reduce((sum, d, i) => {
    if (i === 0) return 0;
    const cur = d.elev ?? 0;
    const prev = data[i - 1].elev ?? 0;
    return sum + Math.max(0, cur - prev);
  }, 0);
  const totalLoss = data.reduce((sum, d, i) => {
    if (i === 0) return 0;
    const cur = d.elev ?? 0;
    const prev = data[i - 1].elev ?? 0;
    return sum + Math.max(0, prev - cur);
  }, 0);

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <defs>
            <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#a16207" stopOpacity={0.7} />
              <stop offset="100%" stopColor="#a16207" stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="tMin"
            stroke="#86909d"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            label={{ value: "时间 (min)", position: "insideBottom", offset: -2, style: { fontSize: 11, fill: "#86909d" } }}
          />
          <YAxis
            stroke="#86909d"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            domain={[Math.floor(elevMin - 5), Math.ceil(elevMax + 5)]}
            label={{ value: "海拔 (m)", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#86909d" } }}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(v) => `时间 ${v} min`}
            formatter={(v: number) => [`${v.toFixed(1)} m`, "海拔"]}
          />
          <Area type="monotone" dataKey="elev" stroke="#a16207" strokeWidth={1.5} fill="url(#elevGrad)" isAnimationActive={false} />
          {climbSegments.slice(0, 5).map((seg, i) => (
            <ReferenceLine
              key={i}
              x={seg.tMin}
              stroke="#dc2626"
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>

      {/* 统计条 */}
      <div className="flex flex-wrap gap-3 text-xs">
        <span className="px-2 py-1 rounded bg-amber-50 text-amber-700">
          累计爬升 +{Math.round(totalGain)} m
        </span>
        <span className="px-2 py-1 rounded bg-sky-50 text-sky-700">
          累计下降 -{Math.round(totalLoss)} m
        </span>
        <span className="px-2 py-1 rounded bg-slate-50 text-slate-700">
          最高 {Math.round(elevMax)} m
        </span>
        <span className="px-2 py-1 rounded bg-slate-50 text-slate-700">
          最低 {Math.round(elevMin)} m
        </span>
        {climbSegments.length > 0 && (
          <span className="px-2 py-1 rounded bg-rose-50 text-rose-700">
            识别 {climbSegments.length} 个爬升 (≥10m, 红虚线标注)
          </span>
        )}
      </div>
    </div>
  );
}
