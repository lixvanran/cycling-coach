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
  // 🔴 V0.9.0: 原来这几个字段都写成必填非空, 于是**类型层面就在说谎** ——
  // 后端零数据时真的返回 null, 但 tsc 永远不会提醒我。
  // 这就是 P0 能一路绿灯走到用户面前的原因: 类型不是注释, 是编译器契约。
  //
  // 现在老老实实标成 `| null`, 让"数据不足"成为**类型系统里的合法状态**,
  // 而不是运行到一半才炸。
  dimensions: {
    fitness: number;
    fatigue: number;
    form: number;
    rhythm: number;
    recovery: number;
  } | null;
  overall: number | null;
  interpretation: Record<string, string> | null;
  source: string | null;
  /** 后端明确告诉我们数据够不够 —— 零数据时 false */
  data_sufficient: boolean;
  /** 数据不足时, 人话解释为什么 */
  reason?: string;
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
      <div className="rounded border border-border bg-white p-6">
        <div className="text-sm text-text-secondary">训练状态加载中…</div>
      </div>
    );
  }
  if (err || !data) {
    return (
      <div className="rounded border border-border bg-status-danger p-6">
        <div className="text-sm text-accent-danger">加载失败: {err}</div>
      </div>
    );
  }

  // V0.9.0 P0: 后端零数据时返回 dimensions: null (诚实地不编 5 维分数)。
  // 我只修了后端调用方, 忘了真正的消费者是这个组件 —— 于是:
  //   `data` 对象是 truthy, 过了上面的 !data 检查,
  //   然后 `data.dimensions[k]` → TypeError: Cannot read properties of null
  //   → App.tsx 的 ErrorBoundary 吞掉整个「周期化」页面。
  //
  // **零数据用户第一次打开就白屏 —— 而零数据用户就是新用户。**
  //
  // 教训: 改后端契约 = 后端调用方 + 前端消费者 + 类型, 三层一起改。
  // 光改一层就会把 bug 推到下一层, 而且藏得比原来更深。
  if (
    !data.data_sufficient ||
    !data.dimensions ||
    !data.interpretation ||
    data.overall === null
  ) {
    return (
      <div className="rounded border border-border bg-white p-6">
        <h3 className="text-base font-semibold text-text-primary">5 维训练状态</h3>
        <p className="text-xs text-text-secondary mt-1">
          {data.reason || "还没有足够的真实训练数据"}
        </p>
        <p className="text-xs text-text-muted mt-3">
          这 5 个维度要靠真实训练数据推算, 缺数据时我们不会给一个猜的分数 ——
          一个凭空来的"体能 72 分", 你没法照着它骑车。
        </p>
        <a
          href="/data/import"
          className="inline-block mt-4 px-3 py-1.5 text-xs rounded
                     bg-accent-primary text-white hover:opacity-90"
        >
          导入 FIT
        </a>
      </div>
    );
  }

  // 上面那一个 if 已经把所有 null 字段一次挡掉了, 所以到这里
  // TypeScript 能自己推导出 dims / overall / interpretation 都是非空。
  //
  // ⚠️ 这里**故意不写 `as`**。`as` 是把"诚实的类型"重新按回"我猜它非空" ——
  // CLAUDE.md 铁律三写着"类型不是注释, 是编译器契约", 而 `as` 恰恰在推翻它。
  // Verifier 复审时把两处 `as number` 挑出来了: 自己写的规矩自己没守。
  //
  // 让 tsc 自己证明, 比我断言它非空可靠。
  const { dimensions: dims, overall, interpretation } = data;
  const chartData = (Object.keys(DIM_LABELS) as (keyof typeof DIM_LABELS)[]).map((k) => ({
    dim: DIM_LABELS[k],
    value: dims[k],
  }));

  return (
    <div className="rounded border border-border bg-white p-5">
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <h3 className="text-base font-semibold text-text-primary">5 维训练状态</h3>
          <p className="text-xs text-text-secondary mt-0.5">借鉴 Joe Friel Form Chart</p>
        </div>
        <div className="text-right">
          <div
            className="text-2xl font-bold tabular-nums"
            style={{ color: colorByScore(overall) }}
          >
            {data.overall}
          </div>
          <div className="text-xs text-text-secondary">综合分</div>
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
        {(Object.keys(DIM_LABELS) as (keyof typeof DIM_LABELS)[]).map((k) => {
          const score = dims[k];
          return (
            <div key={k}>
              <div
                className="text-base font-bold tabular-nums"
                style={{ color: colorByScore(score) }}
              >
                {score}
              </div>
              <div className="text-text-secondary mt-0.5 leading-tight">
                {interpretation[k] || ""}
              </div>
            </div>
          );
        })}
      </div>

      <div className="text-[10px] text-text-muted mt-3 pt-2 border-t border-slate-100">
        {data.source}
      </div>
    </div>
  );
}
