// 课程库 — 浏览 / 搜索 / 筛选 / 复制 / 排到日历
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Filter,
  Copy, Download,
  Calendar,
  Trash2,
  X,
  ChevronRight,
  Sparkles,
  Tag,
  Clock,
  Check,
  Square,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import { useConfirm, ScheduleModal } from "../components/common";
import type {
  Workout,
  WorkoutGoal,
  GoalDef,
  WorkoutStep,
} from "../lib/types";
import { useNavigate } from "react-router-dom";

// intent/goals 配色(TP 风)
const GOAL_COLOR: Record<
  WorkoutGoal,
  { bg: string; text: string; ring: string; chip: string }
> = {
  recovery: {
    bg: "bg-status-info",
    text: "text-accent-primary",
    ring: "",
    chip: "bg-status-info text-accent-primary",
  },
  endurance: {
    bg: "bg-status-success/15",
    text: "text-accent-success",
    ring: "",
    chip: "bg-status-success/20 text-accent-success",
  },
  tempo: {
    bg: "bg-accent-warning/15",
    text: "text-accent-warning",
    ring: "",
    chip: "bg-accent-warning/20 text-accent-warning",
  },
  threshold: {
    bg: "bg-accent-warning/15",
    text: "text-accent-warning",
    ring: "",
    chip: "bg-accent-warning/20 text-accent-warning",
  },
  vo2max: {
    bg: "bg-accent-danger/15",
    text: "text-accent-danger",
    ring: "",
    chip: "bg-accent-danger/20 text-accent-danger",
  },
  race: {
    bg: "bg-status-info",
    text: "text-accent-primary",
    ring: "",
    chip: "bg-status-info text-accent-primary",
  },
};

const KIND_LABEL: Record<string, string> = {
  warmup: "热身",
  main: "主项",
  recovery: "间歇",
  cooldown: "冷身",
};

function fmtMin(m: number) {
  if (m < 60) return `${m}min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r > 0 ? `${h}h${r}min` : `${h}h`;
}

// V0.8.2 (B1-6): 批量排课 — 间隔模式
type BulkIntervalMode = "daily" | "every2" | "weekly";

const BULK_INTERVAL_LABEL: Record<BulkIntervalMode, string> = {
  daily: "每天",
  every2: "隔天",
  weekly: "每周指定日",
};

// 给定起始日期 + 间隔模式 + 周几 (0=周日, 1=周一, ..., 6=周六) → 计算 N 个日期字符串 (YYYY-MM-DD)
function computeBulkDates(
  startDate: string,
  n: number,
  mode: BulkIntervalMode,
  weekday: number
): string[] {
  const dates: string[] = [];
  if (n <= 0) return dates;
  // 起始日 00:00 本地时间
  const [y, m, d] = startDate.split("-").map((s) => parseInt(s, 10));
  let cur = new Date(y, m - 1, d);
  // weekly: 如果起始日不是目标周几, 先推进到下一个目标周几
  if (mode === "weekly") {
    const diff = (weekday - cur.getDay() + 7) % 7;
    if (diff > 0) {
      cur.setDate(cur.getDate() + diff);
    }
  }
  for (let i = 0; i < n; i++) {
    const yy = cur.getFullYear();
    const mm = String(cur.getMonth() + 1).padStart(2, "0");
    const dd = String(cur.getDate()).padStart(2, "0");
    dates.push(`${yy}-${mm}-${dd}`);
    if (mode === "daily") {
      cur.setDate(cur.getDate() + 1);
    } else if (mode === "every2") {
      cur.setDate(cur.getDate() + 2);
    } else {
      cur.setDate(cur.getDate() + 7);
    }
  }
  return dates;
}

function stepSummary(s: WorkoutStep): string {
  const parts: string[] = [];
  if (s.repeat && s.repeat > 1) parts.push(`×${s.repeat}`);
  if (s.label) parts.push(s.label);
  if (s.power_pct_ftp) parts.push(`${s.power_pct_ftp}%FTP`);
  const m = Math.floor(s.duration_s / 60);
  const sec = s.duration_s % 60;
  const dur = sec > 0 ? `${m}'${sec}"` : `${m}min`;
  return parts.length ? `${dur} ${parts.join(" ")}` : dur;
}

