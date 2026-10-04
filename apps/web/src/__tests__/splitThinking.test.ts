/**
 * 思维链 / 回答切分 —— 真测试
 *
 * V0.9.0 之前这段逻辑内嵌在 ChatPage 的流式回调里, **零测试**。
 * 而它决定用户打开聊天页看到的第一屏是"答案"还是"模型的内部分析" ——
 * 是整个 AI 体验里用户感知最强的一处。
 *
 * 仓库原来有个 src/__tests__/ChatPage.test.tsx, 但它:
 *   - 依赖 @testing-library / jsdom, 而项目**根本没装**这些依赖
 *   - package.json 里也没有 test 脚本
 * 也就是说它是**死代码**, 而且因为 import 了不存在的模块, tsc 每次报 3 个错,
 * 直接把 `npm run build` 卡死。
 * 现在逻辑抽成纯函数 (lib/splitThinking.ts), node 环境就能测, 不需要 DOM。
 *
 * ## 一条重要的自我约束
 *
 * **期望值全部写在这个文件里, 不在被测模块里。**
 *
 * 我第一版把用例表 (SPLIT_CASES) 放在 splitThinking.ts 里, 测试 import 它再遍历。
 * 那样看起来 DRY, 实际是**自己测自己**: 谁改一下模块里的期望值, 测试就跟着绿,
 * 而且改得悄无声息。这正是 V0.9.0 这几轮反复在抓的"永远会通过的测试" ——
 * 结果它出现在了我自己刚写的代码里。
 * 现在期望值在这里, 改它必须改测试文件, diff 上看得见。
 */
import { describe, it, expect } from "vitest";
import { splitThinkingAnswer } from "../lib/splitThinking";

/** 表驱动用例: 每个都对应一个真实踩过的坑 */
const CASES: Array<{
  name: string;
  input: string;
  content: string;
  thinking: string;
  phase: "pre" | "thinking" | "answer";
}> = [
  {
    // 正常形态
    name: "标准格式: 两个标题都带空格",
    input: "## Thinking\n推理过程\n## Answer\n今天练 Z2",
    content: "今天练 Z2", thinking: "推理过程", phase: "answer",
  },
  {
    // 实测坑 1: M3 把 '##' / 'Thinking' 拆成两帧发出, 中间空格根本没发出来。
    // 旧实现找带空格的 "## thinking" -> 永远匹配不上 -> 用户第一屏看到内部分析。
    name: "实测坑1: 标记无空格 (M3 真实流的实际形态)",
    input: "##Thinking\n分析 CTL 43\n##Answer\n今天练 Z2",
    content: "今天练 Z2", thinking: "分析 CTL 43", phase: "answer",
  },
  {
    name: "三个井号也认",
    input: "### Thinking\n推理\n### Answer\n答案",
    content: "答案", thinking: "推理", phase: "answer",
  },
  {
    // 实测坑 2: 回答正文里出现 "## Thinking" (用户让 AI 写 markdown 示例时)。
    // 用 indexOf 命中第一个 -> 真正的答案被当成 thinking 切走, content 变空字符串。
    name: "实测坑2: 回答正文里含 '## Thinking' 不能把答案切空",
    input: "##Answer\n示例:\n```md\n## Thinking\nfoo\n```\n结束",
    content: "示例:\n```md\n## Thinking\nfoo\n```\n结束",
    thinking: "", phase: "answer",
  },
  {
    // 这条是抽函数时跑测试抓出来的: 原来只有 Answer 没有 Thinking 时,
    // 标题不会被切掉, 车友会看到裸的 "## Answer" 当成回答第一行。
    name: "只有 Answer 没有 Thinking -> 切掉标题",
    input: "## Answer\n直接回答",
    content: "直接回答", thinking: "", phase: "answer",
  },
  {
    // 隔离 RE_THINK_HEAD 的 ^ 锚定。
    // 变异测试发现: 把 ^\s* 去掉, 上面"实测坑2"那条**照样绿** ——
    // 说明那条并没有在保护锚定。真正区分两者的场景是这个:
    // 文本中间出现 "## Thinking" 但开头没有标题时, 锚定版当成普通正文,
    // 不锚定版会误判成切分点、把 content 清空。
    name: "开头的锚定: 文本中间的 '## Thinking' 不能被当成切分点",
    input: "先说结论, 下面是我的思路:\n## Thinking\n这是正文的一部分",
    content: "先说结论, 下面是我的思路:\n## Thinking\n这是正文的一部分",
    thinking: "", phase: "pre",
  },
  {
    name: "什么标题都还没有 -> pre 阶段全显示",
    input: "今天",
    content: "今天", thinking: "", phase: "pre",
  },
  {
    name: "只有 Thinking 还没流到 Answer",
    input: "## Thinking\n推理中",
    content: "", thinking: "推理中", phase: "thinking",
  },
];

describe("splitThinkingAnswer", () => {
  for (const c of CASES) {
    it(c.name, () => {
      const got = splitThinkingAnswer(c.input);
      expect(got.content).toBe(c.content);
      expect(got.thinking).toBe(c.thinking);
      expect(got.phase).toBe(c.phase);
    });
  }
});

describe("流式累积", () => {
  // M3 真实流的形态: 标记被拆成 5 帧, 且中间空格没有发出来
  const DELTA_SEQ = ["##", "Think", "ing\n\n分析 CTL 43\n", "##Ans", "wer\n\n今天练 Z2"];

  it("标记跨 delta 边界被切开也能正确切分", () => {
    // 实现是对累积全文重新 exec, 所以 delta 边界天然无害 —— 这条锁住它。
    let acc = "";
    for (const d of DELTA_SEQ) acc += d;
    const r = splitThinkingAnswer(acc);
    expect(r.content).toBe("今天练 Z2");
    expect(r.thinking).toContain("分析 CTL 43");
  });

  it("流式过程中任何一帧都不该把内部分析漏成答案", () => {
    // 这是修复前用户真正看到的症状: 6 帧里 4 帧把 ##Thinking 的内容
    // 当成回答正文显示出来。
    let acc = "";
    for (const d of DELTA_SEQ) {
      acc += d;
      const r = splitThinkingAnswer(acc);
      if (r.phase !== "pre") {
        expect(r.content).not.toContain("分析 CTL");
      }
    }
  });
});

describe("回归: 旧实现坏在哪", () => {
  it("旧写法 indexOf('## thinking') 匹配不到无空格的标记", () => {
    // 说明这个 bug 为什么存在, 免得有人觉得"在模型侧补个空格不就行了"然后改回去。
    const real = "##Thinking\n分析\n##Answer\n答案";
    expect(real.includes("## thinking")).toBe(false);
    expect(splitThinkingAnswer(real).content).toBe("答案");
  });

  it("Answer 只在 thinking 之后找, 正文里的同名标题不误切", () => {
    const r = splitThinkingAnswer("##Answer\n示例:\n```md\n## Thinking\nfoo\n```\n结束");
    expect(r.content).toContain("## Thinking");  // 正文里的必须保留
    expect(r.content).not.toBe("");               // 不能被切成空
  });

  it("缺字段时不会崩, 也不会把 undefined 塞进 content", () => {
    // 用户发空白消息, 或者上游返回空 delta
    for (const input of ["", "   ", "\n\n"]) {
      const r = splitThinkingAnswer(input);
      expect(typeof r.content).toBe("string");
      expect(r.content).not.toContain("undefined");
    }
  });
});
