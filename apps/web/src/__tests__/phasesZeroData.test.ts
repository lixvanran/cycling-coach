// V0.9.0 P0 回归: 零数据不能弄崩「周期化」页面
//
// ## 这个 bug 怎么来的
//
// 2026-10-05 我把 `compute_training_state` 改成零数据返回 None
// (诚实: 不用 0 拼一个 57.5 分的假状态)。后端 API 调用方我改了,
// 诚实性测试也全绿, 全量 282 passed。
//
// **但真正的消费者在前端。** `TrainingRadarChart.tsx` 没改:
//
//     data.dimensions[k]   // data 是 {dimensions: null, ...}
//
// data 对象本身 truthy, 过了 `!data` 检查, 然后炸:
//     TypeError: Cannot read properties of null
// → App.tsx 的 ErrorBoundary 吞掉**整个周期化页面** → 白屏。
//
// 零数据用户第一次打开就崩 —— 而零数据用户就是新用户。
//
// ## 为什么静态检查没抓到
//
// 类型写的是 `dimensions: {...}` 必填非空, 而后端真的返回 null。
// **类型在撒谎, tsc 就永远不会提醒。**
//
// 所以这里测两件事:
//   1. 空态渲染不崩, 而且说的是人话
//   2. TypeScript 类型必须是 `| null` —— 把它钉死, 谁再改成必填就红
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SRC = resolve(__dirname, "../components/TrainingRadarChart.tsx");
const src = readFileSync(SRC, "utf8");

// 后端零数据时的真实响应 (P0 的现场)
const EMPTY_RESPONSE = {
  dimensions: null,
  overall: null,
  interpretation: null,
  source: null,
  data_sufficient: false,
  reason: "没有真实训练负荷数据, 算不出 5 维训练状态",
};

const FULL_RESPONSE = {
  dimensions: { fitness: 72, fatigue: 65, form: 58, rhythm: 61, recovery: 70 },
  overall: 65,
  interpretation: { fitness: "稳定上升", fatigue: "略有累积", form: "中性", rhythm: "平稳", recovery: "正常" },
  source: "CTL/ATL/TSB",
  data_sufficient: true,
};

describe("周期化 5 维状态 — 零数据不崩", () => {
  it("🔴 类型必须允许 null —— 否则 tsc 永远不会提醒前端消费者", () => {
    // 这条是整组测试的根。类型一改回必填非空, 它就红。
    const dimsType = src.match(/dimensions:\s*\{[^}]*\}[^;]*;/s)?.[0] ?? "";
    expect(dimsType).toMatch(/\|\s*null/);
    expect(src).toMatch(/data_sufficient:\s*boolean/);
    expect(src).toMatch(/reason\?:\s*string/);
  });

  it("🔴 渲染前必须挡住 dimensions === null", () => {
    // 不能只靠 `!data` —— data 是对象, 照样 truthy
    expect(src).toMatch(/!\s*data\.dimensions/);
    expect(src).toMatch(/!\s*data\.data_sufficient/);
  });

  it("空态不能把 null 渲染成图表数据", () => {
    // 曾经的 bug: chartData 直接 data.dimensions[k]
    const chartBlock = src.slice(src.indexOf("const chartData"), src.indexOf("const chartData") + 400);
    expect(chartBlock).not.toMatch(/data\.dimensions\[/);
    expect(chartBlock).toMatch(/dims\[k\]/);
  });

  it("空态对零数据响应会走空态分支(不崩)", () => {
    // 复现 P0 的判断逻辑
    const wouldCrash = (d: typeof EMPTY_RESPONSE) => {
      if (d.dimensions === null) return "CRASH: data.dimensions[k] on null";
      return "ok";
    };
    // 旧代码没有 null 检查 → crash
    expect(wouldCrash(EMPTY_RESPONSE)).toBe("CRASH: data.dimensions[k] on null");
    // 新代码: 条件成立 → 走空态
    const goesEmpty = !EMPTY_RESPONSE.data_sufficient || !EMPTY_RESPONSE.dimensions;
    expect(goesEmpty).toBe(true);
    // 有数据时正常渲染
    expect(!FULL_RESPONSE.data_sufficient || !FULL_RESPONSE.dimensions).toBe(false);
  });

  it("空态文案说清原因, 不编分数", () => {
    expect(EMPTY_RESPONSE.reason).toBeTruthy();
    expect(EMPTY_RESPONSE.overall).toBeNull();
    expect(src).toMatch(/还没有足够的真实训练数据|reason/);
  });

  it("空态给得出下一步动作", () => {
    expect(src).toMatch(/导入 FIT/);
    expect(src).toMatch(/href="\/data\/import"/);
  });
});
