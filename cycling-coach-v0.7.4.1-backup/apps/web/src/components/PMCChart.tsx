// PMC (Performance Management Chart) 组件
// 双 Y 轴:
//   左轴: CTL(慢性负荷) + ATL(急性负荷)  → 折线
//   右轴: TSB(状态)                          → 面积
// 参考 TrainingPeaks PMC 配色
import { useMemo } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from "recharts";
import type { PMCSnapshot } from "../lib/types";

interface Props {
  series: PMCSnapshot[];
  height?: number;
}

export function PMCChart({ series, height = 280 }: Props) {
  const data = useMemo(
    () =>
      series.map((s) => ({
        date: s.date,
        ctl: s.ctl,
        atl: s.atl,
        tsb: s.tsb,
        tss: s.tss,
      })),
    [series]
  );

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-40 text-text-muted text-sm">
        还没有训练数据 — 上传 .fit 文件即可生成 PMC
      </div>
    );
  }

  // 格式化日期显示(只显示月-日,每 7 天一个 tick)
  const fmtTick = (v: string) => {
    const d = new Date(v);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: -10 }}>
        <defs>
          <linearGradient id="tsbGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22c55e" stopOpacity={0.35} />
            <stop offset="50%" stopColor="#22c55e" stopOpacity={0.08} />
            <stop offset="100%" stopColor="#ef4444" stopOpacity={0.25} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={fmtTick}
          stroke="#64748b"
          fontSize={11}
          interval={Math.max(0, Math.floor(data.length / 8))}
        />
        {/* 左轴:CTL/ATL */}
        <YAxis
          yAxisId="left"
          stroke="#64748b"
          fontSize={11}
          tickLine={false}
          label={{ value: "CTL / ATL", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 10, offset: 20 }}
        />
        {/* 右轴:TSB */}
        <YAxis
          yAxisId="right"
          orientation="right"
          stroke="#64748b"
          fontSize={11}
          tickLine={false}
          label={{ value: "TSB", angle: 90, position: "insideRight", fill: "#64748b", fontSize: 10, offset: 10 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "rgba(15,23,42,0.95)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#cbd5e1" }}
          labelFormatter={(v) => `📅 ${v}`}
          formatter={(value: number, name: string) => {
            const labels: Record<string, string> = {
              ctl: "CTL 慢性",
              atl: "ATL 急性",
              tsb: "TSB 状态",
              tss: "TSS 当日",
            };
            return [value.toFixed(1), labels[name] || name];
          }}
        />
        <ReferenceLine yAxisId="right" y={0} stroke="rgba(255,255,255,0.3)" strokeDasharray="3 3" />
        {/* TSB 面积(右轴) */}
        <Area
          yAxisId="right"
          type="monotone"
          dataKey="tsb"
          stroke="#22c55e"
          strokeWidth={1.5}
          fill="url(#tsbGradient)"
          name="TSB"
        />
        {/* CTL 折线(左轴) */}
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="ctl"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          name="CTL"
        />
        {/* ATL 折线(左轴) */}
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="atl"
          stroke="#f59e0b"
          strokeWidth={2}
          dot={false}
          name="ATL"
        />
        <Legend
          verticalAlign="top"
          height={28}
          iconType="line"
          wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
