/** @type {import('tailwindcss').Config} */
// V0.8.3 B3: TP 老钱风 — 严肃、克制、信息密度高、数据是主角
// Bloomberg Terminal × 现代 web
// 核心变化:
//   - shadow 只保留 sm (1px 极淡), 删 elevated/lg/xl/2xl
//   - 圆角 4px 为默认, 禁止 rounded-xl/2xl/3xl
//   - 配色: 蓝 (#2563eb) 为唯一强调色, 紫 (#6366f1/#8b5cf6) 全部砍掉
//   - 数字字体: JetBrains Mono (等宽, KPI 用)
//   - 背景: #fafbfc 浅灰白, 无渐变
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  // V0.8.3 B3: 删 Tailwind 默认的 rounded-md/lg/xl/2xl/3xl, 只保留 sm (4px)
  theme: {
    borderRadius: {
      none: "0",
      sm: "4px",
      DEFAULT: "4px",
      md: "4px",
      // 不定义 lg/xl/2xl/3xl → 用了就 warn / 编译失败
      full: "9999px",
    },
    // V0.8.3 B3: 删 Tailwind 默认 shadow-lg/xl/2xl/inner, 只保留 sm
    boxShadow: {
      none: "none",
      sm: "0 1px 2px 0 rgba(15, 23, 42, 0.04)",
      DEFAULT: "0 1px 2px 0 rgba(15, 23, 42, 0.04)",
      // 状态色: 左 border 用, 这里留个面板投影以防万一
      panel: "0 1px 2px 0 rgba(15, 23, 42, 0.04)",
    },
    extend: {
      colors: {
        // V0.8.3 B3: 浅灰白底, 1px 边, 不用毛玻璃/渐变
        bg: {
          base: "#fafbfc",          // 主背景(浅灰白)
          panel: "#ffffff",         // 卡片(纯白)
          subtle: "#f3f4f6",        // 次级面板(灰)
          hover: "#f9fafb",         // hover 态(几乎纯白)
          input: "#ffffff",         // 输入框(白)
        },
        border: {
          DEFAULT: "#e5e7eb",       // 默认边 (浅灰)
          strong: "#d1d5db",        // 强调边
          subtle: "#f3f4f6",        // 极淡边
          // V0.8.3 B3: 状态色用于 border-l-4
          "l-success": "#10b981",   // 绿
          "l-warning": "#f59e0b",   // 橙
          "l-danger": "#dc2626",    // 红
          "l-primary": "#2563eb",   // 蓝
          "l-info": "#64748b",      // 灰
        },
        text: {
          primary: "#0f172a",       // 主文字(深近黑)
          secondary: "#475569",     // 次级文字(中灰)
          muted: "#94a3b8",         // 弱化文字(浅灰)
          inverse: "#ffffff",       // 反色
        },
        // V0.8.3 B3: TP 蓝, 唯一强调色; 紫系全部砍
        accent: {
          primary: "#2563eb",       // 主蓝 (TP 风)
          "primary-hover": "#1d4ed8", // hover (蓝-700)
          "primary-soft": "#eff6ff", // 浅蓝背景 (blue-50)
          success: "#059669",       // 成功
          warning: "#d97706",       // 警告
          danger: "#dc2626",        // 危险
          cyan: "#0891b2",          // 青 (次级强调)
        },
        // 训练区间色 (V0.8.3 B3 微调: 偏严肃风)
        zone: {
          z1: "#94a3b8",   // 灰 — 恢复
          z2: "#3b82f6",   // 蓝 — 耐力
          z3: "#10b981",   // 绿 — 节奏
          z4: "#f59e0b",   // 橙 — 阈值
          z5: "#dc2626",   // 红 — VO2
        },
        // V0.8.3 B3: 状态背景 (清淡不抢戏)
        status: {
          success: "#ecfdf5",
          warning: "#fffbeb",
          danger: "#fef2f2",
          info: "#f1f5f9",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      // V0.8.3 B3: 删 backdrop-blur-glass 特殊值, 用默认
      backdropBlur: {
        DEFAULT: "8px",
      },
    },
  },
  // V0.8.3 B3: 删 Tailwind 默认的 gradient-to-r/l/t/b/tr/tl/br/bl/deg
  // 通过 corePlugins 关闭 bg-gradient 类, 强制只能用 bg-[linear-gradient(...)] 显式声明
  // (保留 bg-gradient 因为有些地方仍然需要控制 — 后续清残留时再砍)
  plugins: [],
};