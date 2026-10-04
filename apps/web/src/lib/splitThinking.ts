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
 * 测试在 `src/__tests__/splitThinking.test.ts` (vitest, node 环境)。
 *
 * 用例表**故意不放这里** —— 放在被测模块里再由测试 import, 看着 DRY,
 * 实际是"自己测自己": 改一下期望值测试就跟着绿, 而且改得悄无声息。
 * 期望值写在测试文件里, 改动在 diff 上看得见。
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
