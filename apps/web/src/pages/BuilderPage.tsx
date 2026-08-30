// 课程编排 (Builder) — V0.5 全新设计
// 对标 Scratch 3.0 拖拽积木体验
// 关键交互:
//   1. 三栏: 左侧积木库 (1/5) | 中间时间轴 (3/5) | 右侧实时编辑抽屉 (1/5)
//   2. 拖拽: HTML5 native DnD, 拖到时间轴任意位置 (显示插入线)
//   3. 点击积木 → 右侧抽屉实时双向编辑, 永远可见
//   4. 循环块: scratch 风格 ×N 容器, 内含 work+rest 两条 (可视化缩略)
//   5. 撤销/重做 (Cmd+Z / Cmd+Shift+Z)
//   6. 总时长 + TSS 实时统计 + 预估 IF
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  Plus, Trash2, Save, Sparkles, Layers, Copy, ClipboardPaste, BookmarkPlus, X, ChevronUp, ChevronDown,
  Repeat, Flame, Zap, Mountain, Activity, GripVertical, Undo2, Redo2,
  Play, Settings, Type, Clock, Target, Pencil, Search, ChevronRight,
  Hash, Heart, Gauge, BookOpen, Wand2,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { Workout, WorkoutGoal, WorkoutStep, StepKind } from "../lib/types";
import { useAppStore } from "../store/useAppStore";

// =============== 类型 ===============
type Block =
  | { id: string; kind: "single"; step: WorkoutStep }
  | { id: string; kind: "loop"; reps: number; work: WorkoutStep; rest: WorkoutStep | null; label: string };

// 编辑面板当前选中的位置
type EditTarget =
  | { type: "block"; blockId: string }
  | { type: "loop-part"; blockId: string; part: "work" | "rest" }
  | { type: "meta" }  // 编辑标题/描述/标签
  | null;

// =============== 常量 ===============

// 4 种 kind 配色
const KIND_COLOR: Record<StepKind, {
  bg: string; border: string; text: string; ring: string; lightBg: string; accent: string;
}> = {
  warmup: {
    bg: "bg-sky-500",
    border: "border-sky-500/40",
    text: "text-sky-700",
    ring: "ring-sky-500/50",
    lightBg: "bg-sky-50",
    accent: "#0ea5e9",
  },
  main: {
    bg: "bg-amber-500",
    border: "border-amber-500/40",
    text: "text-amber-700",
    ring: "ring-amber-500/50",
    lightBg: "bg-amber-50",
    accent: "#f59e0b",
  },
  recovery: {
    bg: "bg-emerald-500",
    border: "border-emerald-500/40",
    text: "text-emerald-700",
    ring: "ring-emerald-500/50",
    lightBg: "bg-emerald-50",
    accent: "#10b981",
  },
  cooldown: {
    bg: "bg-slate-400",
    border: "border-slate-400/40",
    text: "text-slate-700",
    ring: "ring-slate-400/50",
    lightBg: "bg-slate-100",
    accent: "#94a3b8",
  },
};

const KIND_LABEL: Record<StepKind, string> = {
  warmup: "热身",
  main: "主项",
  recovery: "恢复",
  cooldown: "放松",
};

const GOAL_OPTIONS: { key: WorkoutGoal; label: string; color: string; ring: string; chip: string }[] = [
  { key: "recovery", label: "恢复", color: "sky", ring: "ring-sky-400", chip: "bg-sky-100 text-sky-700 border-sky-300" },
  { key: "endurance", label: "耐力", color: "emerald", ring: "ring-emerald-400", chip: "bg-emerald-100 text-emerald-700 border-emerald-300" },
  { key: "tempo", label: "节奏", color: "amber", ring: "ring-amber-400", chip: "bg-amber-100 text-amber-700 border-amber-300" },
  { key: "threshold", label: "阈值", color: "orange", ring: "ring-orange-400", chip: "bg-orange-100 text-orange-700 border-orange-300" },
  { key: "vo2max", label: "VO2", color: "red", ring: "ring-red-400", chip: "bg-red-100 text-red-700 border-red-300" },
  { key: "race", label: "比赛", color: "fuchsia", ring: "ring-fuchsia-400", chip: "bg-fuchsia-100 text-fuchsia-700 border-fuchsia-300" },
];

const SUGGESTED_TAGS = ["z1", "z2", "z3", "sweet-spot", "vo2", "intervals", "climbing", "long", "race", "recovery", "test", "endurance", "threshold"];

const QUICK_TEMPLATES: {
  key: string; label: string; icon: any; color: string; goal: WorkoutGoal; blocks: () => Block[];
}[] = [
  {
    key: "vo2", label: "VO2max 5×3min", icon: Flame, color: "from-red-500 to-orange-500", goal: "vo2max",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 5, label: "VO2 5×3min",
        work: { kind: "main", duration_s: 180, power_pct_ftp: 120, cadence_rpm: 92, label: "全力" },
        rest: { kind: "recovery", duration_s: 180, power_pct_ftp: 50, label: "间歇" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "threshold", label: "阈值 2×12min", icon: Mountain, color: "from-orange-500 to-amber-500", goal: "threshold",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 2, label: "阈值 2×12min",
        work: { kind: "main", duration_s: 720, power_pct_ftp: 95, cadence_rpm: 90, label: "阈值" },
        rest: { kind: "recovery", duration_s: 720, power_pct_ftp: 50, label: "恢复" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "tempo", label: "节奏 2×20min", icon: Activity, color: "from-amber-500 to-yellow-500", goal: "tempo",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "warmup", duration_s: 900, power_pct_ftp: 50, label: "热身" } },
      { id: rid(), kind: "loop", reps: 2, label: "节奏 2×20min",
        work: { kind: "main", duration_s: 1200, power_pct_ftp: 88, cadence_rpm: 88, label: "甜蜜点" },
        rest: { kind: "recovery", duration_s: 600, power_pct_ftp: 55, label: "间歇" } },
      { id: rid(), kind: "single", step: { kind: "cooldown", duration_s: 600, power_pct_ftp: 45, label: "冷身" } },
    ],
  },
  {
    key: "recovery", label: "恢复 30min", icon: Zap, color: "from-sky-400 to-cyan-500", goal: "recovery",
    blocks: () => [
      { id: rid(), kind: "single", step: { kind: "main", duration_s: 1800, power_pct_ftp: 50, cadence_rpm: 85, label: "轻松踩" } },
    ],
  },
];

