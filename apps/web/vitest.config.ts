import { defineConfig } from "vitest/config";

// V0.9.0: 前端第一次有测试。
// 环境用 node 而不是 jsdom —— 现在测的 splitThinking 是纯函数, 不碰 DOM,
// 就不需要为它引入 jsdom/@testing-library 这类重依赖。
//
// ⚠️ 将来真的要写组件测试时, 请用**文件级** `// @vitest-environment jsdom`
// 注释, 不要回来改这里的全局 environment —— 否则"这个测试要不要 DOM"
// 这件事就从代码里消失了, 后来人只能靠猜。
//
// include 留空 = 用 vitest 默认 (**/*.{test,spec}.?(c|m)[jt]s?(x))。
// Verifier 指出: 我原先写的 ["src/**/*.test.ts", "src/**/*.test.tsx"]
// 比默认**窄** —— 漏掉 .spec.* 和 src/ 以外的, 谁写个 api.spec.ts 会
// 静默不执行, 而 vitest run 照样退出 0。静默不跑比没有测试更糟。
export default defineConfig({
  test: {
    environment: "node",
  },
});
