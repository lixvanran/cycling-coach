// 功率区间分布 (Coggan 7 区 + GoldenCheetah-style 详细) — V0.6
// 接收 power-zones-detailed API 输出: { zones: [{code, name, color, seconds, percent_time, avg_power, kj, ...}], summary: {...} }
// 也支持老格式: { "Z1": seconds, ... }
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface DetailedZone {
  code: string;
  name: string;
  color: string;
  lo_pct: number;
  hi_pct: number;
  seconds: number;
  percent_time: number;
  percent_distance: number;
  avg_power: number | null;
  max_power: number | null;
  kj: number;
}

interface ZoneSummary {
  polarization_index: number;
  sweet_spot_seconds: number;
  above_ftp_seconds: number;
  easy_seconds: number;
  hard_seconds: number;
}

interface DetailedZones {
  ftp: number;
  total_seconds: number;
  total_kj: number;
  zones: DetailedZone[];
  summary: ZoneSummary;
}

interface PowerZoneChartProps {
  zones: DetailedZones | Record<string, number> | null | undefined;
}

const ZONE_COLORS: Record<string, string> = {
  Z1: "#9ca3af",  // 灰
  Z2: "#3b82f6",  // 蓝
  Z3: "#10b981",  // 绿
  Z4: "#f59e0b",  // 橙黄
  Z5: "#ef4444",  // 红
  Z6: "#dc2626",  // 深红
  Z7: "#7c2d12",  // 棕
};

const ZONE_LABELS: Record<string, string> = {
  Z1: "Z1 恢复",
  Z2: "Z2 耐力",
  Z3: "Z3 节奏",
  Z4: "Z4 阈值",
  Z5: "Z5 VO2",
  Z6: "Z6 无氧",
  Z7: "Z7 神经",
};

function isDetailed(z: any): z is DetailedZones {
  return z && typeof z === "object" && Array.isArray(z.zones);
}

export function PowerZoneChart({ zones }: PowerZoneChartProps) {
  // 老格式兼容: { "Z1": 100, "Z2": 200, ... }
  if (!isDetailed(zones)) {
    if (!zones) {
      return <div className="text-text-muted text-sm p-4">无功率区间数据(需先设置 FTP)</div>;
    }
    const data = Object.entries(zones).map(([k, v]) => ({
      code: k,
      name: ZONE_LABELS[k] || k,
      color: ZONE_COLORS[k] || "#94a3b8",
      seconds: v,
      percent_time: 0,
      avg_power: null,
      kj: 0,
    }));
    return <BarChartView data={data} />;
  }

  // 新格式: detailed
  const data = zones.zones.map((z) => ({
    code: z.code,
    name: z.name,
    color: z.color || ZONE_COLORS[z.code] || "#94a3b8",
    seconds: z.seconds,
    percent_time: z.percent_time,
    avg_power: z.avg_power,
    kj: z.kj,
  }));

  return (
    <div className="space-y-3">
      <BarChartView data={data} />
      <SummaryView summary={zones.summary} totalKj={zones.total_kj} ftp={zones.ftp} />
    </div>
  );
}

function BarChartView({ data }: { data: any[] }) {
  if (data.length === 0) {
    return <div className="text-text-muted text-sm p-4">无功率区间数据(需先设置 FTP)</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
        <XAxis dataKey="code" stroke="#86909d" style={{ fontSize: 11, fontFamily: "monospace" }} />
        <YAxis stroke="#86909d" style={{ fontSize: 11, fontFamily: "monospace" }} unit=" min" />
        <Tooltip
          contentStyle={{
            backgroundColor: "rgba(255,255,255,0.95)",
            border: "1px solid rgba(15,23,42,0.12)",
            borderRadius: 8,
            fontSize: 12,
            boxShadow: "0 4px 12px rgba(15,23,42,0.08)",
          }}
          labelStyle={{ color: "#1a1f2e" }}
          itemStyle={{ color: "#1a1f2e" }}
          formatter={(_v: number, _n, p: any) => {
            const lines = [
              `${p.payload.seconds}s (${(p.payload.seconds / 60).toFixed(1)} min, ${p.payload.percent_time}%)`,
            ];
            if (p.payload.avg_power) lines.push(`区间均功 ${p.payload.avg_power}W`);
            if (p.payload.kj) lines.push(`做功 ${p.payload.kj} kJ`);
            return [lines.join(" / "), p.payload.name];
          }}
        />
        <Bar dataKey={d => d.seconds / 60} radius={[4, 4, 0, 0]} name="时间">
          {data.map((entry) => (
            <Cell key={entry.code} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SummaryView({ summary, totalKj, ftp }: { summary: ZoneSummary; totalKj: number; ftp: number }) {
  const pol = summary.polarization_index;
  const polLabel =
    pol >= 0.80 ? "极化" : pol >= 0.65 ? "偏极化" : pol >= 0.50 ? "中等" : "金字塔型";
  const polColor =
    pol >= 0.65 ? "text-emerald-600" : pol >= 0.50 ? "text-amber-600" : "text-rose-600";

  const ssMin = (summary.sweet_spot_seconds / 60).toFixed(1);
  const aboveMin = (summary.above_ftp_seconds / 60).toFixed(1);
  const easyMin = (summary.easy_seconds / 60).toFixed(1);
  const hardMin = (summary.hard_seconds / 60).toFixed(1);

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
      <div className="px-3 py-2 rounded-md bg-slate-50">
        <div className="text-text-muted">极化指数</div>
        <div className={`text-lg font-semibold ${polColor}`}>
          {(pol * 100).toFixed(1)}% <span className="text-xs text-text-muted font-normal">{polLabel}</span>
        </div>
      </div>
      <div className="px-3 py-2 rounded-md bg-slate-50">
        <div className="text-text-muted">甜蜜点 (88-94% FTP)</div>
        <div className="text-lg font-semibold text-slate-700">{ssMin} min</div>
      </div>
      <div className="px-3 py-2 rounded-md bg-slate-50">
        <div className="text-text-muted">Above FTP</div>
        <div className="text-lg font-semibold text-rose-600">{aboveMin} min</div>
      </div>
      <div className="px-3 py-2 rounded-md bg-slate-50">
        <div className="text-text-muted">总做功 / FTP</div>
        <div className="text-lg font-semibold text-slate-700">{totalKj.toFixed(0)} kJ / {ftp}W</div>
      </div>
    </div>
  );
}