export function LibraryPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();

  const [q, setQ] = useState("");
  const [goal, setGoal] = useState<WorkoutGoal | "">("");
  const [tag, setTag] = useState("");
  const [source, setSource] = useState<"all" | "system" | "user">("all");
  const [goals, setGoals] = useState<GoalDef[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [list, setList] = useState<Workout[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Workout | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<{
    workout: Workout;
    date: string;
  } | null>(null);
  const [localToast, setLocalToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(
    null
  );
  const [repairing, setRepairing] = useState(false);
  // V0.8.2 (B1-6): 多选 + 批量加入日历
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkScheduleOpen, setBulkScheduleOpen] = useState(false);

  // 加载 goals + tags
  useEffect(() => {
    (async () => {
      const [g, t] = await Promise.all([
        api.listWorkoutGoals(),
        api.listWorkoutTags(),
      ]);
      setGoals(g.goals);
      setAllTags(t.tags);
    })();
  }, []);

  // 加载列表
  useEffect(() => {
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const params: Parameters<typeof api.listWorkouts>[0] = {
          limit: 100,
        };
        if (q.trim()) params.q = q.trim();
        if (goal) params.goal = goal;
        if (tag) params.tag = tag;
        if (source !== "all") params.source = source;
        const r = await api.listWorkouts(params);
        setList(r.workouts);
        setTotal(r.total);
      } catch (e: any) {
        const msg = e?.message ?? "加载失败";
        setLoadError(msg);
        showToast("err", "加载失败,见下方提示");
      } finally {
        setLoading(false);
      }
    })();
  }, [q, goal, tag, source]);

  async function onRepair() {
    const ok = await confirm({
      title: "一键修复数据库",
      message: "会自动加缺失列 + 重新 seed 29 个系统课程, 不会影响你的自建课程。",
      variant: "default",
      confirmText: "开始修复",
    });
    if (!ok) return;
    setRepairing(true);
    try {
      const r = await fetch("/api/dev/repair-db", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (data.ok) {
        toast.success(`修复完成! 课程总数: ${JSON.stringify(data.final_count)}`);
        showToast("ok", `修复完成! 课程总数: ${JSON.stringify(data.final_count)}`);
        // 刷新列表
        setSource((s) => (s === "all" ? "all" : "all"));
        setQ("");
        setGoal("");
        setTag("");
        setLoadError(null);
      } else {
        toast.error("修复失败: " + JSON.stringify(data));
        showToast("err", "修复失败: " + JSON.stringify(data));
      }
    } catch (e: any) {
      toast.error("修复失败: " + (e?.message ?? e));
      showToast("err", "修复失败: " + (e?.message ?? e));
    } finally {
      setRepairing(false);
    }
  }

  function showToast(kind: "ok" | "err", msg: string) {
    setLocalToast({ kind, msg });
    setTimeout(() => setLocalToast(null), 2200);
  }

  async function onDuplicate(w: Workout) {
    try {
      const r = await api.duplicateWorkout(w.id);
      showToast("ok", `已复制: ${r.title}`);
      // 刷新
      setSource(source);
    } catch (e) {
      showToast("err", "复制失败");
    }
  }

  async function onDelete(w: Workout) {
    if (w.source === "system") {
      showToast("err", "系统课程不能删除");
      return;
    }
    const ok = await confirm({
      title: "删除课程",
      message: `确定删除课程 "${w.title}" ? 此操作无法撤销。`,
      variant: "danger",
      confirmText: "删除",
    });
    if (!ok) return;
    try {
      await api.deleteWorkout(w.id);
      toast.success("已删除");
      showToast("ok", "已删除");
      setSelected(null);
      setSource(source); // 刷新
    } catch (e) {
      showToast("err", "删除失败");
    }
  }

  async function onScheduleSubmit(date: string) {
    if (!scheduleTarget) return;
    try {
      await api.scheduleWorkout(scheduleTarget.workout.id, date);
      showToast(
        "ok",
        `已排到 ${date},自动关联当天活动`
      );
      setScheduleTarget(null);
    } catch (e) {
      showToast("err", "排课失败");
    }
  }

  // V0.8.2 (B1-6): 批量排课 — 多选 toggle
  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function clearSelection() {
    setSelectedIds(new Set());
  }

  // V0.8.2 (B1-6): 批量提交 — 按间隔模式计算日期, 循环调 scheduleWorkout
  async function onBulkScheduleSubmit(
    startDate: string,
    mode: BulkIntervalMode,
    weekday: number
  ) {
    if (selectedIds.size === 0) return;
    // 按列表顺序排, 取稳定顺序 (先 user 后 system 已经在 API 层排过)
    const ordered = list.filter((w) => selectedIds.has(w.id));
    const dates = computeBulkDates(startDate, ordered.length, mode, weekday);
    setBulkScheduleOpen(false);
    let okCount = 0;
    let failCount = 0;
    for (let i = 0; i < ordered.length; i++) {
      try {
        await api.scheduleWorkout(ordered[i].id, dates[i]);
        okCount++;
      } catch (e) {
        failCount++;
      }
    }
    clearSelection();
    if (failCount === 0) {
      toast.success(`已批量加入 ${okCount} 个 workout`);
      showToast("ok", `已批量加入 ${okCount} 个 workout`);
    } else {
      toast.error(`成功 ${okCount}, 失败 ${failCount}`);
      showToast("err", `成功 ${okCount}, 失败 ${failCount}`);
    }
  }

  return (
    <div className="h-full flex bg-bg-base">
      {/* 主列表 */}
      <div className="flex-1 overflow-auto">
        <div className="p-6 max-w-6xl mx-auto">
          {/* 标题 */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-accent-warning" />
                课程库
              </h1>
              <p className="text-text-muted text-sm mt-1">
                29 套内置经典训练课 + 你的自建课程 · 一键排到日历
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => navigate("/plan")}
                className="px-4 py-2 bg-accent text-bg-base rounded font-medium hover:opacity-90"
              >
                + 新建课程
              </button>
            </div>
          </div>

          {/* 筛选区 */}
          <div className="bg-bg-subtle rounded p-4 mb-4 border border-border">
            <div className="flex gap-3 items-center mb-3">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="搜索标题 / 描述 / 标签..."
                  className="w-full pl-10 pr-3 py-2 bg-bg-base border border-border rounded text-sm focus:outline-none focus:border-accent"
                />
              </div>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value as any)}
                className="px-3 py-2 bg-bg-base border border-border rounded text-sm"
              >
                <option value="all">全部来源</option>
                <option value="system">系统课程</option>
                <option value="user">我的课程</option>
              </select>
            </div>

            {/* Goal 分类 */}
            <div className="flex gap-2 flex-wrap mb-2">
              <span className="text-xs text-text-muted flex items-center gap-1">
                <Filter className="w-3 h-3" />
                分类:
              </span>
              <button
                onClick={() => setGoal("")}
                className={clsx(
                  "px-3 py-1 rounded-md text-xs font-medium transition",
                  !goal
                    ? "bg-accent text-bg-base"
                    : "bg-bg-base text-text-muted hover:text-text-primary"
                )}
              >
                全部
              </button>
              {goals.map((g) => (
                <button
                  key={g.key}
                  onClick={() => setGoal(g.key as WorkoutGoal)}
                  className={clsx(
                    "px-3 py-1 rounded-md text-xs font-medium transition",
                    goal === g.key
                      ? "bg-accent text-bg-base"
                      : `${GOAL_COLOR[g.key].chip} hover:opacity-80`
                  )}
                >
                  {g.label}
                </button>
              ))}
            </div>

            {/* Tags */}
            {allTags.length > 0 && (
              <div className="flex gap-1.5 flex-wrap items-center">
                <span className="text-xs text-text-muted flex items-center gap-1">
                  <Tag className="w-3 h-3" />
                  标签:
                </span>
                <button
                  onClick={() => setTag("")}
                  className={clsx(
                    "px-2 py-0.5 rounded text-[10px]",
                    !tag
                      ? "bg-accent/20 text-accent"
                      : "bg-bg-base text-text-muted"
                  )}
                >
                  不限
                </button>
                {allTags.slice(0, 20).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTag(t === tag ? "" : t)}
                    className={clsx(
                      "px-2 py-0.5 rounded text-[10px]",
                      t === tag
                        ? "bg-accent/20 text-accent"
                        : "bg-bg-base text-text-muted hover:text-text-primary"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 错误 banner + 一键修复 */}
          {loadError && (
            <div className="mb-4 p-3 bg-accent-danger/10 border border-accent-danger rounded">
              <div className="text-sm text-accent-danger mb-2">
                ⚠️ 加载失败:{loadError}
              </div>
              <div className="text-xs text-text-muted mb-2">
                如果是从 V0.3.2 升级上来的,可能是数据库缺列。点下面按钮一键修复。
              </div>
              <button
                onClick={onRepair}
                disabled={repairing}
                className="px-3 py-1.5 bg-accent-danger/20 border border-accent-danger text-accent-danger rounded text-xs hover:bg-accent-danger/30 disabled:opacity-50"
              >
                {repairing ? "修复中..." : "🔧 一键修复数据库"}
              </button>
            </div>
          )}

          {/* 我的课程快捷区(用户自建) */}
          {source === "all" && list.some((w) => w.source === "user") && (
            <div className="mb-4 p-3 bg-bg-subtle border border-border rounded">
              <div className="text-xs font-semibold text-text-muted mb-2">
                📌 我的课程 ({list.filter((w) => w.source === "user").length})
              </div>
              <div className="flex gap-2 flex-wrap">
                {list
                  .filter((w) => w.source === "user")
                  .map((w) => (
                    <button
                      key={w.id}
                      onClick={() => setSelected(w)}
                      className="px-2 py-1 bg-bg-base border border-border rounded text-xs hover:border-accent"
                    >
                      {w.title}
                      <span className="text-text-muted ml-1">
                        {w.duration_min}min
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          )}

          {/* 统计 */}
          <div className="text-xs text-text-muted mb-3 flex items-center gap-3">
            <span>共 {total} 个课程</span>
            {loading && <span>加载中...</span>}
          </div>

          {/* V0.8.2 (B1-6): 多选批量加入日历 toolbar */}
          {selectedIds.size > 0 && (
            <div className="sticky top-0 z-10 mb-3 p-3 bg-accent/10 border border-accent/40 rounded flex items-center gap-3 backdrop-blur-sm">
              <span className="text-sm font-medium text-accent">
                已选 {selectedIds.size} 项
              </span>
              <div className="flex-1" />
              <button
                onClick={clearSelection}
                className="px-3 py-1.5 bg-bg-base border border-border rounded text-xs hover:border-accent/50"
              >
                清空选择
              </button>
              <button
                onClick={() => setBulkScheduleOpen(true)}
                className="px-3 py-1.5 bg-accent text-bg-base rounded text-sm font-medium flex items-center gap-1 hover:opacity-90"
              >
                <Calendar className="w-4 h-4" />
                📅 批量加入日历
              </button>
            </div>
          )}

          {/* 列表 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {list.map((w) => (
              <WorkoutCard
                key={w.id}
                w={w}
                selected={selectedIds.has(w.id)}
                onToggleSelect={() => toggleSelect(w.id)}
                onClick={() => setSelected(w)}
                onDuplicate={() => onDuplicate(w)}
                onSchedule={() =>
                  setScheduleTarget({
                    workout: w,
                    date: new Date().toISOString().slice(0, 10),
                  })
                }
              />
            ))}
          </div>

          {list.length === 0 && !loading && (
            <div className="text-center text-text-muted py-12">
              没有匹配的课程
            </div>
          )}
        </div>
      </div>

      {/* 详情面板 */}
      {selected && (
        <WorkoutDetailDrawer
          workout={selected}
          onClose={() => setSelected(null)}
          onSchedule={(date) => {
            setScheduleTarget({ workout: selected, date });
          }}
          onDelete={() => onDelete(selected)}
          onDuplicate={() => onDuplicate(selected)}
        />
      )}

      {/* 排课 modal */}
      {scheduleTarget && (
        <ScheduleModal
          workoutTitle={scheduleTarget.workout.title}
          onCancel={() => setScheduleTarget(null)}
          onConfirm={onScheduleSubmit}
        />
      )}

      {/* V0.8.2 (B1-6): 批量排课 modal */}
      {bulkScheduleOpen && (
        <BulkScheduleModal
          count={selectedIds.size}
          onCancel={() => setBulkScheduleOpen(false)}
          onConfirm={onBulkScheduleSubmit}
        />
      )}

      {/* Toast (局部, 只在 LibraryPage 用) */}
      {localToast && (
        <div
          className={clsx(
            "fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded text-sm shadow-sm z-50",
            localToast.kind === "ok"
              ? "bg-status-success/90 text-white"
              : "bg-accent-danger/90 text-white"
          )}
        >
          {localToast.msg}
        </div>
      )}
    </div>
  );
}

function WorkoutCard({
  w,
  selected,
  onToggleSelect,
  onClick,
  onDuplicate,
  onSchedule,
}: {
  w: Workout;
  selected: boolean;
  onToggleSelect: () => void;
  onClick: () => void;
  onDuplicate: () => void;
  onSchedule: () => void;
}) {
  const c = GOAL_COLOR[w.goal];
  const [isDragging, setIsDragging] = useState(false);

  // V0.8.3 (B1-1): HTML5 DnD 跨页 — 拖到 CalendarPage 加入计划
  function handleDragStart(e: React.DragEvent<HTMLDivElement>) {
    const payload = JSON.stringify({
      id: w.id,
      title: w.title,
      duration_min: w.duration_min,
      tss: null,
    });
    e.dataTransfer.setData("application/x-library-workout", payload);
    e.dataTransfer.setData("text/plain", w.title);
    e.dataTransfer.effectAllowed = "copy";
    setIsDragging(true);

    // 自定义 ghost 元素 (Safari 友好)
    if (e.dataTransfer.setDragImage) {
      const ghost = document.createElement("div");
      ghost.textContent = `📅 ${w.title} (${w.duration_min}min)`;
      ghost.style.cssText =
        "position:absolute;top:-1000px;left:0;padding:8px 12px;background:#1e293b;color:#fff;border-radius:8px;font-size:12px;font-family:system-ui,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.3);white-space:nowrap;";
      document.body.appendChild(ghost);
      e.dataTransfer.setDragImage(ghost, 0, 0);
      // 下一帧清理 (dragImage 必须仍在 DOM)
      requestAnimationFrame(() => document.body.removeChild(ghost));
    }
  }

  function handleDragEnd() {
    setIsDragging(false);
  }

  return (
    <div
      onClick={onClick}
      draggable={true}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      className={clsx(
        "bg-bg-subtle border rounded p-4 hover:border-accent/40 cursor-pointer transition group relative",
        selected ? "border-accent ring-1 ring-accent/40" : "border-border",
        isDragging && "opacity-50"
      )}
    >
      {/* V0.8.2 (B1-6): 多选 checkbox (hover 显示, 选中常显) */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect();
        }}
        title={selected ? "取消选择" : "加入批量"}
        className={clsx(
          "absolute top-3 right-3 w-5 h-5 rounded border flex items-center justify-center transition",
          selected
            ? "opacity-100 bg-accent border-accent text-bg-base"
            : "opacity-0 group-hover:opacity-100 bg-bg-base border-border text-text-muted hover:border-accent"
        )}
      >
        {selected ? <Check className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
      </button>
      <div className="flex items-start justify-between mb-2 pr-7">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={clsx(
                "px-2 py-0.5 rounded text-[10px] font-medium",
                c.chip
              )}
            >
              {w.goal}
            </span>
            {w.source === "system" && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-bg-base text-text-muted">
                系统
              </span>
            )}
            {w.source === "user" && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-accent/15 text-accent">
                自建
              </span>
            )}
          </div>
          <h3 className="font-semibold text-sm truncate group-hover:text-accent">
            {w.title}
          </h3>
        </div>
        <ChevronRight className="w-4 h-4 text-text-muted opacity-0 group-hover:opacity-100" />
      </div>

      {w.description && (
        <p className="text-xs text-text-muted line-clamp-2 mb-2">
          {w.description}
        </p>
      )}

      <div className="flex items-center gap-3 text-[11px] text-text-muted">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {fmtMin(w.duration_min)}
        </span>
        {w.structure && (
          <span>{w.structure.length} 段</span>
        )}
        {w.tags && w.tags.length > 0 && (
          <span className="truncate">{w.tags.slice(0, 3).join(" · ")}</span>
        )}
      </div>

      <div className="mt-2 pt-2 border-t border-border/50 flex justify-between items-center gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSchedule();
          }}
          title="加到日历 (拖拽备用入口)"
          className="text-[10px] text-text-muted hover:text-accent flex items-center gap-1"
        >
          <Calendar className="w-3 h-3" />
          + 加到日历
        </button>
        {w.source === "system" && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDuplicate();
            }}
            className="text-[10px] text-text-muted hover:text-accent flex items-center gap-1"
          >
            <Copy className="w-3 h-3" />
            复制到我的
          </button>
        )}
      </div>
    </div>
  );
}

