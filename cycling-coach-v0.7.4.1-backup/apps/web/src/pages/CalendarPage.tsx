// 日历页 — V0.5 全新设计
// 重点改进 (V0.5):
//   1. 日格点 → 弹出 Popover (不用 modal): 快速建课/编辑/拖入
//   2. 计划课支持跨日拖拽 (HTML5 DnD)
//   3. 顶部"快速排课"模板条: 4 个一键应用模板
//   4. 4 种意图用 zone 颜色一致
//   5. 实际活动悬停显示详情
import { useEffect, useMemo, useState, useRef } from "react";
import {
  ChevronLeft, ChevronRight, Plus, X, Trash2, Link2, Unlink, Sparkles,
  GripVertical, Wand2, Target, Calendar as CalIcon, Activity, Clock, Flame,
  ArrowRight,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type {
  CalendarMonth, PlanPeriod, PlannedWorkout, PlannedStatus, WorkoutIntent, ActualActivity, ActivitySummary,
} from "../lib/types";
import { useAppStore } from "../store/useAppStore";

// 训练意图 → 颜色 (TP 风格, 更饱和)
const INTENT_COLORS: Record<WorkoutIntent, { bg: string; border: string; text: string; light: string; ring: string }> = {
  recovery:    { bg: "bg-sky-500",    border: "border-sky-500/60",    text: "text-white",     light: "bg-sky-50",    ring: "ring-sky-500/30" },
  endurance:   { bg: "bg-emerald-500", border: "border-emerald-500/60", text: "text-white",     light: "bg-emerald-50", ring: "ring-emerald-500/30" },
  tempo:       { bg: "bg-amber-500",  border: "border-amber-500/60",  text: "text-white",     light: "bg-amber-50",  ring: "ring-amber-500/30" },
  threshold:   { bg: "bg-orange-500", border: "border-orange-500/60", text: "text-white",     light: "bg-orange-50", ring: "ring-orange-500/30" },
  vo2max:      { bg: "bg-red-500",    border: "border-red-500/60",    text: "text-white",     light: "bg-red-50",    ring: "ring-red-500/30" },
  race:        { bg: "bg-fuchsia-500",border: "border-fuchsia-500/60",text: "text-white",     light: "bg-fuchsia-50",ring: "ring-fuchsia-500/30" },
};

const INTENT_LABEL: Record<WorkoutIntent, string> = {
  recovery: "恢复", endurance: "耐力 Z2", tempo: "节奏 Z3", threshold: "阈值 Z4", vo2max: "VO2 Z5", race: "比赛",
};
const INTENT_ICON: Record<WorkoutIntent, any> = {
  recovery: Activity, endurance: Target, tempo: Flame, threshold: Flame, vo2max: Flame, race: Sparkles,
};
const INTENT_DEFAULT: Record<WorkoutIntent, { duration: number; tss: number }> = {
  recovery:  { duration: 60,  tss: 30 },
  endurance: { duration: 90,  tss: 60 },
  tempo:     { duration: 75,  tss: 70 },
  threshold: { duration: 75,  tss: 85 },
  vo2max:    { duration: 75,  tss: 100 },
  race:      { duration: 120, tss: 120 },
};

// 快速排课模板 (点 → 弹窗创建)
const QUICK_PLANS: { key: WorkoutIntent; label: string; icon: any; color: string; defaultTitle: string }[] = [
  { key: "endurance", label: "耐力 Z2", icon: Target, color: "from-emerald-500 to-emerald-600", defaultTitle: "耐力骑行" },
  { key: "tempo",     label: "节奏 Z3", icon: Flame, color: "from-amber-500 to-amber-600", defaultTitle: "节奏训练" },
  { key: "threshold", label: "阈值 Z4", icon: Flame, color: "from-orange-500 to-orange-600", defaultTitle: "阈值训练" },
  { key: "vo2max",    label: "VO2 Z5", icon: Flame, color: "from-red-500 to-red-600", defaultTitle: "VO2max 训练" },
  { key: "recovery",  label: "恢复", icon: Activity, color: "from-sky-500 to-sky-600", defaultTitle: "恢复骑行" },
  { key: "race",      label: "比赛", icon: Sparkles, color: "from-fuchsia-500 to-fuchsia-600", defaultTitle: "比赛日" },
];

export function CalendarPage() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [data, setData] = useState<CalendarMonth | null>(null);
  const [plans, setPlans] = useState<PlanPeriod[]>([]);
  const [activities, setActivities] = useState<ActivitySummary[]>([]);
  const [loading, setLoading] = useState(true);

  // Popover 状态 (替代 modal)
  const [popover, setPopover] = useState<
    | { mode: "new"; date: string; intent: WorkoutIntent; x: number; y: number }
    | { mode: "edit"; planned: PlannedWorkout; x: number; y: number }
    | { mode: "actual"; activities: ActualActivity[]; x: number; y: number }
    | null
  >(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // 拖拽 (跨日)
  const [draggingPlannedId, setDraggingPlannedId] = useState<number | null>(null);
  const [dropDate, setDropDate] = useState<string | null>(null);

  const setView = useAppStore((s) => s.setView);
  const setSelectedActivity = useAppStore((s) => s.setSelectedActivity);

  const refresh = async () => {
    setLoading(true);
    try {
      const [cal, pls, acts] = await Promise.all([
        api.getCalendar(year, month),
        api.listPlans(),
        api.listActivities({ limit: 200 }),
      ]);
      setData(cal);
      setPlans(pls.plans);
      setActivities(acts.activities);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [year, month]);

  // 点 popover 外关闭
  useEffect(() => {
    if (!popover) return;
    const h = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopover(null);
      }
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setPopover(null); };
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", h);
      document.removeEventListener("keydown", esc);
    };
  }, [popover]);

  const prev = () => {
    if (month === 1) { setYear((y) => y - 1); setMonth(12); }
    else { setMonth((m) => m - 1); }
  };
  const next = () => {
    if (month === 12) { setYear((y) => y + 1); setMonth(1); }
    else { setMonth((m) => m + 1); }
  };
  const jumpToday = () => { setYear(today.getFullYear()); setMonth(today.getMonth() + 1); };

  const monthLabel = useMemo(() => `${year} 年 ${month} 月`, [year, month]);

  // 自动关联
  const handleAutoLink = async () => {
    const r = await api.autoLinkMonth(year, month);
    alert(`已自动关联 ${r.linked} / ${r.total} 个计划课`);
    refresh();
  };

  // 计划课拖拽
  function onPlannedDragStart(e: React.DragEvent, id: number) {
    setDraggingPlannedId(id);
    e.dataTransfer.effectAllowed = "move";
  }
  function onPlannedDragEnd() { setDraggingPlannedId(null); setDropDate(null); }
  async function onPlannedDrop(date: string) {
    if (!draggingPlannedId) return;
    try {
      await api.updatePlanned(draggingPlannedId, { scheduled_date: date });
      refresh();
    } catch (e: any) {
      alert("移动失败: " + e.message);
    }
    setDraggingPlannedId(null);
    setDropDate(null);
  }

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex-shrink-0 px-6 pt-6 pb-3">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
              <CalIcon className="w-6 h-6 text-accent" />
              训练日历
            </h1>
            <p className="text-xs text-text-muted mt-1">计划课与实际训练的双轨视图 · 完成度自动统计 · 拖拽跨日改期</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleAutoLink} className="btn-ghost text-xs" title="把当月所有未关联的计划课,自动关联到当天的真实活动">
              <Link2 className="w-3.5 h-3.5" />自动关联
            </button>
            <button onClick={() => setPopover({ mode: "new", date: todayIso(today), intent: "endurance", x: 200, y: 200 })} className="btn-primary text-sm">
              <Plus className="w-4 h-4" />新建计划
            </button>
          </div>
        </div>

        {/* 月份切换 + 快速排课模板 */}
        <div className="flex items-center gap-2 panel p-2.5">
          <button onClick={prev} className="p-1.5 rounded-md hover:bg-bg-elevated text-text-secondary">
            <ChevronLeft size={18} />
          </button>
          <div className="px-3 text-base font-bold min-w-[110px] text-center">{monthLabel}</div>
          <button onClick={next} className="p-1.5 rounded-md hover:bg-bg-elevated text-text-secondary">
            <ChevronRight size={18} />
          </button>
          <button onClick={jumpToday} className="text-xs px-2 py-1 rounded text-accent hover:bg-accent/10 font-medium">今天</button>

          <div className="w-px h-5 bg-border mx-1" />

          <div className="flex items-center gap-1.5 flex-1 overflow-x-auto">
            <span className="text-xs text-text-muted flex items-center gap-1 flex-shrink-0">
              <Wand2 className="w-3 h-3" />快速排课:
            </span>
            {QUICK_PLANS.map((qp) => {
              const Icon = qp.icon;
              return (
                <button
                  key={qp.key}
                  onClick={() => setPopover({ mode: "new", date: todayIso(today), intent: qp.key, x: 200, y: 200 })}
                  className={clsx("px-2 py-1 rounded text-[11px] font-medium text-white bg-gradient-to-r flex items-center gap-1 hover:opacity-90 hover:scale-105 transition-all flex-shrink-0", qp.color)}
                  title={`快速创建 ${qp.label} 课`}
                >
                  <Icon className="w-3 h-3" />
                  {qp.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 月度统计 */}
        {data?.stats && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mt-2.5">
            <StatBox label="计划课" value={data.stats.planned_count} unit="次" />
            <StatBox label="完成度" value={data.stats.completion_rate} unit="%" accent={data.stats.completion_rate >= 80 ? "good" : data.stats.completion_rate >= 50 ? "warn" : "bad"} />
            <StatBox label="实际训练" value={data.stats.actual_activities} unit="次" />
            <StatBox label="总负荷" value={data.stats.actual_tss_total} unit="TSS" hint={`${data.stats.actual_hours_total} 小时`} />
          </div>
        )}
      </div>

      {/* 日历主体 */}
      <div className="flex-1 overflow-auto px-6 pb-4">
        {data && (
          <div className="panel p-2.5">
            {/* 周表头 */}
            <div className="grid grid-cols-7 gap-1 mb-1">
              {["一", "二", "三", "四", "五", "六", "日"].map((w) => (
                <div key={w} className="text-xs text-text-muted text-center py-1.5 font-semibold">
                  {w}
                </div>
              ))}
            </div>
            {/* 网格 */}
            <div className="grid grid-cols-7 gap-1">
              {data.weeks.flat().map((day, idx) => {
                if (day === 0) return <div key={idx} className="aspect-square" />;
                const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                const isToday = dateStr === todayIso(today);
                const planned = data.planned_by_day[dateStr] || [];
                const actual = data.actual_by_day[dateStr] || [];
                return (
                  <DayCell
                    key={idx}
                    day={day}
                    dateStr={dateStr}
                    isToday={isToday}
                    planned={planned}
                    actual={actual}
                    dropDate={dropDate}
                    isDraggingPlannedId={draggingPlannedId}
                    onCellClick={(e) => {
                      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      setPopover({ mode: "new", date: dateStr, intent: "endurance", x: rect.left, y: rect.bottom + 4 });
                    }}
                    onPlannedClick={(e, p) => {
                      e.stopPropagation();
                      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      setPopover({ mode: "edit", planned: p, x: rect.left, y: rect.bottom + 4 });
                    }}
                    onActualClick={(e) => {
                      e.stopPropagation();
                      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      setPopover({ mode: "actual", activities: actual, x: rect.left, y: rect.bottom + 4 });
                    }}
                    onPlannedDragStart={onPlannedDragStart}
                    onPlannedDragEnd={onPlannedDragEnd}
                    onPlannedDrop={onPlannedDrop}
                    onDropHover={(d) => setDropDate(d)}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* 图例 */}
        <div className="mt-3 panel p-2.5">
          <div className="text-xs text-text-muted mb-1.5 font-semibold">训练意图</div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            {Object.entries(INTENT_LABEL).map(([k, v]) => (
              <span key={k} className={clsx("px-2 py-1 rounded-md border-2 font-medium", INTENT_COLORS[k as WorkoutIntent].light, INTENT_COLORS[k as WorkoutIntent].border)} style={{ color: INTENT_COLORS[k as WorkoutIntent].bg.replace("bg-", "").replace("-500", "") }}>
                <span className={clsx("inline-block w-2 h-2 rounded-full mr-1 align-middle", INTENT_COLORS[k as WorkoutIntent].bg)} />
                {v}
              </span>
            ))}
            <span className="px-2 py-1 rounded-md border-2 border-emerald-500/60 bg-emerald-50 text-emerald-700 font-medium">
              <span className="inline-block w-2 h-2 rounded-full mr-1 align-middle bg-emerald-500" />已完成
            </span>
          </div>
        </div>

        {loading && <div className="text-text-muted text-sm text-center py-6">加载中…</div>}
      </div>

      {/* Popover (替代 modal) */}
      {popover && (
        <div
          ref={popoverRef}
          className="fixed z-50 bg-white rounded-xl shadow-2xl border border-border w-80 overflow-hidden"
          style={{ left: Math.min(popover.x, window.innerWidth - 340), top: Math.min(popover.y, window.innerHeight - 400) }}
          onClick={(e) => e.stopPropagation()}
        >
          {popover.mode === "new" && (
            <NewPlannedPopover
              defaultDate={popover.date}
              defaultIntent={popover.intent}
              plans={plans}
              onClose={() => setPopover(null)}
              onSaved={() => { setPopover(null); refresh(); }}
            />
          )}
          {popover.mode === "edit" && (
            <EditPlannedPopover
              planned={popover.planned}
              plans={plans}
              onClose={() => setPopover(null)}
              onSaved={() => { setPopover(null); refresh(); }}
              onViewActivity={(actId) => {
                setSelectedActivity(actId);
                setView("activity-detail");
              }}
            />
          )}
          {popover.mode === "actual" && (
            <ActualPopover
              activities={popover.activities}
              onClose={() => setPopover(null)}
              onViewActivity={(actId) => {
                setSelectedActivity(actId);
                setView("activity-detail");
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

// =============== Day Cell ===============
function DayCell(props: {
  day: number; dateStr: string; isToday: boolean;
  planned: PlannedWorkout[]; actual: ActualActivity[];
  dropDate: string | null; isDraggingPlannedId: number | null;
  onCellClick: (e: React.MouseEvent) => void;
  onPlannedClick: (e: React.MouseEvent, p: PlannedWorkout) => void;
  onActualClick: (e: React.MouseEvent) => void;
  onPlannedDragStart: (e: React.DragEvent, id: number) => void;
  onPlannedDragEnd: () => void;
  onPlannedDrop: (date: string) => void;
  onDropHover: (date: string | null) => void;
}) {
  const isDropTarget = props.dropDate === props.dateStr;
  return (
    <button
      onClick={props.onCellClick}
      onDragOver={(e) => { e.preventDefault(); props.onDropHover(props.dateStr); }}
      onDragLeave={() => props.onDropHover(null)}
      onDrop={(e) => { e.preventDefault(); props.onPlannedDrop(props.dateStr); }}
      className={clsx(
        "aspect-square min-h-[100px] p-1.5 rounded-lg text-left transition-all flex flex-col gap-0.5 overflow-hidden",
        props.isToday
          ? "bg-accent/15 ring-2 ring-accent/50 shadow-md"
          : isDropTarget
            ? "bg-amber-100 ring-2 ring-amber-500/60 scale-[1.02]"
            : "bg-bg-input/50 hover:bg-bg-input ring-1 ring-border/40",
        "cursor-pointer"
      )}
    >
      <div className="flex items-center justify-between">
        <span className={clsx("text-sm font-mono font-semibold", props.isToday ? "text-accent" : "text-text-secondary")}>
          {props.day}
        </span>
        <div className="flex items-center gap-1">
          {props.actual.length > 0 && (
            <span
              onClick={props.onActualClick}
              className="text-[9px] bg-emerald-500 text-white rounded-full px-1.5 font-bold shadow-sm"
              title={`${props.actual.length} 个实际活动`}
            >
              ✓{props.actual.length}
            </span>
          )}
          {props.planned.length > 0 && (
            <span className="text-[9px] bg-bg-elevated text-text-muted rounded-full px-1.5 font-bold">
              {props.planned.length}
            </span>
          )}
        </div>
      </div>
      <div className="flex-1 flex flex-col gap-0.5 overflow-hidden">
        {props.planned.slice(0, 3).map((p) => (
          <div
            key={p.id}
            draggable
            onDragStart={(e) => { e.stopPropagation(); props.onPlannedDragStart(e, p.id); }}
            onDragEnd={props.onPlannedDragEnd}
            onClick={(e) => props.onPlannedClick(e, p)}
            className={clsx(
              "text-[10px] px-1.5 py-0.5 rounded-md font-medium truncate border-2 cursor-grab active:cursor-grabbing flex items-center gap-1",
              p.status === "done"
                ? "bg-emerald-500 text-white border-emerald-600"
                : p.status === "skipped"
                  ? "bg-bg-elevated text-text-muted border-border line-through opacity-60"
                  : clsx(INTENT_COLORS[p.intent].bg, INTENT_COLORS[p.intent].text, INTENT_COLORS[p.intent].border, "hover:scale-105 transition-transform")
            )}
            title={`${p.title} · ${INTENT_LABEL[p.intent]} · ${p.duration_target_min ?? "?"}min`}
          >
            <span className="truncate flex-1">{p.title}</span>
            {p.status === "done" && <span>✓</span>}
          </div>
        ))}
        {props.planned.length > 3 && (
          <div className="text-[9px] text-text-muted">+{props.planned.length - 3} 更多</div>
        )}
      </div>
    </button>
  );
}

// =============== Popover: 新建 ===============
function NewPlannedPopover(props: {
  defaultDate: string; defaultIntent: WorkoutIntent;
  plans: PlanPeriod[];
  onClose: () => void; onSaved: () => void;
}) {
  const [date, setDate] = useState(props.defaultDate);
  const [title, setTitle] = useState(QUICK_PLANS.find((q) => q.key === props.defaultIntent)?.defaultTitle || "");
  const [intent, setIntent] = useState<WorkoutIntent>(props.defaultIntent);
  const [duration, setDuration] = useState<number>(INTENT_DEFAULT[props.defaultIntent].duration);
  const [tss, setTss] = useState<number>(INTENT_DEFAULT[props.defaultIntent].tss);
  const [periodId, setPeriodId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);

  // 改 intent → 改默认 title/duration/tss
  function onIntentChange(newIntent: WorkoutIntent) {
    setIntent(newIntent);
    const d = INTENT_DEFAULT[newIntent];
    setDuration(d.duration);
    setTss(d.tss);
    if (!title || QUICK_PLANS.find((q) => q.defaultTitle === title)) {
      setTitle(QUICK_PLANS.find((q) => q.key === newIntent)?.defaultTitle || "");
    }
  }

  async function save() {
    if (!title.trim()) { alert("请填写标题"); return; }
    setBusy(true);
    try {
      await api.createPlanned({
        scheduled_date: date, title: title.trim(), intent,
        duration_target_min: duration, tss_target: tss,
        period_id: periodId === "" ? undefined : Number(periodId),
      });
      props.onSaved();
    } catch (e: any) {
      alert("保存失败: " + e.message);
    } finally { setBusy(false); }
  }

  return (
    <div>
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-gradient-to-r from-accent/5 to-accent/10">
        <h2 className="text-sm font-bold flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-accent" />
          新建计划课
        </h2>
        <button onClick={props.onClose} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="p-3 space-y-2.5">
        {/* 意图选择 (大色块) */}
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">训练意图</label>
          <div className="grid grid-cols-3 gap-1.5">
            {QUICK_PLANS.map((q) => {
              const Icon = q.icon;
              const c = INTENT_COLORS[q.key];
              const isActive = intent === q.key;
              return (
                <button
                  key={q.key}
                  onClick={() => onIntentChange(q.key)}
                  className={clsx("px-1.5 py-1.5 rounded text-[11px] font-semibold flex flex-col items-center gap-0.5 transition-all",
                    isActive
                      ? `${c.bg} ${c.text} ring-2 ring-current scale-105 shadow-md`
                      : "bg-bg-elevated text-text-muted hover:bg-bg-input border border-border"
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {q.label}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">标题</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="如 Z3 节奏训练"
            autoFocus
            className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">日期</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">时长(min)</label>
            <input type="number" value={duration} onChange={(e) => setDuration(parseInt(e.target.value) || 0)} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">TSS</label>
            <input type="number" value={tss} onChange={(e) => setTss(parseInt(e.target.value) || 0)} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
        </div>
        {props.plans.length > 0 && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">所属周期</label>
            <select value={periodId} onChange={(e) => setPeriodId(e.target.value === "" ? "" : Number(e.target.value))} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent">
              <option value="">(不归属)</option>
              {props.plans.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.start_date}~{p.end_date})</option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2 px-3 py-2 border-t border-border bg-bg-elevated/50">
        <button onClick={props.onClose} className="btn-ghost text-xs">取消</button>
        <button onClick={save} disabled={busy || !title.trim()} className="btn-primary text-xs">
          {busy ? "..." : <><Plus className="w-3 h-3" />创建</>}
        </button>
      </div>
    </div>
  );
}

// =============== Popover: 编辑 ===============
function EditPlannedPopover(props: {
  planned: PlannedWorkout; plans: PlanPeriod[];
  onClose: () => void; onSaved: () => void;
  onViewActivity: (id: number) => void;
}) {
  const [date, setDate] = useState(props.planned.scheduled_date);
  const [title, setTitle] = useState(props.planned.title);
  const [intent, setIntent] = useState<WorkoutIntent>(props.planned.intent);
  const [duration, setDuration] = useState<number | "">(props.planned.duration_target_min || "");
  const [tss, setTss] = useState<number | "">(props.planned.tss_target || "");
  const [status, setStatus] = useState<PlannedStatus>(props.planned.status || "planned");
  const [periodId, setPeriodId] = useState<number | "">(props.planned.period_id || "");
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!title.trim()) { alert("请填写标题"); return; }
    setBusy(true);
    try {
      await api.updatePlanned(props.planned.id, {
        scheduled_date: date, title: title.trim(), intent,
        duration_target_min: duration === "" ? null : Number(duration),
        tss_target: tss === "" ? null : Number(tss),
        period_id: periodId === "" ? null : Number(periodId),
        status,
      });
      props.onSaved();
    } catch (e: any) {
      alert("保存失败: " + e.message);
    } finally { setBusy(false); }
  }

  async function del() {
    if (!confirm(`删除计划课「${props.planned.title}」?`)) return;
    setBusy(true);
    try { await api.deletePlanned(props.planned.id); props.onSaved(); }
    finally { setBusy(false); }
  }

  async function unlink() {
    setBusy(true);
    try { await api.unlinkPlanned(props.planned.id); props.onSaved(); }
    finally { setBusy(false); }
  }

  async function markDone() {
    setBusy(true);
    try { await api.updatePlanned(props.planned.id, { status: "done" }); props.onSaved(); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-gradient-to-r from-accent/5 to-accent/10">
        <h2 className="text-sm font-bold flex items-center gap-1.5">
          <Sparkles className="w-4 h-4 text-accent" />
          {props.planned.title}
        </h2>
        <button onClick={props.onClose} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="p-3 space-y-2.5">
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">标题</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">意图</label>
          <div className="grid grid-cols-3 gap-1.5">
            {QUICK_PLANS.map((q) => {
              const c = INTENT_COLORS[q.key];
              const isActive = intent === q.key;
              return (
                <button
                  key={q.key}
                  onClick={() => setIntent(q.key)}
                  className={clsx("px-1.5 py-1 rounded text-[10px] font-semibold transition-all",
                    isActive ? `${c.bg} ${c.text} ring-2 ring-current scale-105` : "bg-bg-elevated text-text-muted hover:bg-bg-input border border-border"
                  )}
                >
                  {q.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">日期</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full px-1.5 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">时长(min)</label>
            <input type="number" value={duration} onChange={(e) => setDuration(e.target.value === "" ? "" : parseInt(e.target.value))} className="w-full px-1.5 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">TSS</label>
            <input type="number" value={tss} onChange={(e) => setTss(e.target.value === "" ? "" : parseInt(e.target.value))} className="w-full px-1.5 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent" />
          </div>
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">状态</label>
          <div className="grid grid-cols-4 gap-1">
            {([
              { k: "planned", l: "已计划", c: "bg-bg-elevated text-text-muted" },
              { k: "done", l: "完成", c: "bg-emerald-500 text-white" },
              { k: "skipped", l: "跳过", c: "bg-bg-input text-text-muted" },
              { k: "moved", l: "改期", c: "bg-amber-500 text-white" },
            ] as const).map((s) => (
              <button
                key={s.k}
                onClick={() => setStatus(s.k as PlannedStatus)}
                className={clsx("px-2 py-1 rounded text-[10px] font-medium transition-all", status === s.k ? `${s.c} ring-2 ring-current` : "bg-bg-elevated text-text-muted hover:bg-bg-input")}
              >
                {s.l}
              </button>
            ))}
          </div>
        </div>
        {props.plans.length > 0 && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-text-muted mb-1 font-semibold">所属周期</label>
            <select value={periodId} onChange={(e) => setPeriodId(e.target.value === "" ? "" : Number(e.target.value))} className="w-full px-2 py-1.5 bg-white border border-border rounded-md text-xs focus:outline-none focus:border-accent">
              <option value="">(不归属)</option>
              {props.plans.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.start_date}~{p.end_date})</option>
              ))}
            </select>
          </div>
        )}
        {props.planned.actual_activity_id && (
          <div className="rounded-md bg-emerald-50 ring-1 ring-emerald-300 p-2.5 text-xs">
            <div className="text-emerald-700 font-semibold mb-1">已关联真实活动 #{props.planned.actual_activity_id}</div>
            <div className="flex gap-1.5">
              <button onClick={() => props.onViewActivity(props.planned.actual_activity_id!)} className="flex-1 px-2 py-1 rounded bg-emerald-500 text-white text-[10px] font-medium">查看活动</button>
              <button onClick={unlink} className="px-2 py-1 rounded bg-bg-elevated text-text-secondary text-[10px]">解除</button>
            </div>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-border bg-bg-elevated/50">
        <div className="flex gap-1.5">
          {props.planned.status !== "done" && (
            <button onClick={markDone} className="text-[10px] text-emerald-600 hover:text-emerald-700 font-medium">✓ 标完成</button>
          )}
          <button onClick={del} className="text-[10px] text-red-500 hover:text-red-600 font-medium">删除</button>
        </div>
        <div className="flex gap-1.5">
          <button onClick={props.onClose} className="btn-ghost text-xs">取消</button>
          <button onClick={save} disabled={busy || !title.trim()} className="btn-primary text-xs">
            {busy ? "..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============== Popover: 实际活动 ===============
function ActualPopover(props: {
  activities: ActualActivity[];
  onClose: () => void;
  onViewActivity: (id: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-gradient-to-r from-emerald-50 to-emerald-100">
        <h2 className="text-sm font-bold flex items-center gap-1.5 text-emerald-700">
          <Activity className="w-4 h-4" />
          实际活动 ({props.activities.length})
        </h2>
        <button onClick={props.onClose} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="max-h-72 overflow-auto">
        {props.activities.map((a) => (
          <button
            key={a.id}
            onClick={() => props.onViewActivity(a.id)}
            className="w-full text-left px-3 py-2 hover:bg-emerald-50 border-b border-border/40 flex items-center gap-2"
          >
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{a.start_time?.slice(0, 16) || a.id}</div>
              <div className="text-[10px] text-text-muted flex items-center gap-2 mt-0.5">
                <span>{Math.round((a.duration_s || 0) / 60)}min</span>
                {a.distance_m != null && <span>{(a.distance_m / 1000).toFixed(1)}km</span>}
                {a.tss != null && <span className="text-amber-600 font-semibold">TSS {Math.round(a.tss)}</span>}
              </div>
            </div>
            <ArrowRight className="w-3 h-3 text-text-muted" />
          </button>
        ))}
      </div>
    </div>
  );
}

// =============== Stat Box ===============
function StatBox({ label, value, unit, hint, accent }: any) {
  const color = accent === "good" ? "text-emerald-600" : accent === "warn" ? "text-amber-600" : accent === "bad" ? "text-red-600" : "text-text-primary";
  return (
    <div className="bg-white rounded-lg border border-border/50 p-2.5 shadow-sm">
      <div className="text-[10px] text-text-muted uppercase tracking-wider mb-0.5">{label}</div>
      <div className="flex items-baseline gap-1">
        <div className={clsx("text-2xl font-bold tabular-nums", color)}>
          {typeof value === "number" ? value.toFixed(value % 1 === 0 ? 0 : 1) : value}
        </div>
        {unit && <div className="text-[10px] text-text-muted">{unit}</div>}
      </div>
      {hint && <div className="text-[10px] text-text-muted mt-0.5">{hint}</div>}
    </div>
  );
}

function todayIso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
