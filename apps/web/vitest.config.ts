import { defineConfig } from "vitest/config";

// V0.9.0: 前端第一次有测试。
// 环境用 node 而不是 jsdom —— 现在测的 splitThinking 是纯函数,
// 不碰 DOM, 就不需要为它引入 jsdom/@testing-library 这类重依赖。
// 等真的出现需要挂载组件的测试时, 再把 environment 换成 jsdom。
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