function WorkoutDetailDrawer({
  workout,
  onClose,
  onSchedule,
  onDelete,
  onDuplicate,
}: {
  workout: Workout;
  onClose: () => void;
  onSchedule: (date: string) => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const c = GOAL_COLOR[workout.goal];
  const [scheduleDate, setScheduleDate] = useState(
    new Date().toISOString().slice(0, 10)
  );

  return (
    <div className="w-[480px] bg-bg-subtle border-l border-border flex flex-col">
      <div className="p-5 border-b border-border flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={clsx("px-2 py-0.5 rounded text-[10px] font-medium", c.chip)}>
              {workout.goal}
            </span>
            {workout.intensity && workout.intensity !== workout.goal && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-bg-base text-text-muted">
                {workout.intensity}
              </span>
            )}
          </div>
          <h2 className="text-lg font-bold mb-1">{workout.title}</h2>
          <div className="flex items-center gap-3 text-xs text-text-muted">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {fmtMin(workout.duration_min)}
            </span>
            <span>{workout.structure?.length ?? 0} 段</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-5 space-y-4">
        {workout.description && (
          <div>
            <h4 className="text-xs font-semibold text-text-muted mb-1">说明</h4>
            <p className="text-sm">{workout.description}</p>
          </div>
        )}

        {workout.structure && workout.structure.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-text-muted mb-2">
              课程结构
            </h4>
            <div className="space-y-1.5">
              {workout.structure.map((s, i) => {
                const repeat = s.repeat && s.repeat > 1 ? s.repeat : 1;
                return (
                  <div
                    key={i}
                    className="flex items-center gap-3 p-2 bg-bg-base rounded text-sm"
                  >
                    <span
                      className={clsx(
                        "w-12 text-[10px] text-center px-1.5 py-0.5 rounded",
                        s.kind === "warmup" && "bg-status-info text-accent-primary",
                        s.kind === "main" && "bg-accent-warning/20 text-accent-warning",
                        s.kind === "recovery" && "bg-status-success/20 text-accent-success",
                        s.kind === "cooldown" && "bg-bg-subtle0/30 text-text-muted"
                      )}
                    >
                      {KIND_LABEL[s.kind] ?? s.kind}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs">
                        {s.label ?? "—"}
                        {repeat > 1 && (
                          <span className="text-text-muted ml-1">
                            × {repeat}
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-text-muted">
                        {Math.floor(s.duration_s / 60)}min
                        {s.duration_s % 60 > 0 && ` ${s.duration_s % 60}s`}
                        {s.power_pct_ftp && ` · ${s.power_pct_ftp}%FTP`}
                        {s.cadence_rpm && ` · ${s.cadence_rpm}rpm`}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {workout.tags && workout.tags.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-text-muted mb-1">标签</h4>
            <div className="flex flex-wrap gap-1">
              {workout.tags.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded text-[10px] bg-bg-base text-text-muted"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="p-4 border-t border-border space-y-2">
        {/* 排到日历 */}
        <div className="flex gap-2">
          <input
            type="date"
            value={scheduleDate}
            onChange={(e) => setScheduleDate(e.target.value)}
            className="flex-1 px-3 py-2 bg-bg-base border border-border rounded text-sm"
          />
          <button
            onClick={() => onSchedule(scheduleDate)}
            className="px-3 py-2 bg-accent text-bg-base rounded text-sm font-medium flex items-center gap-1 hover:opacity-90"
          >
            <Calendar className="w-4 h-4" />
            排到日历
          </button>
        </div>
        {/* V0.7.1: 导出训练台格式 */}
        <div className="flex gap-2">
          <button
            onClick={() => downloadExport(workout.id, "zwo", workout.title)}
            className="flex-1 px-2 py-2 bg-accent-primary-soft0/10 border border-accent-primary/30 text-accent-primary rounded text-xs hover:bg-accent-primary-soft0/20 font-medium"
            title="Zwift 训练课程 (XML)"
          >
            <Download className="w-3 h-3 inline mr-1" />
            .zwo (Zwift)
          </button>
          <button
            onClick={() => downloadExport(workout.id, "mrc", workout.title)}
            className="flex-1 px-2 py-2 bg-cyan-500/10 border border-cyan-500/30 text-cyan-700 rounded text-xs hover:bg-cyan-500/20 font-medium"
            title="Rouvy / MiniRoad"
          >
            <Download className="w-3 h-3 inline mr-1" />
            .mrc (Rouvy)
          </button>
          <button
            onClick={() => downloadExport(workout.id, "erg", workout.title)}
            className="flex-1 px-2 py-2 bg-accent-warning/10 border border-accent-warning/30 text-accent-warning rounded text-xs hover:bg-accent-warning/20 font-medium"
            title="训练台通用 (CompuTrainer / TrainerRoad)"
          >
            <Download className="w-3 h-3 inline mr-1" />
            .erg
          </button>
        </div>
        <div className="flex gap-2">
          {workout.source === "system" && (
            <button
              onClick={onDuplicate}
              className="flex-1 px-3 py-2 bg-bg-base border border-border rounded text-sm hover:border-accent/50"
            >
              <Copy className="w-3.5 h-3.5 inline mr-1" />
              复制到我的
            </button>
          )}
          {workout.source !== "system" && (
            <button
              onClick={onDelete}
              className="flex-1 px-3 py-2 bg-accent-danger/10 border border-accent-danger text-accent-danger rounded text-sm hover:bg-accent-danger/20"
            >
              <Trash2 className="w-3.5 h-3.5 inline mr-1" />
              删除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// V0.7.1: 下载课程导出
function downloadExport(workoutId: number, format: "zwo" | "mrc" | "erg" | "json", title: string) {
  const url = `/api/workouts/${workoutId}/export?format=${format}`;
  // 直接浏览器打开, 让后端 Content-Disposition 控制文件名
  window.open(url, "_blank");
}

// V0.8.2 (B1-6): 批量排课 modal — 起始日 + 间隔模式
const WEEKDAY_LABEL: Record<number, string> = {
  0: "周日",
  1: "周一",
  2: "周二",
  3: "周三",
  4: "周四",
  5: "周五",
  6: "周六",
};

function BulkScheduleModal({
  count,
  onCancel,
  onConfirm,
}: {
  count: number;
  onCancel: () => void;
  onConfirm: (startDate: string, mode: BulkIntervalMode, weekday: number) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState(today);
  const [mode, setMode] = useState<BulkIntervalMode>("daily");
  const [weekday, setWeekday] = useState<number>(1);

  // 预览前 5 个日期
  const previewDates = computeBulkDates(startDate, Math.min(count, 5), mode, weekday);

  return (
    <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center">
      <div className="bg-bg-subtle rounded p-5 w-[420px] border border-border">
        <h3 className="font-semibold mb-1">批量加入日历</h3>
        <p className="text-xs text-text-muted mb-3">
          将 <span className="text-accent">{count}</span> 个 workout 按间隔排到日历:
        </p>

        <div className="space-y-3">
          {/* 起始日期 */}
          <div>
            <label className="text-xs text-text-muted block mb-1">起始日期</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2 bg-bg-base border border-border rounded text-sm"
            />
          </div>

          {/* 间隔模式 */}
          <div>
            <label className="text-xs text-text-muted block mb-1">间隔模式</label>
            <div className="flex gap-2">
              {(["daily", "every2", "weekly"] as BulkIntervalMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={clsx(
                    "flex-1 px-2 py-2 rounded text-xs font-medium border transition",
                    mode === m
                      ? "bg-accent text-bg-base border-accent"
                      : "bg-bg-base border-border text-text-muted hover:border-accent/50"
                  )}
                >
                  {BULK_INTERVAL_LABEL[m]}
                </button>
              ))}
            </div>
          </div>

          {/* weekly 模式: 选择周几 */}
          {mode === "weekly" && (
            <div>
              <label className="text-xs text-text-muted block mb-1">每周几</label>
              <div className="flex gap-1">
                {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                  <button
                    key={d}
                    onClick={() => setWeekday(d)}
                    className={clsx(
                      "flex-1 px-1 py-1.5 rounded text-[11px] font-medium border transition",
                      weekday === d
                        ? "bg-accent text-bg-base border-accent"
                        : "bg-bg-base border-border text-text-muted hover:border-accent/50"
                    )}
                  >
                    {WEEKDAY_LABEL[d]}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 预览 */}
          <div className="bg-bg-base border border-border rounded p-2">
            <div className="text-[10px] text-text-muted mb-1">
              预览 (前 {previewDates.length} 个):
            </div>
            <div className="text-xs font-mono space-y-0.5">
              {previewDates.map((d, i) => (
                <div key={i} className="text-text-primary">
                  #{i + 1} → {d}
                </div>
              ))}
              {count > previewDates.length && (
                <div className="text-text-muted">... 共 {count} 个</div>
              )}
            </div>
          </div>

          <p className="text-[10px] text-text-muted">
            💡 每个 workout 调用 <code className="text-accent">/workouts/:id/schedule</code> 一次
          </p>
        </div>

        <div className="flex gap-2 mt-4">
          <button
            onClick={onCancel}
            className="flex-1 px-3 py-2 bg-bg-base border border-border rounded text-sm"
          >
            取消
          </button>
          <button
            onClick={() => onConfirm(startDate, mode, weekday)}
            disabled={count === 0}
            className="flex-1 px-3 py-2 bg-accent text-bg-base rounded text-sm font-medium disabled:opacity-50"
          >
            确认 ({count})
          </button>
        </div>
      </div>
    </div>
  );
}
