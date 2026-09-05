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
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
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
    bg: "bg-sky-500/15",
    text: "text-sky-300",
    ring: "ring-sky-500/40",
    chip: "bg-sky-500/20 text-sky-200",
  },
  endurance: {
    bg: "bg-emerald-500/15",
    text: "text-emerald-300",
    ring: "ring-emerald-500/40",
    chip: "bg-emerald-500/20 text-emerald-200",
  },
  tempo: {
    bg: "bg-amber-500/15",
    text: "text-amber-300",
    ring: "ring-amber-500/40",
    chip: "bg-amber-500/20 text-amber-200",
  },
  threshold: {
    bg: "bg-orange-500/15",
    text: "text-orange-300",
    ring: "ring-orange-500/40",
    chip: "bg-orange-500/20 text-orange-200",
  },
  vo2max: {
    bg: "bg-red-500/15",
    text: "text-red-300",
    ring: "ring-red-500/40",
    chip: "bg-red-500/20 text-red-200",
  },
  race: {
    bg: "bg-fuchsia-500/15",
    text: "text-fuchsia-300",
    ring: "ring-fuchsia-500/40",
    chip: "bg-fuchsia-500/20 text-fuchsia-200",
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
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(
    null
  );
  const [repairing, setRepairing] = useState(false);

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
    if (!confirm("一键修复数据库?\n会自动加缺失列 + 重新 seed 29 个系统课程")) return;
    setRepairing(true);
    try {
      const r = await fetch("/api/dev/repair-db", { method: "POST" });
      const data = await r.json();
      if (data.ok) {
        showToast("ok", `修复完成! 课程总数: ${JSON.stringify(data.final_count)}`);
        // 刷新列表
        setSource((s) => (s === "all" ? "all" : "all"));
        setQ("");
        setGoal("");
        setTag("");
        setLoadError(null);
      } else {
        showToast("err", "修复失败: " + JSON.stringify(data));
      }
    } catch (e: any) {
      showToast("err", "修复失败: " + (e?.message ?? e));
    } finally {
      setRepairing(false);
    }
  }

  function showToast(kind: "ok" | "err", msg: string) {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 2200);
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
    if (!confirm(`删除课程 "${w.title}" ?`)) return;
    try {
      await api.deleteWorkout(w.id);
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

  return (
    <div className="h-full flex bg-bg-base">
      {/* 主列表 */}
      <div className="flex-1 overflow-auto">
        <div className="p-6 max-w-6xl mx-auto">
          {/* 标题 */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-amber-400" />
                课程库
              </h1>
              <p className="text-text-muted text-sm mt-1">
                29 套内置经典训练课 + 你的自建课程 · 一键排到日历
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => navigate("/plan")}
                className="px-4 py-2 bg-accent text-bg-base rounded-lg font-medium hover:opacity-90"
              >
                + 新建课程
              </button>
            </div>
          </div>

          {/* 筛选区 */}
          <div className="bg-bg-elevated rounded-xl p-4 mb-4 border border-border">
            <div className="flex gap-3 items-center mb-3">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="搜索标题 / 描述 / 标签..."
                  className="w-full pl-10 pr-3 py-2 bg-bg-base border border-border rounded-lg text-sm focus:outline-none focus:border-accent"
                />
              </div>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value as any)}
                className="px-3 py-2 bg-bg-base border border-border rounded-lg text-sm"
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
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
              <div className="text-sm text-red-300 mb-2">
                ⚠️ 加载失败:{loadError}
              </div>
              <div className="text-xs text-text-muted mb-2">
                如果是从 V0.3.2 升级上来的,可能是数据库缺列。点下面按钮一键修复。
              </div>
              <button
                onClick={onRepair}
                disabled={repairing}
                className="px-3 py-1.5 bg-red-500/20 border border-red-500/40 text-red-200 rounded text-xs hover:bg-red-500/30 disabled:opacity-50"
              >
                {repairing ? "修复中..." : "🔧 一键修复数据库"}
              </button>
            </div>
          )}

          {/* 我的课程快捷区(用户自建) */}
          {source === "all" && list.some((w) => w.source === "user") && (
            <div className="mb-4 p-3 bg-bg-elevated border border-border rounded-lg">
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

          {/* 列表 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {list.map((w) => (
              <WorkoutCard
                key={w.id}
                w={w}
                onClick={() => setSelected(w)}
                onDuplicate={() => onDuplicate(w)}
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

      {/* Toast */}
      {toast && (
        <div
          className={clsx(
            "fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm shadow-lg z-50",
            toast.kind === "ok"
              ? "bg-emerald-500/90 text-white"
              : "bg-red-500/90 text-white"
          )}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

function WorkoutCard({
  w,
  onClick,
  onDuplicate,
}: {
  w: Workout;
  onClick: () => void;
  onDuplicate: () => void;
}) {
  const c = GOAL_COLOR[w.goal];
  return (
    <div
      onClick={onClick}
      className="bg-bg-elevated border border-border rounded-xl p-4 hover:border-accent/40 cursor-pointer transition group"
    >
      <div className="flex items-start justify-between mb-2">
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

      {w.source === "system" && (
        <div className="mt-2 pt-2 border-t border-border/50 flex justify-end">
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
        </div>
      )}
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
    <div className="w-[480px] bg-bg-elevated border-l border-border flex flex-col">
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
                        s.kind === "warmup" && "bg-sky-500/20 text-sky-300",
                        s.kind === "main" && "bg-amber-500/20 text-amber-300",
                        s.kind === "recovery" && "bg-emerald-500/20 text-emerald-300",
                        s.kind === "cooldown" && "bg-slate-500/30 text-slate-300"
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
            className="flex-1 px-3 py-2 bg-bg-base border border-border rounded-lg text-sm"
          />
          <button
            onClick={() => onSchedule(scheduleDate)}
            className="px-3 py-2 bg-accent text-bg-base rounded-lg text-sm font-medium flex items-center gap-1 hover:opacity-90"
          >
            <Calendar className="w-4 h-4" />
            排到日历
          </button>
        </div>
        {/* V0.7.1: 导出训练台格式 */}
        <div className="flex gap-2">
          <button
            onClick={() => downloadExport(workout.id, "zwo", workout.title)}
            className="flex-1 px-2 py-2 bg-indigo-500/10 border border-indigo-500/30 text-indigo-700 rounded-lg text-xs hover:bg-indigo-500/20 font-medium"
            title="Zwift 训练课程 (XML)"
          >
            <Download className="w-3 h-3 inline mr-1" />
            .zwo (Zwift)
          </button>
          <button
            onClick={() => downloadExport(workout.id, "mrc", workout.title)}
            className="flex-1 px-2 py-2 bg-cyan-500/10 border border-cyan-500/30 text-cyan-700 rounded-lg text-xs hover:bg-cyan-500/20 font-medium"
            title="Rouvy / MiniRoad"
          >
            <Download className="w-3 h-3 inline mr-1" />
            .mrc (Rouvy)
          </button>
          <button
            onClick={() => downloadExport(workout.id, "erg", workout.title)}
            className="flex-1 px-2 py-2 bg-amber-500/10 border border-amber-500/30 text-amber-700 rounded-lg text-xs hover:bg-amber-500/20 font-medium"
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
              className="flex-1 px-3 py-2 bg-bg-base border border-border rounded-lg text-sm hover:border-accent/50"
            >
              <Copy className="w-3.5 h-3.5 inline mr-1" />
              复制到我的
            </button>
          )}
          {workout.source !== "system" && (
            <button
              onClick={onDelete}
              className="flex-1 px-3 py-2 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm hover:bg-red-500/20"
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

function ScheduleModal({
  workoutTitle,
  onCancel,
  onConfirm,
}: {
  workoutTitle: string;
  onCancel: () => void;
  onConfirm: (date: string) => void;
}) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  return (
    <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center">
      <div className="bg-bg-elevated rounded-xl p-5 w-[360px] border border-border">
        <h3 className="font-semibold mb-2">排到日历</h3>
        <p className="text-xs text-text-muted mb-3">
          将课程 <span className="text-accent">{workoutTitle}</span> 加到:
        </p>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full px-3 py-2 bg-bg-base border border-border rounded-lg text-sm mb-3"
        />
        <p className="text-[10px] text-text-muted mb-3">
          💡 当天有活动会自动关联,完成度会更新
        </p>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 px-3 py-2 bg-bg-base border border-border rounded-lg text-sm"
          >
            取消
          </button>
          <button
            onClick={() => onConfirm(date)}
            className="flex-1 px-3 py-2 bg-accent text-bg-base rounded-lg text-sm font-medium"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}
