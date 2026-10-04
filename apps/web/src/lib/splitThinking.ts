/**
 * 思维链 / 回答的切分逻辑 —— 从 ChatPage 抽出来的纯函数
 *
 * ## 为什么要抽出来
 *
 * 这段逻辑决定**用户打开聊天页看到的第一屏是答案还是模型的内部分析**,
 * 是整个 AI 体验里用户感知最强的一处。但它原本内嵌在 ChatPage 的
 * 流式回调里, 没有任何测试护栏 (前端连 vitest 都没装, 见下)。
 *
 * 抽成纯函数的好处不只是可测: 切分规则从"藏在组件里的一段 indexOf"
 * 变成"一个有名字、有文档、有测试的函数"。
 *
 * ## 背景: 真实 M3 流里踩到的三个坑
 *
 * 1. **标记被拆成多个 delta**: 实测收到 `'##'` / `'Thinking'` / `'\n\n'`
 *    三帧, 拼起来是 `"##Thinking"`, 中间的空格**根本没有发出来**。
 *    原来找的是 `"## thinking"` (带空格) —— 永远匹配不上, 于是
 *    用户看到的第一屏是模型的内部分析。
 *    → 匹配必须对空格不敏感。
 *
 * 2. **回答正文里可能出现 "## Thinking"**: 用户让 AI 写 markdown 示例时,
 *    正文里就会有一行 `## Thinking`。用 `indexOf` 命中第一个 →
 *    真正的答案被当成 thinking 切走, content 变成空字符串。
 *    → thinking 标记必须锚定在缓冲区开头。
 *
 * 3. **流式**: 每个 delta 都要对**累积后的全文**重新切分, 不能只扫新 chunk。
 *    所以标记跨 delta 边界被切开完全无害 —— 这是本实现天然具备的性质,
 *    但必须写测试锁住, 改的时候容易改错。
 *
 * ## 已知局限
 *
 * 仓库里没有前端测试框架 (`package.json` 无 test 脚本, devDependencies
 * 里没有 vitest / testing-library), 所以本文件目前只能靠人工和
 * tsc 保证。**带 TODO 标记的用例就是待接入自动化的那批。**
 */

export interface SplitResult {
  /** 车友实际看到的回答正文 */
  content: string;
  /** 折叠起来的思考过程; 还没切分出来时为 "" */
  thinking: string;
  /** 流式进行到哪一步了 */
  phase: "pre" | "thinking" | "answer";
}

// thinking 锚定开头: 回答正文里的同名标题不能被误认
const RE_THINK_HEAD = /^\s*#{2,}\s*thinking/i;
const RE_ANSWER_HEAD = /#{2,}\s*answer/i;

/**
 * 把累积的流式文本切成 (回答, 思考)。
 *
 * 每次收到新 delta 后对**累积全文**重新调用即可, 不需要管 delta 边界。
 *
 * @param fullText 从流开始累积到目前为止的全部文本
 */
export function splitThinkingAnswer(fullText: string): SplitResult {
  const thinkM = RE_THINK_HEAD.exec(fullText);
  const thinkEnd = thinkM ? thinkM.index + thinkM[0].length : -1;

  // Answer 只在 thinking 块之后找, 避免正文里的标题被误切
  const answerM = RE_ANSWER_HEAD.exec(fullText);
  const answerIdx = answerM ? answerM.index : -1;

  if (thinkM && answerM) {
    return {
      content: fullText.slice(answerIdx + answerM[0].length).trim(),
      thinking: fullText.slice(thinkEnd, answerIdx).trim(),
      phase: "answer",
    };
  }
  if (thinkM) {
    return {
      content: "",
      thinking: fullText.slice(thinkEnd).trim(),
      phase: "thinking",
    };
  }
  // 只有 Answer 没有 Thinking: 也要把标题切掉, 否则车友会看到一行
  // 裸的 "## Answer" 当成回答的第一行。
  // (这条是跑 SPLIT_CASES 时被抓出来的 —— 写的时候没想到这个分支。)
  if (answerM) {
    return {
      content: fullText.slice(answerIdx + answerM[0].length).trim(),
      thinking: "",
      phase: "answer",
    };
  }
  return { content: fullText, thinking: "", phase: "pre" };
}

/**
 * TODO(vitest): 等前端测试框架接上后, 把下面的用例直接搬成单测。
 * 每一行都对应一个真实踩过的坑, 别在重构时弄丢。
 */
export const SPLIT_CASES: Array<{ name: string; input: string; expect: Partial<SplitResult> }> = [
  {
    name: "标准格式: 两个标题都带空格",
    input: "## Thinking\n推理过程\n## Answer\n今天练 Z2",
    expect: { content: "今天练 Z2", thinking: "推理过程", phase: "answer" },
  },
  {
    name: "实测坑1: 标记无空格 (M3 真实流的实际形态)",
    input: "##Thinking\n分析 CTL 43\n##Answer\n今天练 Z2",
    expect: { content: "今天练 Z2", thinking: "分析 CTL 43", phase: "answer" },
  },
  {
    name: "三个井号也认",
    input: "### Thinking\n推理\n### Answer\n答案",
    expect: { content: "答案", phase: "answer" },
  },
  {
    name: "实测坑2: 回答正文里含 '## Thinking' 不能把答案切空",
    input: "##Answer\n示例:\n```md\n## Thinking\nfoo\n```\n结束",
    expect: { content: "示例:\n```md\n## Thinking\nfoo\n```\n结束" },
  },
  {
    // 期望是 answer 而不是 pre: 标题本身要被切掉。
    // 写成 pre 是我第一版想错了 —— 跑出来才发现这个分支的行为和直觉不同。
    name: "只有 Answer 没有 Thinking -> 切掉标题, 全当答案",
    input: "## Answer\n直接回答",
    expect: { content: "直接回答", thinking: "", phase: "answer" },
  },
  {
    name: "什么标题都还没有 -> pre 阶段全显示",
    input: "今天",
    expect: { content: "今天", thinking: "", phase: "pre" },
  },
  {
    name: "实测坑3: 只有 Thinking 还没流到 Answer",
    input: "## Thinking\n推理中",
    expect: { content: "", thinking: "推理中", phase: "thinking" },
  },
];

/**
 * TODO(vitest): 流式累积的正确性 —— 对累积全文重新切分, 标记跨 delta 边界无害。
 * 用下面的 DELTA_SEQ 逐帧累积断言。
 */
export const DELTA_SEQ: string[] = ["##", "Think", "ing\n\n分析 CTL 43\n", "##Ans", "wer\n\n今天练 Z2"];
