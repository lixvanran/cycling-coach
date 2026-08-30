// HR 区间分布图(柱状)
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface HRZoneChartProps {
  zones: Record<string, number>; // {"Z1": 0, "Z2": 0, ...}
  cadenceZones?: Record<string, number>;
  kind?: "hr" | "cadence";
}

const HR_COLORS: Record<string, string> = {
  Z1: "#7c8694",
  Z2: "#3b82f6",
  Z3: "#10b981",
  Z4: "#f59e0b",
  Z5: "#ef4444",
};

const CAD_COLORS = ["#7c8694", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#a855f7"];

export function HRZoneChart({ zones, cadenceZones, kind = "hr" }: HRZoneChartProps) {
  const data = Object.entries(zones).map(([k, v]) => ({
    zone: k,
    seconds: v,
    minutes: Math.round((v / 60) * 10) / 10,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
        <XAxis
          dataKey="zone"
          stroke="#5a6376"
          style={{ fontSize: 11, fontFamily: "monospace" }}
        />
        <YAxis
          stroke="#5a6376"
          style={{ fontSize: 11, fontFamily: "monospace" }}
          unit=" min"
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
          formatter={(v: number, _n, p: any) => [
            `${v} min (${p.payload.seconds}s)`,
            "持续时间",
          ]}
        />
        <Bar dataKey="minutes" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={HR_COLORS[entry.zone] || "#3b82f6"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
