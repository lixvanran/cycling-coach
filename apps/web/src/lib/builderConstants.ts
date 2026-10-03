// V0.8.3.1 P0: Builder 共享常量/工具
// 从 BuilderPage.tsx 抽出 (1893 行太胖),让 page 只剩编排逻辑
// 共用: BuilderPage.tsx / ChatMessage.tsx (workout JSON 转 blocks)
import type { WorkoutGoal, WorkoutStep, StepKind } from "./types";
import type { Block } from "./builderBlocks";

// =============== ID 生成 ===============
// 注意: ChatMessage.tsx 也有一个 rid(),保持同步 (chat JSON 解析需要)
export function rid() {
  return Math.random().toString(36).slice(2, 10);
}

// =============== Step 工厂 ===============
export function newStep(kind: StepKind = "main"): WorkoutStep {
  return {
    kind,
    duration_s: 600,
    power_pct_ftp: kind === "warmup" ? 50 : kind === "cooldown" ? 45 : 75,
    cadence_rpm: 88,
    label: "",
    repeat: 1,
  };
}

// =============== Block 计算 ===============
export function blockDuration(b: Block): number {
  if (b.kind === "single") return b.step.duration_s;
  return (b.work.duration_s + (b.rest?.duration_s ?? 0)) * b.reps;
}

// =============== 时间格式化 ===============
export function fmtTime(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (sec === 0) return `${m}min`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function fmtBigTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}m`;
  return `${m}min`;
}

// =============== StepKind 配色 (TP 风) ===============
export const KIND_COLOR: Record<StepKind, {
  bg: string; border: string; text: string; ring: string; lightBg: string; accent: string;
}> = {
  warmup: {
    bg: "bg-status-info",
    border: "border-accent-primary/40",
    text: "text-accent-primary",
    ring: "",
    lightBg: "bg-status-info",
    accent: "#0ea5e9",
  },
  main: {
    bg: "bg-accent-warning",  // V0.8.3.1: bg-status-warning0 → bg-accent-warning
    border: "border-accent-warning",
    text: "text-accent-warning",
    ring: "",
    lightBg: "bg-status-warning",
    accent: "#f59e0b",
  },
  recovery: {
    bg: "bg-status-success",
    border: "border-accent-success",
    text: "text-accent-success",
    ring: "",
    lightBg: "bg-status-success",
    accent: "#10b981",
  },
  cooldown: {
    bg: "bg-slate-400",
    border: "border-slate-400/40",
    text: "text-text-secondary",
    ring: "ring-accent-primary/50",
    lightBg: "bg-slate-100",
    accent: "#94a3b8",
  },
};

export const KIND_LABEL: Record<StepKind, string> = {
  warmup: "热身",
  main: "主项",
  recovery: "恢复",
  cooldown: "放松",
};

// =============== Goal 配色 ===============
export const GOAL_OPTIONS: { key: WorkoutGoal; label: string; color: string; ring: string; chip: string }[] = [
  { key: "recovery", label: "恢复", color: "sky", ring: "ring-accent-primary", chip: "bg-status-info text-accent-primary border-accent-primary" },
  { key: "endurance", label: "耐力", color: "emerald", ring: "ring-emerald-400", chip: "bg-status-success text-accent-success border-border" },
  { key: "tempo", label: "节奏", color: "amber", ring: "ring-amber-400", chip: "bg-status-warning text-accent-warning border-border" },
  { key: "threshold", label: "阈值", color: "orange", ring: "ring-accent-warning", chip: "bg-status-warning text-accent-warning border-border" },
  { key: "vo2max", label: "VO2", color: "red", ring: "ring-accent-danger", chip: "bg-status-danger text-accent-danger border-accent-danger" },
  { key: "race", label: "比赛", color: "fuchsia", ring: "ring-accent-primary", chip: "bg-status-info text-accent-primary border-accent-primary" },
];

// =============== 推荐标签 ===============
export const SUGGESTED_TAGS = ["z1", "z2", "z3", "sweet-spot", "vo2", "intervals", "climbing", "long", "race", "recovery", "test", "endurance", "threshold"];

// =============== 快速模板 (无 icon, icon 在 BuilderPage 内联组装避免 lucide 循环依赖) ===============
export type QuickTemplateSpec = {
  key: string; label: string; color: string; goal: WorkoutGoal; blocks: () => Block[];
};

export const QUICK_TEMPLATES: QuickTemplateSpec[] = [
  {
    key: "vo2", label: "VO2max 5×3min", color: "bg-accent-danger", goal: "vo2max",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 5, label: "VO2 5×3min",
        work: { kind: "main", duration_s: 180, power_pct_ftp: 120, cadence_rpm: 92, label: "全力" },
        rest: { kind: "recovery", duration_s: 180, power_pct_ftp: 50, label: "间歇" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "threshold", label: "阈值 2×12min", color: "bg-accent-warning", goal: "threshold",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 2, label: "阈值 2×12min",
        work: { kind: "main", duration_s: 720, power_pct_ftp: 95, cadence_rpm: 90, label: "阈值" },
        rest: { kind: "recovery", duration_s: 720, power_pct_ftp: 50, label: "恢复" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "tempo", label: "节奏 2×20min", color: "bg-accent-warning", goal: "tempo",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 2, label: "节奏 2×20min",
        work: { kind: "main", duration_s: 1200, power_pct_ftp: 88, cadence_rpm: 88, label: "甜蜜点" },
        rest: { kind: "recovery", duration_s: 600, power_pct_ftp: 55, label: "间歇" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "recovery", label: "恢复 30min", color: "bg-accent-cyan", goal: "recovery",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "main", duration_s: 1800, power_pct_ftp: 50, cadence_rpm: 85, label: "轻松踩" } },
    ],
  },
];
