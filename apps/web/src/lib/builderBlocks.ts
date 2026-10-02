// V0.8.3: Builder Block[] 类型 (从 BuilderPage.tsx 提取, 给 ChatMessage 共用)
// 避免循环依赖: ChatMessage → BuilderPage → ChatMessage
import type { WorkoutStep } from "./types";

export type Block =
  | { id: string; kind: "single"; step: WorkoutStep }
  | { id: string; kind: "loop"; reps: number; work: WorkoutStep; rest: WorkoutStep | null; label: string };