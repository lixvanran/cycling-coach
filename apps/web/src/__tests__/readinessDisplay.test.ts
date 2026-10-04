import { describe, it, expect } from "vitest";
import {
  renderDimension,
  coverageText,
  READINESS_DIMENSIONS,
} from "../lib/readinessDisplay";

// 期望值全部写在这里, 不从被测模块导入。
// 从实现导出期望值再由自己的测试消费 = 自己测自己, 改期望值和改实现是
// 同一次编辑, diff 上看不出区别。这里 DRY 是错的直觉, 重复是故意的。
const FULL: Record<string, number> = {
  hrv: 30, acwr: 25, tsb: 20, phase: 15, rpe: 10,
};
const PARTIAL: Record<string, number> = { tsb: 5, phase: 12 };
const REAL_ZERO: Record<string, number> = { hrv: 0, tsb: 20 };

describe("renderDimension · 缺失 vs 0 分必须区分", () => {
  // 这条直接对应被 Verifier 抓到的那半个修复:
  // 标签写了"无数据", 数字却还是 0/30 —— 而数字才是格子里最显眼的东西。
  it("缺失维度显示 --, 绝不是 0/30", () => {
    for (const d of READINESS_DIMENSIONS) {
      if (d.key in PARTIAL) continue;
      const r = renderDimension(d.key, PARTIAL, d.max);
      expect(r.has).toBe(false);
      expect(r.scoreText).toBe("--");
      expect(r.scoreText).not.toBe(`0/${d.max}`);
      expect(r.pct).toBe(0);
    }
  });

  it("真的 0 分时显示 0/30, 不是 --", () => {
    // 这是最容易改坏的反向断言: 如果实现一律返回 "--",
    // "缺失显示 --" 那条照样绿, 但真实的 0 分就被吞掉了。
    const r = renderDimension("hrv", REAL_ZERO, 30);
    expect(r.has).toBe(true);
    expect(r.scoreText).toBe("0/30");
    expect(r.pct).toBe(0);
  });

  it("0 分和缺失的条形色不同 —— 没有数据不是表现差", () => {
    const missing = renderDimension("hrv", PARTIAL, 30);
    const zero = renderDimension("hrv", REAL_ZERO, 30);
    expect(missing.barClass).toBe("bg-border");
    expect(zero.barClass).not.toBe("bg-border");
    // 0 分是真的差, 该用警示色
    expect(zero.barClass).toBe("bg-accent-danger");
  });

  it("缺 breakdown 整体时全部维度都显示 --", () => {
    for (const d of READINESS_DIMENSIONS) {
      expect(renderDimension(d.key, undefined, d.max).scoreText).toBe("--");
    }
  });
});

describe("renderDimension · 正常值", () => {
  it("五维齐全时逐个显示真实分数", () => {
    expect(renderDimension("hrv", FULL, 30).scoreText).toBe("30/30");
    expect(renderDimension("acwr", FULL, 25).scoreText).toBe("25/25");
    expect(renderDimension("tsb", FULL, 20).scoreText).toBe("20/20");
    expect(renderDimension("phase", FULL, 15).scoreText).toBe("15/15");
    expect(renderDimension("rpe", FULL, 10).scoreText).toBe("10/10");
  });

  it("部分分数的百分比正确", () => {
    expect(renderDimension("tsb", PARTIAL, 20).pct).toBe(25);
    expect(renderDimension("phase", PARTIAL, 15).pct).toBe(80);
  });

  it("分档配色边界", () => {
    const c = (v: number, max: number) => renderDimension("hrv", { hrv: v }, max).barClass;
    expect(c(30, 30)).toBe("bg-status-success"); // 100%
    expect(c(21, 30)).toBe("bg-status-success"); // 70%
    expect(c(20, 30)).toBe("bg-accent-warning"); // 66.7% -> 警告
    expect(c(12, 30)).toBe("bg-accent-warning"); // 40%
    expect(c(11, 30)).toBe("bg-accent-danger");  // 36.7% -> 危险
  });

  it("百分比被夹在 0-100, 不会画出超宽条", () => {
    expect(renderDimension("hrv", { hrv: 999 }, 30).pct).toBe(100);
    expect(renderDimension("hrv", { hrv: -5 }, 30).pct).toBe(0);
  });

  it("null 也算缺失, 不是 0", () => {
    // JSON 里缺失字段可能是 null 而不是 undefined —— 序列化过的接口会这样
    const r = renderDimension("hrv", { hrv: null as unknown as number }, 30);
    expect(r.has).toBe(false);
    expect(r.scoreText).toBe("--");
  });
});

describe("coverageText", () => {
  it("不完整时给出 N/M 维", () => {
    expect(coverageText({ n_available: 3, n_total: 5, complete: false })).toBe("基于 3/5 维");
  });

  it("完整时不显示覆盖度", () => {
    expect(coverageText({ n_available: 5, n_total: 5, complete: true })).toBeNull();
  });

  it("没有 coverage 数据时不显示", () => {
    expect(coverageText(undefined)).toBeNull();
  });
});
