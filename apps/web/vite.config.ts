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
  base: "./",  // 桌面模式走 file:// 或 http://127.0.0.1:8765, 都要相对路径
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
