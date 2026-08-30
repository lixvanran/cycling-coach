// 5 维训练状态雷达图
//
// 借鉴: Joe Friel Form Chart (The Cyclist's Training Bible) + Recharts RadarChart
// 5 维: 体能 / 疲劳 / 状态 / 节奏 / 恢复 (0-100)

import { useEffect, useState } from "react";
import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface TrainingState {
  dimensions: {
    fitness: number;
    fatigue: number;
    form: number;
    rhythm: number;
    recovery: number;
  };
  overall: number;
  interpretation: Record<string, string>;
  source: string;
}

const DIM_LABELS: Record<keyof TrainingState["dimensions"], string> = {
  fitness: "体能 (CTL)",
  fatigue: "恢复 (ATL反)",
  form: "状态 (TSB)",
  rhythm: "节奏 (ramp)",
  recovery: "反馈 (RPE)",
};

function colorByScore(s: number): string {
  if (s >= 80) return "#10b981"; // green
  if (s >= 65) return "#3b82f6"; // blue
  if (s >= 50) return "#eab308"; // yellow
  if (s >= 35) return "#f97316"; // orange
  return "#ef4444"; // red
}

export function TrainingRadarChart() {
  const [data, setData] = useState<TrainingState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/race-prep/training-state")
      .then((r) => r.json())
      .then((j) => {
        if (j.error) throw new Error(j.error);
        setData(j);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <div className="text-sm text-slate-500">训练状态加载中…</div>
      </div>
    );
  }
  if (err || !data) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6">
        <div className="text-sm text-red-600">加载失败: {err}</div>
      </div>
    );
  }

  const chartData = (Object.keys(DIM_LABELS) as (keyof TrainingState["dimensions"])[]).map(
    (k) => ({
      dim: DIM_LABELS[k],
      value: data.dimensions[k],
    })
  );

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <h3 className="text-base font-semibold text-slate-800">5 维训练状态</h3>
          <p className="text-xs text-slate-500 mt-0.5">借鉴 Joe Friel Form Chart</p>
        </div>
        <div className="text-right">
          <div
            className="text-2xl font-bold tabular-nums"
            style={{ color: colorByScore(data.overall) }}
          >
            {data.overall}
          </div>
          <div className="text-xs text-slate-500">综合分</div>
        </div>
      </div>

      <div className="h-64 -mx-2">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsRadar cx="50%" cy="50%" outerRadius="75%" data={chartData}>
            <PolarGrid stroke="#cbd5e1" />
            <PolarAngleAxis
              dataKey="dim"
              tick={{ fill: "#475569", fontSize: 11 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fill: "#94a3b8", fontSize: 9 }}
              tickCount={6}
            />
            <Radar
              name="当前"
              dataKey="value"
              stroke="#1621FF"
              fill="#1621FF"
              fillOpacity={0.35}
              isAnimationActive
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "white",
                border: "1px solid #e2e8f0",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(v: number) => [`${v} / 100`, "得分"]}
            />
          </RechartsRadar>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-5 gap-1 mt-3 text-center text-[10px]">
        {(Object.keys(DIM_LABELS) as (keyof TrainingState["dimensions"])[]).map((k) => {
          const score = data.dimensions[k];
          return (
            <div key={k}>
              <div
                className="text-base font-bold tabular-nums"
                style={{ color: colorByScore(score) }}
              >
                {score}
              </div>
              <div className="text-slate-500 mt-0.5 leading-tight">
                {data.interpretation[k] || ""}
              </div>
            </div>
          );
        })}
      </div>

      <div className="text-[10px] text-slate-400 mt-3 pt-2 border-t border-slate-100">
        {data.source}
      </div>
    </div>
  );
}
