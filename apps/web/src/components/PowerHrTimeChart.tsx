// 训练图:功率 + 心率 + 踏频 + 海拔(对齐 TP 多线可切换)
import { useMemo, useState } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import type { Sample } from "../lib/types";

interface Props {
  samples: Sample[];
  ftp?: number | null;
}

type SeriesKey = "power" | "hr" | "cadence";

const SERIES_META: Record<SeriesKey, { label: string; color: string; yAxisId: string }> = {
  power:   { label: "功率 (W)",       color: "#6366f1", yAxisId: "power" },
  hr:      { label: "心率 (bpm)",      color: "#ef4444", yAxisId: "hr" },
  cadence: { label: "踏频 (rpm)",      color: "#10b981", yAxisId: "cadence" },
};

export function PowerHrTimeChart({ samples }: Props) {
  const [hidden, setHidden] = useState<Set<SeriesKey>>(new Set());

  // 降采样:把 1Hz 降到 ~1500 点
  const data = useMemo(() => {
    if (samples.length === 0) return [];
    const stride = Math.max(1, Math.floor(samples.length / 1500));
    return samples
      .filter((_, i) => i % stride === 0)
      .map((s) => ({
        t: s.t_offset,
        tLabel: formatTime(s.t_offset),
        power: s.power,
        hr: s.hr,
        cadence: s.cadence,
        elevation: s.elevation,
      }));
  }, [samples]);

  // 是否有踏频数据(有些设备不记录)
  const hasCadence = useMemo(
    () => samples.some((s) => s.cadence != null),
    [samples]
  );

  const toggle = (k: SeriesKey) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  if (data.length === 0) {
    return <div className="text-text-muted text-sm p-4">无样本数据</div>;
  }

  return (
    <div>
      {/* 自定义可点 legend */}
      <div className="flex items-center gap-4 px-4 py-2 text-xs">
        {(["power", "hr"] as SeriesKey[])
          .concat(hasCadence ? (["cadence"] as SeriesKey[]) : [])
          .map((k) => {
            const meta = SERIES_META[k];
            const off = hidden.has(k);
            return (
              <button
                key={k}
                onClick={() => toggle(k)}
                className="flex items-center gap-1.5 transition-opacity"
                style={{ opacity: off ? 0.35 : 1 }}
                title={off ? "点击显示" : "点击隐藏"}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: meta.color }}
                />
                <span className="text-text-secondary">{meta.label}</span>
              </button>
            );
          })}
        <span className="ml-auto text-text-muted">海拔(背景渐变)</span>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <defs>
            <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.08)" />
          <XAxis
            dataKey="tLabel"
            stroke="#86909d"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            minTickGap={50}
          />
          <YAxis
            yAxisId="power"
            stroke="#6366f1"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            unit="W"
            domain={["auto", "auto"]}
          />
          <YAxis
            yAxisId="hr"
            orientation="right"
            stroke="#ef4444"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            unit="bpm"
            domain={["auto", "auto"]}
          />
          <YAxis
            yAxisId="cadence"
            orientation="right"
            hide={hidden.has("cadence") ? false : true}
            stroke="#10b981"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            unit="rpm"
            domain={[0, 130]}
            tick={false}
            axisLine={false}
          />
          <YAxis
            yAxisId="elev"
            orientation="right"
            hide
            domain={["dataMin - 10", "dataMax + 10"]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(255,255,255,0.95)",
              border: "1px solid rgba(15,23,42,0.12)",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 12px rgba(15,23,42,0.08)",
            }}
            labelStyle={{ color: "#1a1f2e" }}
            formatter={(v: number, name: string) => {
              if (v == null) return ["—", name];
              return [v, name];
            }}
          />
          <Area
            yAxisId="elev"
            type="monotone"
            dataKey="elevation"
            fill="url(#elevGrad)"
            stroke="#06b6d4"
            strokeWidth={1}
            name="海拔 (m)"
            isAnimationActive={false}
          />
          {!hidden.has("power") && (
            <Line
              yAxisId="power"
              type="monotone"
              dataKey="power"
              stroke="#6366f1"
              strokeWidth={1.5}
              dot={false}
              name="功率 (W)"
              isAnimationActive={false}
            />
          )}
          {!hidden.has("hr") && (
            <Line
              yAxisId="hr"
              type="monotone"
              dataKey="hr"
              stroke="#ef4444"
              strokeWidth={1.5}
              dot={false}
              name="心率 (bpm)"
              isAnimationActive={false}
            />
          )}
          {hasCadence && !hidden.has("cadence") && (
            <Line
              yAxisId="cadence"
              type="monotone"
              dataKey="cadence"
              stroke="#10b981"
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              name="踏频 (rpm)"
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