// 工具函数
function rid() {
  return Math.random().toString(36).slice(2, 10);
}
function newStep(kind: StepKind = "main"): WorkoutStep {
  return {
    kind,
    duration_s: 600,
    power_pct_ftp: kind === "warmup" ? 50 : kind === "cooldown" ? 45 : 75,
    cadence_rpm: 88,
    label: "",
    repeat: 1,
  };
}
function blockDuration(b: Block): number {
  if (b.kind === "single") return b.step.duration_s;
  return (b.work.duration_s + (b.rest?.duration_s ?? 0)) * b.reps;
}
function fmtTime(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (sec === 0) return `${m}min`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
function fmtBigTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}m`;
  return `${m}min`;
}

// =============== 主体 ===============
export function BuilderPage() {
  const setView = useAppStore((s) => s.setView);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [goal, setGoal] = useState<WorkoutGoal>("endurance");
  const [intensity, setIntensity] = useState<WorkoutGoal>("endurance");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [myWorkouts, setMyWorkouts] = useState<Workout[]>([]);
  const [editing, setEditing] = useState<Workout | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // 编辑面板目标 (scratch 风格 — 永远在右侧显示)
  const [editTarget, setEditTarget] = useState<EditTarget>(null);
  // 撤销/重做
  const [history, setHistory] = useState<Block[][]>([]);
  const [future, setFuture] = useState<Block[][]>([]);

  // 拖拽状态
  const [draggedItem, setDraggedItem] = useState<{ kind: "new" | "existing"; block?: Block; stepKind?: StepKind; blockId?: string } | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  // V0.7.1: 块多选 + 段剪贴板 + 段模板
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [clipboardBlocks, setClipboardBlocks] = useState<Block[]>([]);
  // 段模板库 (本地存储)
  const [segmentTemplates, setSegmentTemplates] = useState<Block[]>(() => {
    try {
      const saved = localStorage.getItem("cc:segment_templates");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  // 多选最后点击的 id (Shift 范围选)
  const [lastSelectedId, setLastSelectedId] = useState<string | null>(null);

  // =============== 撤销/重做 ===============
  const pushHistory = useCallback((newBlocks: Block[]) => {
    setHistory((h) => [...h.slice(-30), blocks]);
    setFuture([]);
    setBlocks(newBlocks);
  }, [blocks]);

  const undo = () => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setHistory((h) => h.slice(0, -1));
    setFuture((f) => [blocks, ...f]);
    setBlocks(prev);
  };
  const redo = () => {
    if (future.length === 0) return;
    const next = future[0];
    setFuture((f) => f.slice(1));
    setHistory((h) => [...h, blocks]);
    setBlocks(next);
  };

  // 键盘快捷键
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      // 在 input/textarea 里跳过, 避免拦截正常输入
      const tag = (e.target as HTMLElement)?.tagName;
      const inEditable = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;
      if (inEditable) return;

      if (isMod && e.key === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (isMod && (e.key === "Z" || (e.key === "z" && e.shiftKey))) { e.preventDefault(); redo(); }
      else if (isMod && e.key === "s") { e.preventDefault(); save(); }
      // V0.7.1: Ctrl+C 复制 / Ctrl+V 粘贴 / Ctrl+D 复制选中
      else if (isMod && (e.key === "c" || e.key === "C")) { e.preventDefault(); copySelected(); }
      else if (isMod && (e.key === "v" || e.key === "V")) { e.preventDefault(); pasteBlocks(); }
      else if (isMod && (e.key === "d" || e.key === "D")) { e.preventDefault(); copySelected(); }
      // Esc 取消多选
      else if (e.key === "Escape") { setSelectedIds(new Set()); setLastSelectedId(null); }
      else if (e.key === "Delete" || e.key === "Backspace") {
        if (selectedIds.size > 0 || editTarget?.type === "block") {
          e.preventDefault();
          removeSelected();
        }
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  // =============== 加载 ===============
  useEffect(() => {
    loadMyWorkouts();
  }, []);

  async function loadMyWorkouts() {
    try {
      const r = await api.listWorkouts({ limit: 200 });
      setMyWorkouts(r.workouts.filter((w) => w.source === "user" || !w.source));
    } catch (e) { /* ignore */ }
  }

  function loadFromWorkout(w: Workout) {
    setEditing(w);
    setTitle(w.title);
    setDescription(w.description || "");
    setGoal(w.goal);
    setIntensity(w.goal);
    setTags(w.tags || []);
    setBlocks(structureToBlocks(w.structure));
    setHistory([]);
    setFuture([]);
    setEditTarget(null);
  }

  function resetForm() {
    setEditing(null);
    setTitle("");
    setDescription("");
    setGoal("endurance");
    setIntensity("endurance");
    setTags([]);
    setBlocks([]);
    setHistory([]);
    setFuture([]);
    setEditTarget(null);
  }

  // =============== Block 操作 ===============
  function addSingleBlock(kind: StepKind, atIndex?: number) {
    const newBlock: Block = { id: rid(), kind: "single", step: newStep(kind) };
    const idx = atIndex ?? blocks.length;
    const newBlocks = [...blocks.slice(0, idx), newBlock, ...blocks.slice(idx)];
    pushHistory(newBlocks);
    setEditTarget({ type: "block", blockId: newBlock.id });
  }

  function addLoopBlock(atIndex?: number) {
    const newBlock: Block = {
      id: rid(), kind: "loop", reps: 3, label: "循环 3×",
      work: { kind: "main", duration_s: 300, power_pct_ftp: 100, cadence_rpm: 90, label: "主项" },
      rest: { kind: "recovery", duration_s: 180, power_pct_ftp: 50, label: "间歇" },
    };
    const idx = atIndex ?? blocks.length;
    const newBlocks = [...blocks.slice(0, idx), newBlock, ...blocks.slice(idx)];
    pushHistory(newBlocks);
    setEditTarget({ type: "block", blockId: newBlock.id });
  }

  function applyTemplate(t: typeof QUICK_TEMPLATES[0]) {
    const newBlocks = [...blocks, ...t.blocks()];
    pushHistory(newBlocks);
    setGoal(t.goal);
    setIntensity(t.goal);
    setEditTarget(null);
  }

  function removeBlock(id: string) {
    pushHistory(blocks.filter((b) => b.id !== id));
    if (editTarget?.type === "block" && editTarget.blockId === id) setEditTarget(null);
    if (editTarget?.type === "loop-part" && editTarget.blockId === id) setEditTarget(null);
  }

  function duplicateBlock(id: string) {
    const idx = blocks.findIndex((b) => b.id === id);
    if (idx < 0) return;
    const b = blocks[idx];
    const copy: Block = b.kind === "single"
      ? { id: rid(), kind: "single", step: { ...b.step } }
      : { id: rid(), kind: "loop", reps: b.reps, label: b.label, work: { ...b.work }, rest: b.rest ? { ...b.rest } : null };
    pushHistory([...blocks.slice(0, idx + 1), copy, ...blocks.slice(idx + 1)]);
  }

  function moveBlock(id: string, dir: -1 | 1) {
    const idx = blocks.findIndex((b) => b.id === id);
    if (idx < 0) return;
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= blocks.length) return;
    const newBlocks = [...blocks];
    [newBlocks[idx], newBlocks[newIdx]] = [newBlocks[newIdx], newBlocks[idx]];
    pushHistory(newBlocks);
  }

  // V0.7.1: 多选辅助 — Shift 范围选 / Cmd+Click 加选
  function toggleBlockSelection(id: string, modifiers: { shift?: boolean; meta?: boolean } = {}) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (modifiers.shift && lastSelectedId) {
        // 范围选: 从 lastSelectedId 到 id 之间全部选中
        const a = blocks.findIndex((b) => b.id === lastSelectedId);
        const bIdx = blocks.findIndex((b) => b.id === id);
        if (a >= 0 && bIdx >= 0) {
          const [from, to] = a < bIdx ? [a, bIdx] : [bIdx, a];
          for (let i = from; i <= to; i++) next.add(blocks[i].id);
        }
        return next;
      }
      if (modifiers.meta) {
        // Cmd+Click: toggle 单个
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }
      // 普通: 单选
      next.clear();
      next.add(id);
      return next;
    });
    setLastSelectedId(id);
    setEditTarget({ type: "block", blockId: id });
  }

  // V0.7.1: 复制选中块到剪贴板 (in-memory + 系统剪贴板)
  async function copySelected() {
    const ids = selectedIds.size > 0 ? selectedIds : (editTarget?.type === "block" ? new Set([editTarget.blockId]) : new Set<string>());
    if (ids.size === 0) { showToast("err", "未选中任何块"); return; }
    const blocksToCopy: Block[] = [];
    for (const b of blocks) {
      if (ids.has(b.id)) {
        blocksToCopy.push(b);
      }
    }
    setClipboardBlocks(blocksToCopy);
    // 写系统剪贴板 (JSON 形式, 其他地方也能用)
    try {
      const json = JSON.stringify(blocksToCopy.map((b) => {
        if (b.kind === "single") return { kind: "single", step: b.step };
        return { kind: "loop", reps: b.reps, work: b.work, rest: b.rest, label: b.label };
      }));
      await navigator.clipboard.writeText(json);
      showToast("ok", `已复制 ${blocksToCopy.length} 块到剪贴板 (系统剪贴板已同步)`);
    } catch {
      showToast("ok", `已复制 ${blocksToCopy.length} 块到内部剪贴板`);
    }
  }

  // V0.7.1: 粘贴剪贴板块
  function pasteBlocks(atIndex?: number) {
    let source: Block[] = clipboardBlocks;
    if (source.length === 0) {
      showToast("err", "剪贴板为空, 先 Ctrl+C 复制");
      return;
    }
    const insertAt = atIndex ?? blocks.length;
    // 重新生成 id 避免冲突
    const newBlocks: Block[] = source.map((b) => {
      if (b.kind === "single") return { id: rid(), kind: "single", step: { ...b.step } };
      return { id: rid(), kind: "loop", reps: b.reps, label: b.label, work: { ...b.work }, rest: b.rest ? { ...b.rest } : null };
    });
    pushHistory([...blocks.slice(0, insertAt), ...newBlocks, ...blocks.slice(insertAt)]);
    showToast("ok", `已粘贴 ${newBlocks.length} 块`);
    // 选中新粘贴的块
    setSelectedIds(new Set(newBlocks.map((b) => b.id)));
  }

  // V0.7.1: 批量删除选中块
  function removeSelected() {
    if (selectedIds.size === 0) {
      if (editTarget?.type === "block") {
        removeBlock(editTarget.blockId);
        return;
      }
      showToast("err", "未选中任何块");
      return;
    }
    const newBlocks = blocks.filter((b) => !selectedIds.has(b.id));
    pushHistory(newBlocks);
    showToast("ok", `已删除 ${selectedIds.size} 块`);
    setSelectedIds(new Set());
  }

  // V0.7.1: 段模板 — 保存选中块
  function saveAsTemplate() {
    const ids = selectedIds.size > 0 ? selectedIds : (editTarget?.type === "block" ? new Set([editTarget.blockId]) : new Set<string>());
    if (ids.size === 0) { showToast("err", "未选中任何块"); return; }
    const blocksToSave: Block[] = [];
    for (const b of blocks) {
      if (ids.has(b.id)) blocksToSave.push(b);
    }
    const next = [...segmentTemplates, ...blocksToSave];
    setSegmentTemplates(next);
    try {
      localStorage.setItem("cc:segment_templates", JSON.stringify(next));
      showToast("ok", `已保存 ${blocksToSave.length} 块到段模板库`);
    } catch (e) {
      showToast("err", "保存失败: localStorage 满");
    }
  }

  // V0.7.1: 段模板 — 插入模板到末尾
  function insertTemplate(tpl: Block) {
    const fresh: Block = tpl.kind === "single"
      ? { id: rid(), kind: "single", step: { ...tpl.step } }
      : { id: rid(), kind: "loop", reps: tpl.reps, label: tpl.label, work: { ...tpl.work }, rest: tpl.rest ? { ...tpl.rest } : null };
    pushHistory([...blocks, fresh]);
    const tplLabel = tpl.kind === "loop" ? tpl.label : tpl.step.label;
    const tplKind = tpl.kind === "single" ? tpl.step.kind : tpl.work?.kind;
    showToast("ok", `已插入模板段 "${tplLabel || tplKind || "段"}"`);
  }

  function clearTemplates() {
    if (segmentTemplates.length === 0) return;
    if (!confirm(`清空 ${segmentTemplates.length} 个段模板?`)) return;
    setSegmentTemplates([]);
    localStorage.removeItem("cc:segment_templates");
    showToast("ok", "段模板已清空");
  }

  function updateSingleStep(blockId: string, patch: Partial<WorkoutStep>) {
    pushHistory(blocks.map((b) => b.id === blockId && b.kind === "single" ? { ...b, step: { ...b.step, ...patch } } : b));
  }

  function updateLoop(blockId: string, patch: Partial<Extract<Block, { kind: "loop" }>>) {
    pushHistory(blocks.map((b) => b.id === blockId && b.kind === "loop" ? { ...b, ...patch } : b));
  }

  function updateLoopPart(blockId: string, part: "work" | "rest", patch: Partial<WorkoutStep>) {
    pushHistory(blocks.map((b) => {
      if (b.id !== blockId || b.kind !== "loop") return b;
      if (part === "work") return { ...b, work: { ...b.work, ...patch } };
      if (part === "rest" && b.rest) return { ...b, rest: { ...b.rest, ...patch } };
      return b;
    }));
  }

  // =============== 拖拽 ===============
  function onDragStartNew(e: React.DragEvent, stepKind?: StepKind) {
    setDraggedItem({ kind: "new", stepKind });
    e.dataTransfer.effectAllowed = "copy";
  }
  function onDragStartExisting(e: React.DragEvent, blockId: string) {
    setDraggedItem({ kind: "existing", blockId });
    e.dataTransfer.effectAllowed = "move";
  }
  function onDragEnd() {
    setDraggedItem(null);
    setDropIndex(null);
  }
  function onDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    setDropIndex(idx);
  }
  function onDrop(e: React.DragEvent, idx: number) {
    e.preventDefault();
    if (!draggedItem) return;
    if (draggedItem.kind === "new" && draggedItem.stepKind) {
      addSingleBlock(draggedItem.stepKind, idx);
    } else if (draggedItem.kind === "existing" && draggedItem.blockId) {
      const oldIdx = blocks.findIndex((b) => b.id === draggedItem.blockId);
      if (oldIdx < 0) return;
      const newBlocks = [...blocks];
      const [moved] = newBlocks.splice(oldIdx, 1);
      const targetIdx = oldIdx < idx ? idx - 1 : idx;
      newBlocks.splice(targetIdx, 0, moved);
      pushHistory(newBlocks);
    }
    onDragEnd();
  }

  // =============== 标签 ===============
  function addTag() {
    const t = tagInput.trim();
    if (!t) return;
    if (!tags.includes(t)) setTags([...tags, t]);
    setTagInput("");
  }
  function removeTag(t: string) { setTags(tags.filter((x) => x !== t)); }

  // =============== 保存 ===============
  function showToast(kind: "ok" | "err", msg: string) {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 2200);
  }

  async function save() {
    if (!title.trim()) { showToast("err", "请输入课程标题"); return; }
    if (blocks.length === 0) { showToast("err", "至少 1 个积木块"); return; }
    setLoading(true);
    try {
      const payload = {
        title: title.trim(), goal, intensity,
        duration_min: Math.round(blockTotal(blocks) / 60),
        structure: blocksToStructure(blocks),
        tags, description: description.trim() || null, is_template: true,
      };
      let saved: Workout;
      if (editing) {
        saved = await api.updateWorkout(editing.id, payload);
        showToast("ok", `已更新: ${saved.title}`);
      } else {
        saved = await api.createWorkout(payload);
        showToast("ok", `已创建: ${saved.title}`);
      }
      await loadMyWorkouts();
      loadFromWorkout(saved);
    } catch (e: any) {
      showToast("err", `保存失败: ${e?.message ?? "?"}`);
    } finally {
      setLoading(false);
    }
  }

  // =============== 统计 ===============
  const totalDur = blockTotal(blocks);
  const totalTSS = computeTSS(blocks, goal);

  return (
    <div className="h-full flex flex-col bg-bg-base select-none" onDragEnd={onDragEnd}>
      {/* ============== 顶部固定工具栏 ============== */}
      <div className="flex-shrink-0 bg-white/80 backdrop-blur border-b border-border px-5 py-2.5 flex items-center justify-between gap-3 sticky top-0 z-20 shadow-sm">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)" }}>
            <Layers size={18} className="text-white" />
          </div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onFocus={() => setEditTarget({ type: "meta" })}
            placeholder="课程标题..."
            className="text-base font-semibold bg-transparent border-b-2 border-transparent hover:border-border focus:border-accent focus:outline-none px-1 min-w-0 flex-1 max-w-xs"
          />
          {editing && <span className="text-xs text-text-muted">编辑中 #{editing.id}</span>}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button onClick={undo} disabled={history.length === 0} className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30" title="撤销 (Ctrl+Z)">
            <Undo2 size={16} />
          </button>
          <button onClick={redo} disabled={future.length === 0} className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30" title="重做 (Ctrl+Shift+Z)">
            <Redo2 size={16} />
          </button>
          <div className="w-px h-6 bg-border mx-1" />
          {/* V0.7.1: 复制 / 粘贴 / 段模板按钮 */}
          <button onClick={copySelected} disabled={selectedIds.size === 0 && editTarget?.type !== "block"} className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30" title="复制选中 (Ctrl+C / Ctrl+D)">
            <Copy size={16} />
          </button>
          <button onClick={() => pasteBlocks()} disabled={clipboardBlocks.length === 0} className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30" title={`粘贴 (Ctrl+V, 剪贴板 ${clipboardBlocks.length} 块)`}>
            <ClipboardPaste size={16} />
          </button>
          <button onClick={saveAsTemplate} disabled={selectedIds.size === 0 && editTarget?.type !== "block"} className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30" title="存为段模板">
            <BookmarkPlus size={16} />
          </button>
          {selectedIds.size > 0 && (
            <span className="text-[10px] text-text-muted px-1.5 py-0.5 rounded bg-accent/10 text-accent">
              已选 {selectedIds.size} 块
            </span>
          )}
          <div className="w-px h-6 bg-border mx-1" />
          <button onClick={() => setView("library")} className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary">
            ← 课程库
          </button>
          <button onClick={resetForm} className="px-3 py-1.5 bg-bg-elevated border border-border rounded-md text-sm hover:border-accent/50">
            新建
          </button>
          <button onClick={save} disabled={loading} className="btn-primary text-sm">
            <Save className="w-4 h-4" />
            {editing ? "更新" : "保存"}
          </button>
        </div>
      </div>

      {/* ============== 主体:三栏 ============== */}
      <div className="flex-1 flex min-h-0">

        {/* === V0.7.1 段模板区 (跨课程复用) === */}
        {segmentTemplates.length > 0 && (
          <div className="w-44 border-r border-border bg-gradient-to-b from-indigo-50/40 to-white p-2 flex-shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">段模板</div>
              <button
                onClick={clearTemplates}
                className="text-[10px] text-text-muted hover:text-rose-500"
                title="清空"
              >
                <X size={11} />
              </button>
            </div>
            <div className="space-y-1">
              {segmentTemplates.map((t, i) => {
                const label = t.kind === "single"
                  ? `${KIND_LABEL[t.step.kind] || t.step.kind} ${fmtBigTime(t.step.duration_s)} ${t.step.power_pct_ftp ? `${t.step.power_pct_ftp}% FTP` : ""}`
                  : `×${t.reps} ${KIND_LABEL[t.work?.kind || "main"]} ${fmtBigTime(t.work?.duration_s || 0)}${t.rest ? `+${fmtBigTime(t.rest.duration_s)} 恢复` : ""}`;
                return (
                  <button
                    key={`tpl-${i}`}
                    onClick={() => insertTemplate(t)}
                    className="w-full text-left p-1.5 rounded text-[10px] bg-white border border-indigo-200 hover:border-indigo-500 hover:bg-indigo-50 transition"
                    title="点击插入到末尾"
                  >
                    <div className="font-medium text-slate-700 truncate">{label}</div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* === 左侧积木库 === */}
        <BlockLibrary
          goal={goal}
          setGoal={setGoal}
          setIntensity={setIntensity}
          description={description}
          setDescription={setDescription}
          tags={tags}
          tagInput={tagInput}
          setTagInput={setTagInput}
          addTag={addTag}
          removeTag={removeTag}
          myWorkouts={myWorkouts}
          editingId={editing?.id}
          loadFromWorkout={loadFromWorkout}
          onDragStartNew={onDragStartNew}
          onDragStartExisting={onDragStartExisting}
          onDragEnd={onDragEnd}
          applyTemplate={applyTemplate}
          onClickMeta={() => setEditTarget({ type: "meta" })}
        />

        {/* === 中间时间轴 === */}
        <TimelineArea
          blocks={blocks}
          editTarget={editTarget}
          selectedIds={selectedIds}
          onSelectBlock={(id, modifiers) => {
            if (modifiers && (modifiers.shift || modifiers.meta)) {
              toggleBlockSelection(id, modifiers);
            } else {
              setEditTarget({ type: "block", blockId: id });
              setSelectedIds(new Set([id]));
              setLastSelectedId(id);
            }
          }}
          onSelectLoopPart={(bid, part) => setEditTarget({ type: "loop-part", blockId: bid, part })}
          onMoveUp={(id) => moveBlock(id, -1)}
          onMoveDown={(id) => moveBlock(id, 1)}
          onRemove={removeBlock}
          onDuplicate={duplicateBlock}
          onDragOver={onDragOver}
          onDrop={onDrop}
          dropIndex={dropIndex}
          draggedItem={draggedItem}
          onAddWarmup={(idx) => addSingleBlock("warmup", idx)}
          onAddMain={(idx) => addSingleBlock("main", idx)}
          onAddRecovery={(idx) => addSingleBlock("recovery", idx)}
          onAddCooldown={(idx) => addSingleBlock("cooldown", idx)}
          onAddLoop={(idx) => addLoopBlock(idx)}
        />

        {/* === 右侧实时编辑抽屉 === */}
        <EditPanel
          editTarget={editTarget}
          blocks={blocks}
          title={title}
          setTitle={setTitle}
          description={description}
          setDescription={setDescription}
          goal={goal}
          setGoal={setGoal}
          tags={tags}
          tagInput={tagInput}
          setTagInput={setTagInput}
          addTag={addTag}
          removeTag={removeTag}
          onClose={() => setEditTarget(null)}
          updateSingleStep={updateSingleStep}
          updateLoop={updateLoop}
          updateLoopPart={updateLoopPart}
          onRemove={(id) => { removeBlock(id); }}
          onDuplicate={duplicateBlock}
        />
      </div>

      {/* ============== 底部统计 ============== */}
      <div className="flex-shrink-0 bg-white/80 backdrop-blur border-t border-border px-5 py-2 flex items-center justify-between sticky bottom-0">
        <div className="flex items-center gap-5 text-sm">
          <Stat icon={Clock} label="总时长" value={fmtBigTime(totalDur)} accent />
          <Stat icon={Gauge} label="TSS 约" value={Math.round(totalTSS)} />
          <Stat icon={Activity} label="IF 约" value={(totalTSS / Math.max(totalDur / 60, 1) / 100 * 0.85).toFixed(2)} />
          <div className="text-xs text-text-muted">{blocks.length} 块积木 · 撤销栈 {history.length}</div>
        </div>
        <button onClick={save} disabled={loading || blocks.length === 0 || !title.trim()} className="btn-primary text-sm">
          <Save className="w-4 h-4" />
          {editing ? "更新课程" : "保存课程"}
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div className={clsx("fixed bottom-24 left-1/2 -translate-x-1/2 px-5 py-2.5 rounded-lg text-sm shadow-2xl z-50 font-medium",
          toast.kind === "ok" ? "bg-emerald-500 text-white" : "bg-red-500 text-white")}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// =============== 左侧积木库 ===============
function BlockLibrary(props: {
  goal: WorkoutGoal; setGoal: (g: WorkoutGoal) => void; setIntensity: (g: WorkoutGoal) => void;
  description: string; setDescription: (s: string) => void;
  tags: string[]; tagInput: string; setTagInput: (s: string) => void;
  addTag: () => void; removeTag: (t: string) => void;
  myWorkouts: Workout[]; editingId?: number;
  loadFromWorkout: (w: Workout) => void;
  onDragStartNew: (e: React.DragEvent, kind?: StepKind) => void;
  onDragStartExisting: (e: React.DragEvent, blockId: string) => void;
  onDragEnd: () => void;
  applyTemplate: (t: any) => void;
  onClickMeta: () => void;
}) {
  return (
    <div className="w-64 flex-shrink-0 border-r border-border overflow-auto bg-bg-elevated/40">
      {/* 基础信息 */}
      <div className="p-3 border-b border-border space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <select value={props.goal} onChange={(e) => {
            const g = e.target.value as WorkoutGoal;
            props.setGoal(g);
            props.setIntensity(g);
          }} className="px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent">
            {GOAL_OPTIONS.map((g) => (
              <option key={g.key} value={g.key}>{g.label}</option>
            ))}
          </select>
          <input
            value={props.description}
            onChange={(e) => props.setDescription(e.target.value)}
            onFocus={props.onClickMeta}
            placeholder="说明 (可选)"
            className="px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent"
          />
        </div>
        {/* 标签 */}
        <div>
          <div className="flex gap-1 flex-wrap items-center">
            {props.tags.map((t) => (
              <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-accent/15 text-accent font-medium flex items-center gap-1">
                {t}
                <button onClick={() => props.removeTag(t)} className="hover:text-red-500">×</button>
              </span>
            ))}
            <input
              value={props.tagInput}
              onChange={(e) => props.setTagInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), props.addTag())}
              onFocus={props.onClickMeta}
              placeholder="+ 标签"
              className="px-1.5 py-0.5 bg-white border border-border rounded text-[10px] w-16 focus:outline-none focus:border-accent"
            />
          </div>
          <div className="text-[10px] text-text-muted mt-1">推荐: {SUGGESTED_TAGS.slice(0, 5).join(", ")}</div>
        </div>
      </div>

      {/* 积木 - 基础段 (拖拽源) */}
      <div className="p-3 border-b border-border">
        <div className="text-xs font-semibold text-text-secondary mb-2 flex items-center gap-1.5">
          <Plus className="w-3 h-3" />
          基础段
          <span className="text-text-muted text-[10px] font-normal ml-auto">拖到中间</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {([
            { kind: "warmup" as StepKind, label: "热身", c: KIND_COLOR.warmup, icon: Flame },
            { kind: "main" as StepKind, label: "主项", c: KIND_COLOR.main, icon: Zap },
            { kind: "recovery" as StepKind, label: "间歇", c: KIND_COLOR.recovery, icon: Activity },
            { kind: "cooldown" as StepKind, label: "冷身", c: KIND_COLOR.cooldown, icon: Mountain },
          ]).map((b) => {
            const Icon = b.icon;
            return (
              <div
                key={b.kind}
                draggable
                onDragStart={(e) => props.onDragStartNew(e, b.kind)}
                onDragEnd={props.onDragEnd}
                className={clsx("px-2 py-2.5 rounded-lg text-xs font-semibold cursor-grab active:cursor-grabbing transition-all hover:scale-105 hover:shadow-md flex items-center gap-1.5 border-2", b.c.lightBg, b.c.text, b.c.border)}
                title={`拖拽: ${b.label}`}
              >
                <Icon className="w-3.5 h-3.5" />
                {b.label}
              </div>
            );
          })}
        </div>
      </div>

      {/* 积木 - 循环段 */}
      <div className="p-3 border-b border-border">
        <div className="text-xs font-semibold text-text-secondary mb-2 flex items-center gap-1.5">
          <Repeat className="w-3 h-3" />
          循环段
        </div>
        <div
          draggable
          onDragStart={(e) => { e.dataTransfer.setData("text/plain", "loop"); props.onDragStartNew(e); }}
          onDragEnd={props.onDragEnd}
          onClick={() => props.applyTemplate(QUICK_TEMPLATES[0])}
          className="w-full px-3 py-2.5 rounded-lg text-xs font-semibold cursor-grab active:cursor-grabbing transition-all hover:scale-105 hover:shadow-md bg-gradient-to-r from-amber-400 to-red-500 text-white border-2 border-amber-500 flex items-center justify-center gap-1.5"
          title="点击应用 VO2 5×3min 模板 / 或拖入"
        >
          <Repeat className="w-3.5 h-3.5" />
          + 循环块 (主项+间歇)
        </div>
        <div className="text-[10px] text-text-muted mt-1.5">适合间歇训练,设置重复次数</div>
      </div>

      {/* 快速模板 */}
      <div className="p-3 border-b border-border">
        <div className="text-xs font-semibold text-text-secondary mb-2 flex items-center gap-1.5">
          <Wand2 className="w-3 h-3" />
          快速模板 (一键填充)
        </div>
        <div className="space-y-1.5">
          {QUICK_TEMPLATES.map((t) => {
            const I = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => props.applyTemplate(t)}
                className={clsx("w-full px-3 py-2 rounded-md text-xs flex items-center gap-2 bg-gradient-to-r text-white font-medium hover:opacity-90 hover:scale-[1.02] transition-all", t.color)}
              >
                <I className="w-3.5 h-3.5" />
                <span className="flex-1 text-left">{t.label}</span>
                <Plus className="w-3 h-3" />
              </button>
            );
          })}
        </div>
      </div>

      {/* 我的课程 */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-text-secondary flex items-center gap-1.5">
            <BookOpen className="w-3 h-3" />
            我的课程
          </h3>
          <span className="text-[10px] text-text-muted bg-bg-elevated px-1.5 rounded">{props.myWorkouts.length}</span>
        </div>
        <div className="space-y-1 max-h-48 overflow-auto">
          {props.myWorkouts.map((w) => (
            <button
              key={w.id}
              onClick={() => props.loadFromWorkout(w)}
              className={clsx("w-full text-left p-2 rounded-md text-xs transition-all",
                props.editingId === w.id
                  ? "bg-accent/15 text-accent ring-2 ring-accent/30"
                  : "hover:bg-bg-elevated text-text-primary"
              )}
            >
              <div className="font-medium truncate">{w.title}</div>
              <div className="text-text-muted text-[10px] flex items-center gap-2 mt-0.5">
                <span>{w.goal}</span>
                <span>{w.duration_min}min</span>
              </div>
            </button>
          ))}
          {props.myWorkouts.length === 0 && (
            <div className="text-[10px] text-text-muted text-center py-2">还没有</div>
          )}
        </div>
      </div>
    </div>
  );
}

// =============== 中间时间轴 ===============
function TimelineArea(props: {
  blocks: Block[];
  editTarget: EditTarget;
  selectedIds: Set<string>;
  onSelectBlock: (id: string, modifiers?: { shift?: boolean; meta?: boolean }) => void;
  onSelectLoopPart: (blockId: string, part: "work" | "rest") => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onRemove: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDragOver: (e: React.DragEvent, idx: number) => void;
  onDrop: (e: React.DragEvent, idx: number) => void;
  dropIndex: number | null;
  draggedItem: any;
  onAddWarmup: (idx: number) => void;
  onAddMain: (idx: number) => void;
  onAddRecovery: (idx: number) => void;
  onAddCooldown: (idx: number) => void;
  onAddLoop: (idx: number) => void;
}) {
  const totalDur = blockTotal(props.blocks);
  return (
    <div className="flex-1 flex flex-col min-w-0">
      <div className="flex-1 overflow-auto p-4">
        {props.blocks.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-2 max-w-3xl mx-auto">
            {props.blocks.map((b, i) => (
              <div key={b.id}>
                {/* 插入占位 */}
                {props.dropIndex === i && (
                  <DropIndicator />
                )}
                <BlockCard
                  block={b}
                  index={i}
                  total={props.blocks.length}
                  totalDur={totalDur}
                  isSelected={isBlockSelected(b.id, props.editTarget)}
                  isMultiSelected={props.selectedIds.has(b.id)}
                  isPartSelected={isPartSelected(b.id, props.editTarget)}
                  onSelect={(modifiers) => props.onSelectBlock(b.id, modifiers)}
                  onSelectPart={(part) => props.onSelectLoopPart(b.id, part)}
                  onMoveUp={() => props.onMoveUp(b.id)}
                  onMoveDown={() => props.onMoveDown(b.id)}
                  onRemove={() => props.onRemove(b.id)}
                  onDuplicate={() => props.onDuplicate(b.id)}
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/plain", b.id);
                    // 调上层 handler
                    e.dataTransfer.effectAllowed = "move";
                    // 不直接调 onDragStartExisting, 这里通过 global 状态
                    document.dispatchEvent(new CustomEvent("block-drag-start", { detail: { blockId: b.id } }));
                  }}
                />
              </div>
            ))}
            {/* 末尾插入占位 */}
            {props.dropIndex === props.blocks.length && <DropIndicator />}
            {/* 末尾占位 (可拖入) */}
            <div
              onDragOver={(e) => { e.preventDefault(); }}
              onDrop={(e) => props.onDrop(e, props.blocks.length)}
              className="h-12 border-2 border-dashed border-border rounded-lg flex items-center justify-center text-xs text-text-muted hover:border-accent/50 hover:bg-accent/5 transition-all"
            >
              <Plus className="w-3 h-3 mr-1" />
              拖到这里添加到最后
            </div>
          </div>
        )}
        {props.blocks.length === 0 && <EmptyDropZone onAddLoop={props.onAddLoop} onDrop={props.onDrop} />}
      </div>
    </div>
  );
}

function isBlockSelected(id: string, t: EditTarget): boolean {
  if (!t) return false;
  if (t.type === "block" && t.blockId === id) return true;
  if (t.type === "loop-part" && t.blockId === id) return true;
  return false;
}
function isPartSelected(id: string, t: EditTarget): "work" | "rest" | null {
  if (!t || t.type !== "loop-part" || t.blockId !== id) return null;
  return t.part;
}

function DropIndicator() {
  return (
    <div className="h-1 my-1 rounded bg-accent shadow-[0_0_8px_rgba(99,102,241,0.5)] animate-pulse" />
  );
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-text-muted">
      <Layers className="w-16 h-16 mb-3 opacity-30" />
      <div className="text-sm">从左侧拖个积木过来,或点快速模板</div>
      <div className="text-xs mt-2">↑ 基础段 / 循环段 / 快速模板</div>
    </div>
  );
}

function EmptyDropZone({
  onAddLoop,
  onDrop,
}: {
  onAddLoop: (idx: number) => void;
  onDrop: (e: React.DragEvent, idx: number) => void;
}) {
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); }}
      onDrop={(e) => onDrop(e, 0)}
      className="mt-4 max-w-2xl mx-auto p-8 border-2 border-dashed border-border rounded-xl text-center hover:border-accent/50 hover:bg-accent/5 transition-all"
    >
      <div className="text-text-muted text-sm mb-3">从这里开始构建你的课程</div>
      <div className="text-text-muted text-[10px] mb-3">↑ 从左侧拖入积木, 或点击下方按钮</div>
      <div className="flex justify-center gap-2">
        <button onClick={() => onAddLoop(0)} className="px-4 py-2 bg-gradient-to-r from-amber-400 to-red-500 text-white rounded-md text-sm font-medium hover:opacity-90">
          <Repeat className="w-3.5 h-3.5 inline mr-1" /> 加循环块
        </button>
      </div>
    </div>
  );
}

// =============== Block 卡片 ===============
function BlockCard(props: {
  block: Block; index: number; total: number; totalDur: number;
  isSelected: boolean; isMultiSelected: boolean; isPartSelected: "work" | "rest" | null;
  onSelect: (modifiers?: { shift?: boolean; meta?: boolean }) => void; onSelectPart: (part: "work" | "rest") => void;
  onMoveUp: () => void; onMoveDown: () => void;
  onRemove: () => void; onDuplicate: () => void;
  onDragStart: (e: React.DragEvent) => void;
}) {
  if (props.block.kind === "single") {
    return <SingleBlockCard {...props} step={props.block.step} />;
  }
  return <LoopBlockCard {...props} block={props.block} />;
}

function SingleBlockCard(props: any) {
  const step = props.step as WorkoutStep;
  const c = KIND_COLOR[step.kind];
  const mins = Math.floor(step.duration_s / 60);
  const secs = step.duration_s % 60;

  return (
    <div
      onClick={(e) => props.onSelect({ shift: e.shiftKey, meta: e.metaKey || e.ctrlKey })}
      className={clsx(
        "group rounded-xl border-2 transition-all cursor-pointer overflow-hidden flex items-stretch h-16",
        props.isSelected
          ? `${c.ring} shadow-md border-current`
          : props.isMultiSelected
            ? "border-accent bg-accent/5"
            : "border-border hover:border-text-muted/40 hover:shadow-sm bg-white"
      )}
    >
      {/* 拖拽手柄 */}
      <div
        draggable
        onDragStart={props.onDragStart}
        className="w-6 flex items-center justify-center text-text-muted hover:text-text-primary cursor-grab active:cursor-grabbing"
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      {/* 左侧色块 */}
      <div className={clsx("w-20 flex flex-col items-center justify-center", c.bg, c.text)} style={{ color: "white" }}>
        <div className="text-[10px] opacity-80">#{props.index + 1}</div>
        <div className="text-xl font-bold leading-none">{mins}<span className="text-[10px] opacity-80">:{String(secs).padStart(2,"0")}</span></div>
        <div className="text-[9px] opacity-80 mt-0.5">{step.kind === "warmup" ? "热身" : step.kind === "main" ? "主项" : step.kind === "recovery" ? "间歇" : "冷身"}</div>
      </div>
      {/* 中间 */}
      <div className="flex-1 px-3 flex items-center gap-3 min-w-0">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{step.label || "(未命名)"}</div>
          <div className="text-[10px] text-text-muted flex items-center gap-2 mt-0.5">
            {step.power_pct_ftp && <span>⚡ {step.power_pct_ftp}%FTP</span>}
            {step.cadence_rpm && <span>🌀 {step.cadence_rpm}rpm</span>}
            {step.hr_pct_lthr && <span>💗 {step.hr_pct_lthr}%LTHR</span>}
          </div>
        </div>
      </div>
      {/* 操作 */}
      <div className="flex items-center px-1 opacity-0 group-hover:opacity-100 transition" onClick={(e) => e.stopPropagation()}>
        <IconBtn onClick={props.onMoveUp} disabled={props.index === 0} title="上移"><ChevronUp className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onMoveDown} disabled={props.index === props.total - 1} title="下移"><ChevronDown className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onDuplicate} title="复制"><Copy className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onRemove} title="删除" danger><Trash2 className="w-3 h-3" /></IconBtn>
      </div>
    </div>
  );
}

function LoopBlockCard(props: any) {
  const block = props.block as Extract<Block, { kind: "loop" }>;
  const oneDur = block.work.duration_s + (block.rest?.duration_s ?? 0);
  const totalDur = oneDur * block.reps;
  const mins = Math.floor(totalDur / 60);
  const secs = totalDur % 60;

  return (
    <div
      onClick={(e) => props.onSelect({ shift: e.shiftKey, meta: e.metaKey || e.ctrlKey })}
      className={clsx(
        "rounded-xl border-2 transition-all cursor-pointer overflow-hidden",
        props.isSelected
          ? "border-amber-500 ring-2 ring-amber-500/30 shadow-md bg-white"
          : props.isMultiSelected
            ? "border-accent bg-accent/5"
            : "border-amber-300/60 hover:border-amber-500 hover:shadow-sm bg-white"
      )}
    >
      {/* 拖拽手柄 + 头部 */}
      <div className="flex items-stretch h-9">
        <div
          draggable
          onDragStart={props.onDragStart}
          className="w-6 flex items-center justify-center text-text-muted hover:text-text-primary cursor-grab active:cursor-grabbing"
          onClick={(e) => e.stopPropagation()}
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
        <div className="flex-1 px-3 flex items-center gap-2 bg-gradient-to-r from-amber-50 to-orange-50">
          <Repeat className="w-3.5 h-3.5 text-amber-600" />
          <input
            value={block.label}
            onChange={(e) => { e.stopPropagation(); }}
            readOnly
            className="flex-1 bg-transparent text-sm font-semibold text-amber-900 outline-none px-1"
          />
          <span className="text-amber-600 text-sm font-bold">×</span>
          <input
            type="number"
            value={block.reps}
            readOnly
            className="w-10 px-1 py-0.5 bg-white border border-amber-300 rounded text-center text-sm font-bold text-amber-900"
          />
        </div>
        <div className="px-3 flex items-center text-xs font-semibold text-amber-900">
          {mins}<span className="text-[10px] opacity-70">:{String(secs).padStart(2,"0")}</span>
        </div>
      </div>
      {/* 内部 work+rest 缩略 (scratch 风格) */}
      <div className="flex">
        <button
          onClick={(e) => { e.stopPropagation(); props.onSelectPart("work"); }}
          className={clsx("flex-1 flex items-center gap-2 px-3 py-2 border-r border-border transition",
            props.isPartSelected === "work" ? "bg-amber-100" : "hover:bg-amber-50/50")}
        >
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500 text-white font-bold">主项</span>
          <span className="flex-1 text-xs text-left truncate">{block.work.label || "(未命名)"}</span>
          <span className="text-[10px] text-text-muted">
            {fmtTime(block.work.duration_s)} · {block.work.power_pct_ftp ?? "?"}%FTP
            {block.work.cadence_rpm ? ` · ${block.work.cadence_rpm}rpm` : ""}
          </span>
        </button>
        {block.rest && (
          <button
            onClick={(e) => { e.stopPropagation(); props.onSelectPart("rest"); }}
            className={clsx("flex-1 flex items-center gap-2 px-3 py-2 transition",
              props.isPartSelected === "rest" ? "bg-emerald-100" : "hover:bg-emerald-50/50")}
          >
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500 text-white font-bold">间歇</span>
            <span className="flex-1 text-xs text-left truncate">{block.rest.label || "(未命名)"}</span>
            <span className="text-[10px] text-text-muted">
              {fmtTime(block.rest.duration_s)} · {block.rest.power_pct_ftp ?? "?"}%FTP
            </span>
          </button>
        )}
      </div>
      {/* 底部操作 */}
      <div className="flex items-center justify-end px-2 py-1 bg-bg-elevated/50 border-t border-border/40 gap-0.5" onClick={(e) => e.stopPropagation()}>
        <IconBtn onClick={props.onMoveUp} disabled={props.index === 0} title="上移"><ChevronUp className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onMoveDown} disabled={props.index === props.total - 1} title="下移"><ChevronDown className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onDuplicate} title="复制"><Copy className="w-3 h-3" /></IconBtn>
        <IconBtn onClick={props.onRemove} title="删除" danger><Trash2 className="w-3 h-3" /></IconBtn>
      </div>
    </div>
  );
}

function IconBtn({ onClick, disabled, danger, title, children }: any) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      disabled={disabled}
      title={title}
      className={clsx(
        "p-1 rounded transition",
        danger ? "text-red-400 hover:bg-red-500/15" : "text-text-muted hover:text-text-primary hover:bg-bg-elevated",
        disabled && "opacity-30 cursor-not-allowed"
      )}
    >
      {children}
    </button>
  );
}

function Stat({ icon: Icon, label, value, accent }: any) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon className={clsx("w-3.5 h-3.5", accent ? "text-accent" : "text-text-muted")} />
      <span className="text-text-muted">{label}</span>
      <span className={clsx("font-bold text-base", accent ? "text-accent" : "text-text-primary")}>{value}</span>
    </div>
  );
}

// =============== 右侧实时编辑抽屉 (Scratch 风格:永远可见) ===============
function EditPanel(props: {
  editTarget: EditTarget;
  blocks: Block[];
  title: string; setTitle: (s: string) => void;
  description: string; setDescription: (s: string) => void;
  goal: WorkoutGoal; setGoal: (g: WorkoutGoal) => void;
  tags: string[]; tagInput: string; setTagInput: (s: string) => void;
  addTag: () => void; removeTag: (t: string) => void;
  onClose: () => void;
  updateSingleStep: (blockId: string, p: Partial<WorkoutStep>) => void;
  updateLoop: (blockId: string, p: any) => void;
  updateLoopPart: (blockId: string, part: "work" | "rest", p: Partial<WorkoutStep>) => void;
  onRemove: (id: string) => void;
  onDuplicate: (id: string) => void;
}) {
  const t = props.editTarget;
  // 找出当前选中的 block
  const block = t && (t.type === "block" || t.type === "loop-part")
    ? props.blocks.find((b) => b.id === t.blockId)
    : null;

  return (
    <div className="w-72 flex-shrink-0 border-l border-border bg-bg-elevated/40 overflow-auto">
      <div className="p-3 sticky top-0 bg-bg-elevated/95 backdrop-blur z-10 border-b border-border flex items-center justify-between">
        <div className="text-xs font-semibold text-text-secondary flex items-center gap-1.5">
          {t?.type === "meta" ? <Settings className="w-3.5 h-3.5 text-accent" /> :
            block ? <Pencil className="w-3.5 h-3.5 text-accent" /> :
            <Settings className="w-3.5 h-3.5 text-text-muted" />}
          {t?.type === "meta" ? "课程属性" :
            block ? (block.kind === "loop" ? "循环块" : "段落") :
            "未选择"}
        </div>
        {t && (
          <button onClick={props.onClose} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {!t && (
        <div className="p-6 text-center text-text-muted text-sm">
          <Pencil className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <div>点中间的积木</div>
          <div className="text-xs mt-1">在右侧编辑属性</div>
          <div className="mt-6 text-left text-[11px] leading-relaxed bg-bg-elevated rounded-lg p-3 space-y-1">
            <div className="font-semibold mb-1.5 flex items-center gap-1">💡 快捷键</div>
            <div><kbd className="px-1 bg-white border border-border rounded text-[10px]">Ctrl+Z</kbd> 撤销</div>
            <div><kbd className="px-1 bg-white border border-border rounded text-[10px]">Ctrl+Shift+Z</kbd> 重做</div>
            <div><kbd className="px-1 bg-white border border-border rounded text-[10px]">Ctrl+S</kbd> 保存</div>
            <div><kbd className="px-1 bg-white border border-border rounded text-[10px]">Del</kbd> 删除所选</div>
          </div>
        </div>
      )}

      {t?.type === "meta" && (
        <div className="p-3 space-y-3">
          <Field label="标题">
            <input
              value={props.title}
              onChange={(e) => props.setTitle(e.target.value)}
              className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent"
              autoFocus
            />
          </Field>
          <Field label="说明">
            <textarea
              value={props.description}
              onChange={(e) => props.setDescription(e.target.value)}
              rows={2}
              placeholder="课程说明 (可选)"
              className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent resize-none"
            />
          </Field>
          <Field label="训练目标">
            <select value={props.goal} onChange={(e) => props.setGoal(e.target.value as WorkoutGoal)} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent">
              {GOAL_OPTIONS.map((g) => (
                <option key={g.key} value={g.key}>{g.label}</option>
              ))}
            </select>
          </Field>
          <Field label="标签">
            <div className="space-y-1.5">
              <div className="flex gap-1 flex-wrap items-center">
                {props.tags.map((t) => (
                  <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-accent/15 text-accent font-medium flex items-center gap-1">
                    {t}
                    <button onClick={() => props.removeTag(t)} className="hover:text-red-500">×</button>
                  </span>
                ))}
              </div>
              <input
                value={props.tagInput}
                onChange={(e) => props.setTagInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), props.addTag())}
                placeholder="输入标签, 回车添加"
                className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent"
              />
              <div className="text-[10px] text-text-muted flex flex-wrap gap-1">
                {SUGGESTED_TAGS.slice(0, 8).map((t) => (
                  <button
                    key={t}
                    onClick={() => { if (!props.tags.includes(t)) props.setTagInput(t); props.addTag?.(); }}
                    className="px-1.5 py-0.5 rounded bg-bg-elevated hover:bg-accent/10 hover:text-accent"
                  >+ {t}</button>
                ))}
              </div>
            </div>
          </Field>
        </div>
      )}

      {/* 编辑 single block */}
      {t?.type === "block" && block?.kind === "single" && (
        <SingleBlockEditor
          step={block.step}
          onChange={(p) => props.updateSingleStep(block.id, p)}
          onDuplicate={() => props.onDuplicate(block.id)}
          onRemove={() => props.onRemove(block.id)}
        />
      )}

      {/* 编辑 loop block (整体) */}
      {t?.type === "block" && block?.kind === "loop" && (
        <LoopBlockEditor
          block={block}
          onChange={(p) => props.updateLoop(block.id, p)}
        />
      )}

      {/* 编辑 loop 部分 (work / rest) */}
      {t?.type === "loop-part" && block?.kind === "loop" && (
        <LoopPartEditor
          part={t.part}
          step={t.part === "work" ? block.work : block.rest!}
          onChange={(p) => props.updateLoopPart(block.id, t.part, p)}
        />
      )}
    </div>
  );
}

function Field({ label, children }: any) {
  return (
    <div>
      <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">{label}</label>
      {children}
    </div>
  );
}

function NumInput({ value, onChange, suffix, min, max, step }: {
  value: number | undefined | null;
  onChange: (v: number | undefined) => void;
  suffix?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? parseFloat(e.target.value) : undefined)}
        min={min} max={max} step={step ?? 1}
        className="flex-1 px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
      />
      {suffix && <span className="text-[10px] text-text-muted w-12">{suffix}</span>}
    </div>
  );
}

function SingleBlockEditor({ step, onChange, onDuplicate, onRemove }: {
  step: WorkoutStep;
  onChange: (p: Partial<WorkoutStep>) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const c = KIND_COLOR[step.kind as StepKind];
  return (
    <div className="p-3 space-y-3">
      <div className={clsx("p-3 rounded-lg", c.lightBg)}>
        <Field label="类型">
          <select
            value={step.kind}
            onChange={(e) => onChange({ kind: e.target.value as StepKind })}
            className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm font-medium focus:outline-none focus:border-accent"
          >
            <option value="warmup">🔥 热身</option>
            <option value="main">⚡ 主项</option>
            <option value="recovery">💧 间歇</option>
            <option value="cooldown">❄️ 冷身</option>
          </select>
        </Field>
        <div className="mt-2">
          <Field label="标签">
            <input
              value={step.label ?? ""}
              onChange={(e) => onChange({ label: e.target.value })}
              placeholder="如 '节奏主项'"
              className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent"
            />
          </Field>
        </div>
      </div>

      {/* 时长滑块 */}
      <div>
        <Field label={`时长 · ${fmtTime(step.duration_s)}`}>
          <input
            type="range"
            value={step.duration_s}
            min={30} max={7200} step={30}
            onChange={(e) => onChange({ duration_s: parseInt(e.target.value) })}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-text-muted mt-1">
            <span>30s</span><span>2h</span>
          </div>
          <NumInput value={step.duration_s} onChange={(v) => onChange({ duration_s: v })} suffix="秒" min={30} max={7200} step={30} />
        </Field>
      </div>

      {/* 强度 */}
      <div>
        <Field label={`功率 · ${step.power_pct_ftp ?? "?"}%FTP`}>
          <input
            type="range"
            value={step.power_pct_ftp ?? 75}
            min={40} max={200} step={5}
            onChange={(e) => onChange({ power_pct_ftp: parseInt(e.target.value) })}
            className="w-full accent-accent"
          />
          <NumInput value={step.power_pct_ftp} onChange={(v) => onChange({ power_pct_ftp: v })} suffix="%FTP" min={40} max={200} step={5} />
        </Field>
      </div>

      <div>
        <Field label={`心率 · ${step.hr_pct_lthr ?? "?"}%LTHR`}>
          <input
            type="range"
            value={step.hr_pct_lthr ?? 75}
            min={40} max={110} step={2}
            onChange={(e) => onChange({ hr_pct_lthr: parseInt(e.target.value) })}
            className="w-full accent-accent"
          />
          <NumInput value={step.hr_pct_lthr} onChange={(v) => onChange({ hr_pct_lthr: v })} suffix="%LTHR" min={40} max={110} step={2} />
        </Field>
      </div>

      <div>
        <Field label={`踏频 · ${step.cadence_rpm ?? "?"}rpm`}>
          <input
            type="range"
            value={step.cadence_rpm ?? 88}
            min={50} max={120} step={2}
            onChange={(e) => onChange({ cadence_rpm: parseInt(e.target.value) })}
            className="w-full accent-accent"
          />
          <NumInput value={step.cadence_rpm} onChange={(v) => onChange({ cadence_rpm: v })} suffix="rpm" min={50} max={120} step={2} />
        </Field>
      </div>

      <div className="flex gap-2 pt-2">
        <button onClick={onDuplicate} className="flex-1 btn-ghost text-xs"><Copy className="w-3 h-3" />复制</button>
        <button onClick={onRemove} className="flex-1 btn-ghost text-xs text-red-500 hover:text-red-600"><Trash2 className="w-3 h-3" />删除</button>
      </div>
    </div>
  );
}

function LoopBlockEditor({ block, onChange }: { block: Extract<Block, { kind: "loop" }>; onChange: (p: Partial<Extract<Block, { kind: "loop" }>>) => void }) {
  const oneDur = block.work.duration_s + (block.rest?.duration_s ?? 0);
  const total = oneDur * block.reps;
  return (
    <div className="p-3 space-y-3">
      <div className="p-3 rounded-lg bg-gradient-to-br from-amber-50 to-orange-50">
        <Field label="循环名">
          <input
            value={block.label}
            onChange={(e) => onChange({ label: e.target.value })}
            className="w-full px-2 py-1.5 bg-white border border-amber-300 rounded-md text-sm font-medium focus:outline-none focus:border-amber-500"
          />
        </Field>
        <div className="mt-2">
          <Field label={`重复次数 · ${block.reps} 次`}>
            <input
              type="range"
              value={block.reps}
              min={1} max={20} step={1}
              onChange={(e) => onChange({ reps: parseInt(e.target.value) })}
              className="w-full accent-amber-500"
            />
            <div className="flex justify-between text-[10px] text-text-muted mt-1">
              <span>1</span><span>20</span>
            </div>
          </Field>
        </div>
      </div>

      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">单次时长 · {fmtTime(oneDur)}</div>
      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">总时长 · {fmtBigTime(total)}</div>

      <div className="text-[10px] text-text-muted">点中间循环块内的"主项/间歇"行,可单独编辑</div>
    </div>
  );
}

function LoopPartEditor({ part, step, onChange }: {
  part: "work" | "rest";
  step: WorkoutStep;
  onChange: (p: Partial<WorkoutStep>) => void;
}) {
  return (
    <div className="p-3 space-y-3">
      <div className={clsx("p-3 rounded-lg", part === "work" ? "bg-amber-50" : "bg-emerald-50")}>
        <div className="text-xs font-bold mb-2 flex items-center gap-1.5">
          {part === "work" ? <Zap className="w-3.5 h-3.5 text-amber-600" /> : <Activity className="w-3.5 h-3.5 text-emerald-600" />}
          {part === "work" ? "主项 (Work)" : "间歇 (Rest)"}
        </div>
        <Field label="标签">
          <input
            value={step.label ?? ""}
            onChange={(e) => onChange({ label: e.target.value })}
            placeholder="如 '全力' / '主动恢复'"
            className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent"
          />
        </Field>
      </div>

      <Field label={`时长 · ${fmtTime(step.duration_s)}`}>
        <input
          type="range"
          value={step.duration_s}
          min={15} max={3600} step={15}
          onChange={(e) => onChange({ duration_s: parseInt(e.target.value) })}
          className="w-full accent-accent"
        />
        <NumInput value={step.duration_s} onChange={(v) => onChange({ duration_s: v })} suffix="秒" min={15} max={3600} step={15} />
      </Field>

      <Field label={`功率 · ${step.power_pct_ftp ?? "?"}%FTP`}>
        <input
          type="range"
          value={step.power_pct_ftp ?? 50}
          min={20} max={200} step={5}
          onChange={(e) => onChange({ power_pct_ftp: parseInt(e.target.value) })}
          className="w-full accent-accent"
        />
        <NumInput value={step.power_pct_ftp} onChange={(v) => onChange({ power_pct_ftp: v })} suffix="%FTP" min={20} max={200} step={5} />
      </Field>

      {part === "work" && (
        <Field label={`踏频 · ${step.cadence_rpm ?? "?"}rpm`}>
          <input
            type="range"
            value={step.cadence_rpm ?? 88}
            min={50} max={120} step={2}
            onChange={(e) => onChange({ cadence_rpm: parseInt(e.target.value) })}
            className="w-full accent-accent"
          />
          <NumInput value={step.cadence_rpm} onChange={(v) => onChange({ cadence_rpm: v })} suffix="rpm" min={50} max={120} step={2} />
        </Field>
      )}

      <Field label={`心率 · ${step.hr_pct_lthr ?? "?"}%LTHR`}>
        <input
          type="range"
          value={step.hr_pct_lthr ?? 65}
          min={40} max={110} step={2}
          onChange={(e) => onChange({ hr_pct_lthr: parseInt(e.target.value) })}
          className="w-full accent-accent"
        />
        <NumInput value={step.hr_pct_lthr} onChange={(v) => onChange({ hr_pct_lthr: v })} suffix="%LTHR" min={40} max={110} step={2} />
      </Field>
    </div>
  );
}

// =============== 数据转换 ===============
function blockTotal(blocks: Block[]): number {
  return blocks.reduce((s, b) => s + blockDuration(b), 0);
}
function computeTSS(blocks: Block[], goal: WorkoutGoal): number {
  const ifMap: Record<WorkoutGoal, number> = {
    recovery: 0.5, endurance: 0.65, tempo: 0.85,
    threshold: 0.95, vo2max: 1.2, race: 0.95,
  };
  const baseIf = ifMap[goal];
  let tss = 0;
  for (const b of blocks) {
    if (b.kind === "single") {
      const ifv = (b.step.power_pct_ftp ?? 75) / 100;
      tss += (b.step.duration_s / 3600) * ifv * ifv * 100;
    } else {
      const workIf = (b.work.power_pct_ftp ?? 100) / 100;
      tss += (b.work.duration_s / 3600) * workIf * workIf * 100 * b.reps;
      if (b.rest) {
        const restIf = (b.rest.power_pct_ftp ?? 50) / 100;
        tss += (b.rest.duration_s / 3600) * restIf * restIf * 100 * b.reps;
      }
    }
  }
  // 乘基础 goal IF
  return tss * (baseIf / 0.75);
}

function blocksToStructure(blocks: Block[]): any[] {
  // V0.7.4.2 修: 后端期望 list[StepIn], 不是 {version, blocks}
  // StepIn: { kind, duration_s, power_pct_ftp, hr_pct_lthr, cadence_rpm, label, repeat }
  return blocks.map((b) => {
    if (b.kind === "single") {
      // flat single step
      return { ...b.step, repeat: 1 };
    }
    // loop: 展开成 N 个 main + recovery
    const out: any[] = [];
    for (let i = 0; i < (b.reps || 1); i++) {
      out.push({ ...b.work, label: b.work?.label || `${b.label} 主项 ${i + 1}`, repeat: 1 });
      if (i < (b.reps || 1) - 1 || b.rest) {
        out.push({ ...b.rest, label: b.rest?.label || `${b.label} 间歇 ${i + 1}`, repeat: 1 });
      }
    }
    return out;
  }).flat();
}

function structureToBlocks(s: any): Block[] {
  if (!s) return [];
  // V0.7.4.2 修: 兼容 list / {version, blocks} 两种格式
  const arr = s.blocks || (Array.isArray(s) ? s : []);
  if (!Array.isArray(arr)) return [];
  return arr.map((b: any): Block | null => {
    if (b.kind === "loop") {
      return { id: rid(), kind: "loop", reps: b.reps, label: b.label, work: b.work, rest: b.rest };
    }
    if (b.step) {
      return { id: rid(), kind: "single", step: b.step };
    }
    // flat step (新格式)
    if (b.duration_s) {
      return { id: rid(), kind: "single", step: {
        kind: b.kind || "main",
        duration_s: b.duration_s,
        power_pct_ftp: b.power_pct_ftp,
        hr_pct_lthr: b.hr_pct_lthr,
        cadence_rpm: b.cadence_rpm,
        label: b.label,
      }};
    }
    return null;
  }).filter((x): x is Block => x !== null);
}
