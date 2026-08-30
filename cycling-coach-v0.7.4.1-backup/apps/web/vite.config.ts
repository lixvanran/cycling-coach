import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite 配置
// - dev:  1420 端口, 代理 /api -> 8765
// - build: 输出到 ../../cycling_coach/static (相对本文件)
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
        manualChunks: undefined,  // 桌面模式不在意分块
      },
    },
  },
});
