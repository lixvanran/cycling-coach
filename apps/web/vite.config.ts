import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite 配置 — V0.8.0
// - dev:  1420 端口, 代理 /api -> 8765
// - build: 输出到 ../../cycling_coach/static (相对本文件)
// - manualChunks: 拆分 vendor (react/recharts/leaflet/markdown),
//   配合 App.tsx 路由级 lazy(), 首屏 chunk < 350KB
export default defineConfig({
  plugins: [react()],
  // 🔴 V0.9.1 修 P0: 原来是 `base: "./"`(相对路径), 注释说
  // "桌面模式走 file:// 或 http://127.0.0.1:8765, 都要相对路径"。
  //
  // **这个前提是错的**, 而且后果极严重:
  //   index.html 里写的是 ./assets/index-xxx.js
  //   浏览器在 /plan/calendar 解析 ./assets/ -> /plan/assets/ -> 404
  //   -> SPA fallback 返回 index.html(MIME 是 text/html)
  //   -> 浏览器: "Expected a JavaScript-or-Wasm module script"
  //   -> **整个页面的 JS 一行都没执行**
  //
  // 也就是说所有嵌套路由(/plan/* /training/* /data/* /ai/*)全是
  // 空白骨架: 没有数据、没有按钮、没有日历事件。
  // 用户看到的就是"按钮做了但看不见""元素重叠""拖不动"。
  //
  // 根路径 `/` 恰好正常(./assets/ -> /assets/), 所以问题更隐蔽 ——
  // 首页好好的, 一进子页面就"空了"。
  //
  // 桌面版实际走的是 `mainWindow.loadURL('http://127.0.0.1:8765')`
  // (apps/desktop/main.cjs:188), **是 http 不是 file://**,
  // 所以绝对路径完全安全。SPA 路由由服务端的 fallback 负责,
  // 两者不冲突。
  base: "/",
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../../cycling_coach/static"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        // V0.8.0: 拆分大 vendor 进独立 chunk
        // 桌面模式不在意分块, 但 web 模式 + 路由级 lazy 配合
        // 可让首屏 (/) 只加载 vendor-react + 入口 + dashboard chunk
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-charts": ["recharts"],
          "vendor-map": ["leaflet"],
          "vendor-markdown": ["react-markdown", "rehype-sanitize", "remark-gfm"],
          "vendor-icons": ["lucide-react"],
          "vendor-state": ["zustand"],
        },
      },
    },
  },
});
