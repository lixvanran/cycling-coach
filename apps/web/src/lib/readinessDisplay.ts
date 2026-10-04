// V0.9.0: readiness 五维明细的渲染判定 —— 缺失维度必须显示"--", 不能显示 0
//
// ## 为什么抽成纯函数
//
// `DailyRecommendationCard` 是 300 行的 React 组件, 要测它就得引入
// @testing-library + jsdom。而我要测的其实只有一件事:
// **给定 breakdown 和权重, 每个维度该显示成什么**。
// 那是个纯函数, 不该绑在组件上。
//
// 抽取还有一个额外好处: 上一轮我漏掉的那个问题(标签写了"无数据",
// 数字读数还是 `0/30`)之所以能溜过去, 就是因为它**藏在 JSX 里没人测**。
// 抽出来之后"数字怎么显示"和"标签怎么显示"就必须在同一个地方定义。
//
// ## 那 4 条丢失的覆盖, 这次是第 3 次尝试
//
// - 第一次: 死在 ChatPage.test.tsx, 依赖没装, 从没跑过 (已删)
// - 第二次: Verifier 建议的 store 层测试, 拿回 2/4 (已做, 见 chatStore.test.ts)
// - 第三次: 本文件, 拿回渲染判定这一层
// 剩下 1 条(点击切 tab)确实需要 DOM, 仍然不覆盖。

/** 五个维度的展示顺序与满分, 与后端 READINESS_WEIGHTS 对应 */
export const READINESS_DIMENSIONS: { key: string; label: string; max: number }[] = [
  { key: "hrv", label: "HRV", max: 30 },
  { key: "acwr", label: "ACWR", max: 25 },
  { key: "tsb", label: "训练负荷", max: 20 },
  { key: "phase", label: "周期阶段", max: 15 },
  { key: "rpe", label: "主观疲劳", max: 10 },
];

/**
 * 单个维度的渲染判定
 *
 * 核心区分是 `has`: 维度**缺失**(没数据)和**得 0 分**(数据很差)在训练决策上
 * 是完全不同的两件事 ——
 *   - 得 0 分: "这一项很差", 该调整训练
 *   - 缺数据:   "这一项不知道", 该去补数据
 * 用同一个 `0` 渲染它们就是在骗人。
 */
export interface DimRender {
  key: string;
  label: string;
  max: number;
  /** 是否有真实数据。false 时**不可**显示成 0 分 */
  has: boolean;
  /** 显示的得分文本: 有数据 "17/30", 无数据 "--" (不是 "0/30") */
  scoreText: string;
  /** 条形图宽度百分比 */
  pct: number;
  /** 语义色。无数据走中性灰, 不用红/黄 —— 没有数据不是"表现差" */
  barClass: string;
  /** 该维度要补的话, 用户该做什么 */
  missingHint: string;
}

const MISSING_HINTS: Record<string, string> = {
  hrv: "心率带提供每日晨起 HRV, 约需 2 周建立基线",
  acwr: "需要 28 天训练史才会出现",
  tsb: "导入带功率的训练记录",
  phase: "完成一次周期设定",
  rpe: "训练后填一次主观疲劳度 (RPE 1-10)",
};

export function renderDimension(
  key: string,
  breakdown: Record<string, number> | undefined,
  max: number,
): DimRender {
  const raw = breakdown?.[key];
  const has = raw !== undefined && raw !== null;
  const v = has ? raw : 0;
  const pct = has ? Math.max(0, Math.min(100, (v / max) * 100)) : 0;
  const label = READINESS_DIMENSIONS.find((d) => d.key === key)?.label ?? key;

  return {
    key,
    label,
    max,
    has,
    // 无数据时必须是 "--"。曾经这里写成 `${v}/${m.max}`, 于是标签虽然标了
    // "无数据", 数字却还是 0/30 —— 诚实性修复做了一半, 而用户读到的恰恰是那半个。
    scoreText: has ? `${v}/${max}` : "--",
    pct,
    barClass: !has
      ? "bg-border"
      : pct >= 70
        ? "bg-status-success"
        : pct >= 40
          ? "bg-accent-warning"
          : "bg-accent-danger",
    missingHint: MISSING_HINTS[key] ?? "",
  };
}

/** 覆盖度文案: "基于 3/5 维" */
export function coverageText(cov?: {
  n_available: number;
  n_total: number;
  complete: boolean;
}): string | null {
  if (!cov || cov.complete) return null;
  return `基于 ${cov.n_available}/${cov.n_total} 维`;
}
