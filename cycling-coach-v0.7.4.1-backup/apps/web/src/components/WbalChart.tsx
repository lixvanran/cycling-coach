// W'bal 曲线 (Skiba 模型) — V0.6 GoldenCheetah 对标
import { useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, ReferenceArea } from "recharts";

export interface WbalData {
  activity_id: number;
  cp: number;
  w_prime: number;
  wbal_curve: number[];
  min_wbal: number;
  min_wbal_at_s: number;
  min_wbal_pct: number;
  depleted: boolean;
  depletion_at_s: number | null;
  critical_events: Array<{
    start_s: number;
    end_s: number;
    duration_s: number;
    min_wbal: number;
    min_wbal_pct: number;
  }>;
  match_potential: number;
  tau_s: number;
}

interface WbalChartProps {
  wbal: WbalData | null | undefined;
}

export function WbalChart({ wbal }: WbalChartProps) {
  const data = useMemo(() => {
    if (!wbal || !wbal.wbal_curve) return [];
    return wbal.wbal_curve.map((v, i) => ({
      t: i,
      tMin: +(i / 60).toFixed(2),
      wbal: v,
      wbalKJ: +(v / 1000).toFixed(2),
    }));
  }, [wbal]);

  if (!wbal) {
    return <div className="text-text-muted text-sm p-4">W'bal 数据未加载</div>;
  }
  if (data.length === 0) {
    return <div className="text-text-muted text-sm p-4">活动无功率数据, 无法计算 W'bal</div>;
  }

  const wPrimeKJ = wbal.w_prime / 1000;
  const minKJ = wbal.min_wbal / 1000;
  const redZone = wbal.w_prime * 0.30;  // 30% W' 警戒线
  const redZoneKJ = redZone / 1000;

  return (
    <div className="space-y-3">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <XAxis
            dataKey="tMin"
            stroke="#86909d"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            label={{ value: "时间 (min)", position: "insideBottom", offset: -2, style: { fontSize: 11, fill: "#86909d" } }}
          />
          <YAxis
            stroke="#86909d"
            style={{ fontSize: 11, fontFamily: "monospace" }}
            label={{ value: "W'bal (kJ)", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#86909d" } }}
            domain={[0, wPrimeKJ * 1.05]}
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
            itemStyle={{ color: "#1a1f2e" }}
            formatter={(v: number) => [`${v.toFixed(2)} kJ`, "W'bal"]}
            labelFormatter={(label) => `时间 ${label} min`}
          />
          {/* 红色警戒区 (W'bal < 30% W') */}
          <ReferenceArea y1={0} y2={redZoneKJ} fill="#fee2e2" fillOpacity={0.4} />
          <ReferenceLine y={redZoneKJ} stroke="#dc2626" strokeDasharray="3 3" label={{ value: "30% 警戒线", position: "right", style: { fontSize: 10, fill: "#dc2626" } }} />
          <ReferenceLine y={wPrimeKJ} stroke="#10b981" strokeDasharray="3 3" label={{ value: `W'=${wPrimeKJ}kJ`, position: "right", style: { fontSize: 10, fill: "#10b981" } }} />
          {/* 最低点标记 */}
          {wbal.min_wbal_at_s > 0 && (
            <ReferenceLine
              x={+(wbal.min_wbal_at_s / 60).toFixed(2)}
              stroke="#7c2d12"
              strokeDasharray="2 2"
              label={{ value: `最低 ${minKJ.toFixed(1)}kJ @ ${(wbal.min_wbal_at_s/60).toFixed(1)}min`, position: "top", style: { fontSize: 10, fill: "#7c2d12" } }}
            />
          )}
          <Line type="monotone" dataKey="wbalKJ" stroke="#3b82f6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>

      {/* 关键指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <Stat label="CP" value={`${wbal.cp}W`} sub={`τ=${wbal.tau_s}s`} />
        <Stat label="W'" value={`${wPrimeKJ}kJ`} sub={`起始 ${wPrimeKJ}kJ`} />
        <Stat
          label="最低 W'bal"
          value={`${minKJ.toFixed(1)} kJ`}
          sub={`${wbal.min_wbal_pct.toFixed(1)}% W' @ ${(wbal.min_wbal_at_s/60).toFixed(1)}min`}
          color={wbal.min_wbal_pct < 30 ? "text-rose-600" : wbal.min_wbal_pct < 50 ? "text-amber-600" : "text-emerald-600"}
        />
        <Stat
          label="比赛匹配潜力"
          value={`${(wbal.match_potential * 100).toFixed(0)}%`}
          sub={wbal.depleted ? "⚠️ 已耗尽" : wbal.match_potential > 0.7 ? "剩余少, 难再加速" : "尚有余力"}
          color={wbal.depleted ? "text-rose-700 font-semibold" : wbal.match_potential > 0.7 ? "text-amber-600" : "text-emerald-600"}
        />
      </div>

      {/* 临界事件 */}
      {wbal.critical_events && wbal.critical_events.length > 0 && (
        <div className="text-xs bg-rose-50 border border-rose-200 rounded-md p-2">
          <div className="font-semibold text-rose-700 mb-1">⚠️ 临界事件 (W'bal &lt; 30% W'):</div>
          {wbal.critical_events.map((e, i) => (
            <div key={i} className="text-rose-600">
              • {e.start_s}s → {e.end_s}s ({e.duration_s}s), 最低 {e.min_wbal}J ({e.min_wbal_pct}%)
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub, color }: { label: string; value: string; sub: string; color?: string }) {
  return (
    <div className="px-3 py-2 rounded-md bg-slate-50">
      <div className="text-text-muted">{label}</div>
      <div className={`text-lg font-semibold ${color || "text-slate-700"}`}>{value}</div>
      <div className="text-[10px] text-text-muted">{sub}</div>
    </div>
  );
}
