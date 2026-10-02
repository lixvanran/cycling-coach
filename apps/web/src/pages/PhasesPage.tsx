// 训练周期 (Periodization) 管理页 — V0.6.1
// Joe Friel 框架: Base / Build / Peak / Taper / Recovery / Race
import { useEffect, useState } from "react";
import {
  Plus,
  Trash2,
  Edit3,
  Calendar,
  Target,
  Trophy,
  Sparkles,
  Save,
  X,
  ChevronRight,
  Award,
  TrendingUp,
  Activity,
  BarChart3,
  CalendarPlus,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from "recharts";
import clsx from "clsx";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/common";
import { PhaseSignalsCard } from "../components/PhaseSignalsCard";
import { TrainingRadarChart } from "../components/TrainingRadarChart";
import { RaceTypePicker } from "../components/RaceTypePicker";
import type { TrainingPhase } from "../lib/types";

const PHASE_COLORS: Record<string, { bg: string; border: string; text: string; bar: string }> = {
  // V0.8.3 B3: TP 老钱风 — 砍 ring, 用 1px 边 (边框表达选中)
  base: { bg: "bg-status-info", border: "border-l-primary", text: "text-accent-primary", bar: "bg-status-info" },
  build: { bg: "bg-status-warning", border: "border-border", text: "text-accent-warning", bar: "bg-status-warning0" },
  peak: { bg: "bg-status-danger", border: "border-accent-danger", text: "text-accent-danger", bar: "bg-status-danger0" },
  taper: { bg: "bg-status-success", border: "border-border", text: "text-accent-success", bar: "bg-status-success" },
  recovery: { bg: "bg-bg-subtle", border: "border-slate-300", text: "text-text-secondary", bar: "bg-slate-400" },
  race: { bg: "bg-status-info", border: "border-accent-primary", text: "text-accent-primary", bar: "bg-status-info" },
  rest: { bg: "bg-bg-subtle", border: "border-slate-300", text: "text-text-secondary", bar: "bg-slate-300" },
};

export function PhasesPage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [phases, setPhases] = useState<TrainingPhase[]>([]);
  const [meta, setMeta] = useState<Record<string, { label: string; color: string; description: string; icon: string }>>({});
  const [current, setCurrent] = useState<TrainingPhase | null>(null);
  const [nextRace, setNextRace] = useState<any>(null);
  const [suggest, setSuggest] = useState<any>(null);
  const [polarized, setPolarized] = useState<any>(null);
  const [racePlan, setRacePlan] = useState<any>(null);
  const [showRacePlan, setShowRacePlan] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [applyPhase, setApplyPhase] = useState<TrainingPhase | null>(null);

  const load = () => {
    Promise.all([
      api.phasesList(),
      api.phasesMeta(),
      api.phasesCurrent(),
      api.phasesNextRace(),
      api.phasesSuggest(),
      api.phasesPolarized(30),
    ]).then(([list, m, c, nr, sg, pz]) => {
      setPhases(list);
      setMeta(m.phases);
      setCurrent(c);
      setNextRace(nr);
      setSuggest(sg);
      setPolarized(pz);
    });
  };

  const onGenerateRacePlan = async (raceDate: string, raceName: string) => {
    try {
      const plan = await api.phasesRacePlan(raceDate, raceName);
      setRacePlan(plan);
      setShowRacePlan(true);
    } catch (e: any) {
      toast.error("生成失败: " + (e?.message || e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onDelete = async (id: number) => {
    const ok = await confirm({
      title: "删除训练阶段",
      message: "删除后无法恢复, 关联的训练计划也会受影响。",
      variant: "danger",
      confirmText: "删除",
    });
    if (!ok) return;
    try {
      await api.phasesDelete(id);
      toast.success("已删除");
      load();
    } catch (e: any) {
      toast.error("删除失败: " + (e?.message || e));
    }
  };

  const openApply = (p: TrainingPhase) => {
    setApplyPhase(p);
  };

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <PhaseSignalsCard />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary flex items-center gap-2">
            <Calendar className="w-6 h-6 text-accent" />
            训练周期 (Periodization)
          </h1>
          <p className="text-sm text-text-muted mt-1">
            规划 Base / Build / Peak / Taper / Recovery 阶段, 让训练有的放矢
          </p>
        </div>
        <button
          onClick={() => {
            setEditId(null);
            setShowForm(true);
          }}
          className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" /> 新建阶段
        </button>
      </div>

      {/* 当前阶段卡 + 智能推荐 + 下场比赛 */}
      <div className="grid grid-cols-3 gap-4">
        <CurrentCard current={current} meta={meta} />
        <SuggestionCard suggest={suggest} meta={meta} onCreate={(t: string) => {
          setEditId(null);
          setShowForm(true);
          // 预填类型
          setTimeout(() => {
            const sel = document.querySelector<HTMLSelectElement>('select[name="phase_type"]');
            if (sel) {
              sel.value = t;
              sel.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }, 0);
        }} />
        <NextRaceCard nextRace={nextRace} />
      </div>

      {/* 5 维训练状态雷达图 (Joe Friel Form Chart) */}
      <TrainingRadarChart />

      {/* Seiler 80/20 极化训练分布 */}
      {polarized && polarized.total_hours > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-accent" />
              Seiler 80/20 极化训练分布 (近 {polarized.days_analyzed} 天)
            </div>
            <div className="text-xs text-text-muted">
              目标: 低强度 80% · 高强度 20% · 避免灰色地带
            </div>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-3 mb-3">
              <PolarStat label="低强度 (Z1+Z2)" value={polarized.pct.easy} target={80} color="emerald" />
              <PolarStat label="中强度 (Z3+Z4)" value={polarized.pct.threshold} target={10} color="amber" inverse={true} />
              <PolarStat label="高强度 (Z5+)" value={polarized.pct.hard} target={20} color="rose" />
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={[
                { zone: "Z1", sec: polarized.zones.Z1, color: "#86efac" },
                { zone: "Z2", sec: polarized.zones.Z2, color: "#10b981" },
                { zone: "Z3", sec: polarized.zones.Z3, color: "#fde68a" },
                { zone: "Z4", sec: polarized.zones.Z4, color: "#fbbf24" },
                { zone: "Z5", sec: polarized.zones.Z5, color: "#fca5a5" },
                { zone: "Z6", sec: polarized.zones.Z6, color: "#f87171" },
                { zone: "Z7", sec: polarized.zones.Z7, color: "#dc2626" },
              ]}>
                <XAxis dataKey="zone" stroke="#86909d" style={{ fontSize: 11, fontFamily: "monospace" }} />
                <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} tickFormatter={(v) => `${Math.round(v / 60)}m`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [`${Math.round(v / 60)} min`, "时长"]}
                />
                <Bar dataKey="sec" isAnimationActive={false}>
                  {[0, 1, 2, 3, 4, 5, 6].map((i) => (
                    <Cell key={i} fill={["#86efac", "#10b981", "#fde68a", "#fbbf24", "#fca5a5", "#f87171", "#dc2626"][i]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className={clsx(
              "text-sm mt-2 px-3 py-2 rounded-md",
              polarized.polarized_score > 0.7 ? "bg-status-success text-accent-success" :
              polarized.polarized_score > 0.4 ? "bg-status-warning text-accent-warning" :
              "bg-status-danger text-accent-danger"
            )}>
              {polarized.interpretation} (极化分数 {polarized.polarized_score})
            </div>
            <div className="text-[10px] text-text-muted mt-2 italic">
              学术: Stephen Seiler 2010, "What is Best Practice for Training Intensity Distribution in Endurance Athletes"
            </div>
          </div>
        </section>
      )}

      {/* 比赛日倒推计划 */}
      <section className="panel">
        <div className="panel-header">
          <div className="text-sm font-medium text-text-primary flex items-center gap-2">
            <Trophy className="w-4 h-4 text-accent" />
            比赛日倒推计划
          </div>
          <button
            onClick={() => setShowRacePlan(true)}
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            <Sparkles className="w-3 h-3" /> 生成完整周期
          </button>
        </div>
        <div className="p-4 text-xs text-text-muted">
          输入比赛日, 自动生成 Base → Build I → Build II → Peak → Taper → Race 完整计划
        </div>
      </section>

      {/* 阶段列表 */}
      <div>
        <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-3">
          所有阶段 ({phases.length})
        </h2>
        {phases.length === 0 ? (
          <div className="panel p-6 text-center text-text-muted">
            还没有阶段, 点击右上角"新建阶段"开始规划
          </div>
        ) : (
          <div className="space-y-2">
            {phases.map((p) => {
              const c = PHASE_COLORS[p.phase_type] || PHASE_COLORS.base;
              const m = meta[p.phase_type];
              const targetRatio = p.target_tss_week && p.actual_avg_tss_week
                ? p.actual_avg_tss_week / p.target_tss_week
                : null;
              return (
                <div
                  key={p.id}
                  className={clsx("panel p-3 flex items-center gap-3 border-l-4", c.border, c.bg)}
                >
                  <div className="text-2xl">{m?.icon || "📅"}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <div className={clsx("text-sm font-semibold", c.text)}>
                        {p.name}
                      </div>
                      <span className={clsx("px-1.5 py-0.5 rounded text-[10px] font-medium", c.bg, c.text)}>
                        {m?.label || p.phase_type}
                      </span>
                      {p.is_race && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-status-info text-accent-primary">
                          🏁 比赛
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-text-muted mt-0.5 flex gap-3">
                      <span>📅 {p.start_date} → {p.end_date} ({p.duration_days}天)</span>
                      {p.target_tss_week != null && (
                        <span>🎯 周目标 TSS {p.target_tss_week}</span>
                      )}
                      {p.actual_count > 0 && (
                        <span>
                          ✓ 实际: {p.actual_count} 次训练
                          {p.actual_avg_tss_week != null && (
                            <span className={targetRatio && targetRatio > 1.2 ? " text-accent-danger" : targetRatio && targetRatio < 0.6 ? " text-accent-warning" : " text-accent-success"}>
                              {" "}(周均 {p.actual_avg_tss_week})
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                    {p.notes && (
                      <div className="text-xs text-text-muted mt-1">💡 {p.notes}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => openApply(p)}
                      className="px-2 py-1 rounded text-xs font-medium bg-status-success text-accent-success hover:bg-status-success border border-border flex items-center gap-1"
                      title="把阶段所有 workout 一键生成到日历"
                    >
                      <CalendarPlus className="w-3 h-3" />
                      应用到日历
                    </button>
                    <button
                      onClick={() => {
                        setEditId(p.id);
                        setShowForm(true);
                      }}
                      className="p-1.5 rounded hover:bg-white/50"
                      title="编辑"
                    >
                      <Edit3 className="w-3.5 h-3.5 text-text-muted" />
                    </button>
                    <button
                      onClick={() => onDelete(p.id)}
                      className="p-1.5 rounded hover:bg-status-danger"
                      title="删除"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-text-muted hover:text-accent-danger" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 表单弹窗 */}
      {showRacePlan && (
        <RacePlanForm
          onClose={() => setShowRacePlan(false)}
          onGenerate={onGenerateRacePlan}
          plan={racePlan}
        />
      )}

      {showForm && (
        <PhaseForm
          meta={meta}
          editPhase={editId ? phases.find((p) => p.id === editId) || null : null}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            load();
          }}
        />
      )}

      {applyPhase && (
        <ApplyToCalendarModal
          phase={applyPhase}
          onClose={() => setApplyPhase(null)}
          onApplied={() => {
            setApplyPhase(null);
            load();
          }}
        />
      )}
    </div>
  );
}

// 极化统计卡
function PolarStat({ label, value, target, color, inverse }: any) {
  const good = inverse ? value <= target : Math.abs(value - target) < 10;
  return (
    <div className={clsx("px-3 py-2 rounded-md border",
      good ? "bg-status-success border-border" : "bg-status-warning border-border"
    )}>
      <div className="text-xs text-text-muted">{label}</div>
      <div className="text-2xl font-bold font-mono">
        {value.toFixed(1)}<span className="text-sm text-text-muted">%</span>
      </div>
      <div className="text-[10px] text-text-muted">
        {inverse ? "≤" : "≈"} {target}% {good ? "✓" : "⚠"}
      </div>
    </div>
  );
}

// 比赛日倒推表单 + 计划展示
function RacePlanForm({ onClose, onGenerate, plan }: any) {
  const toast = useToast();
  const [raceDate, setRaceDate] = useState("");
  const [raceName, setRaceName] = useState("");

  const submit = () => {
    if (!raceDate || !raceName) {
      toast.warn("请填写比赛日和名称");
      return;
    }
    onGenerate(raceDate, raceName);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded shadow-sm w-full max-w-3xl my-8 max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-border sticky top-0 bg-white flex items-center justify-between z-10">
          <div className="text-lg font-semibold flex items-center gap-2">
            <Trophy className="w-5 h-5 text-accent-warning" />
            比赛日倒推周期计划 (Joe Friel 框架)
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        {!plan ? (
          <div className="p-6 space-y-3">
            <div className="text-sm text-text-muted">
              训练学框架: Joe Friel "The Cyclist's Training Bible"
              <br />· Base 8-12 周 → Build 6-8 周 → Peak 2-3 周 → Taper 1-2 周 → Race
            </div>
            <div>
              <label className="text-xs text-text-muted">比赛日</label>
              <input
                type="date"
                value={raceDate}
                onChange={(e) => setRaceDate(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted">比赛名称</label>
              <input
                type="text"
                value={raceName}
                onChange={(e) => setRaceName(e.target.value)}
                placeholder="e.g. 环千岛湖, 绕圈赛"
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <button onClick={submit} className="btn-primary px-4 py-2 text-sm w-full">
              <Sparkles className="w-4 h-4 inline mr-1.5" />
              生成完整周期计划
            </button>
          </div>
        ) : (
          <div className="p-4 space-y-3">
            <div className="text-sm">
              🏁 <span className="font-semibold">{plan.race_name}</span> · {plan.race_date} · 距今 {plan.weeks_total} 周
              <span className="text-xs text-text-muted ml-2">当前: CTL {plan.current_ctl}, FTP {plan.current_ftp}W</span>
            </div>
            <div className="space-y-2">
              {plan.plan.map((p: any, i: number) => {
                const c = PHASE_COLORS[p.phase] || PHASE_COLORS.base;
                return (
                  <div key={i} className={clsx("border-l-4 rounded-r-md p-3", c.bg, c.border)}>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className={clsx("text-sm font-semibold", c.text)}>{p.label}</span>
                        <span className="text-xs text-text-muted ml-2">({p.weeks}周)</span>
                      </div>
                      {p.weekly_tss_target > 0 && (
                        <div className="text-xs font-mono text-text-muted">
                          TSS/wk {p.weekly_tss_target} ({p.weekly_tss_range?.join("-")})
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-text-muted mt-1">{p.intensity_focus}</div>
                    <div className="mt-2 space-y-0.5">
                      {p.key_workouts.map((kw: string, j: number) => (
                        <div key={j} className="text-xs">· {kw}</div>
                      ))}
                    </div>
                    {p.notes && (
                      <div className="text-xs text-text-muted mt-2 italic">💡 {p.notes}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ----- 子组件 -----

function CurrentCard({ current, meta }: any) {
  if (!current) {
    return (
      <div className="panel p-3">
        <div className="text-xs text-text-muted">当前阶段</div>
        <div className="text-sm text-text-muted mt-2">今天不在任何阶段</div>
      </div>
    );
  }
  const c = PHASE_COLORS[current.phase_type] || PHASE_COLORS.base;
  const m = meta[current.phase_type];
  return (
    <div className={clsx("panel p-3 border-l-4", c.border, c.bg)}>
      <div className="text-xs text-text-muted">当前阶段</div>
      <div className={clsx("text-lg font-semibold mt-1", c.text)}>
        {m?.icon} {m?.label}
      </div>
      <div className="text-xs text-text-muted mt-1">{current.name}</div>
      <div className="text-xs text-text-muted mt-0.5">
        {current.start_date} → {current.end_date}
      </div>
    </div>
  );
}

function SuggestionCard({ suggest, meta, onCreate }: any) {
  if (!suggest) return null;
  const c = PHASE_COLORS[suggest.suggestion] || PHASE_COLORS.base;
  const m = meta[suggest.suggestion];
  return (
    <div className="panel p-3">
      <div className="text-xs text-text-muted flex items-center gap-1">
        <Sparkles className="w-3 h-3" /> 智能推荐 (PMC 推导)
      </div>
      <div className={clsx("text-lg font-semibold mt-1", c.text)}>
        {m?.icon} {m?.label || suggest.suggestion}
      </div>
      <div className="text-xs text-text-muted mt-1 leading-relaxed space-y-0.5">
        {suggest.reasons?.map((r: string, i: number) => (
          <div key={i}>· {r}</div>
        ))}
      </div>
      <div className="text-[10px] text-text-muted mt-2 grid grid-cols-2 gap-1">
        <div>CTL {suggest.current_ctl} · ATL {suggest.current_atl}</div>
        <div>TSB {suggest.current_tsb} · ramp {suggest.ramp_rate}/wk</div>
        <div>目标 TSS/wk: {suggest.target_weekly_tss} ({suggest.target_weekly_tss_range?.join("-")})</div>
        <div>建议 {suggest.weeks_recommended} 周</div>
      </div>
      <button
        onClick={() => onCreate(suggest.suggestion)}
        className="text-xs text-primary mt-2 flex items-center gap-1 hover:underline"
      >
        一键创建 <ChevronRight className="w-3 h-3" />
      </button>
    </div>
  );
}

function NextRaceCard({ nextRace }: any) {
  if (!nextRace) {
    return (
      <div className="panel p-3">
        <div className="text-xs text-text-muted">下一场比赛</div>
        <div className="text-sm text-text-muted mt-2">未安排</div>
      </div>
    );
  }
  const days = nextRace.days_to_race;
  const color = days <= 7 ? "text-accent-danger" : days <= 21 ? "text-accent-warning" : "text-accent-success";
  return (
    <div className="panel p-3 border-l-4 border-accent-primary bg-status-info">
      <div className="text-xs text-text-muted flex items-center gap-1">
        <Trophy className="w-3 h-3" /> 下一场比赛
      </div>
      <div className="text-lg font-semibold text-accent-primary mt-1">
        🏁 {nextRace.name}
      </div>
      <div className="text-xs text-text-muted mt-1">
        {nextRace.date} · 还有
      </div>
      <div className={clsx("text-3xl font-bold font-mono mt-1", color)}>
        {days} <span className="text-sm">天</span>
      </div>
    </div>
  );
}

function PhaseForm({ meta, editPhase, onClose, onSaved }: any) {
  const [phaseType, setPhaseType] = useState(editPhase?.phase_type || "base");
  const [name, setName] = useState(editPhase?.name || "");
  const [startDate, setStartDate] = useState(editPhase?.start_date || new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(
    editPhase?.end_date ||
    new Date(Date.now() + 28 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  );
  const [targetTss, setTargetTss] = useState(editPhase?.target_tss_week?.toString() || "");
  const [targetFtp, setTargetFtp] = useState(editPhase?.target_ftp_w?.toString() || "");
  const [notes, setNotes] = useState(editPhase?.notes || "");
  const [isRace, setIsRace] = useState(editPhase?.is_race || false);
  const [raceType, setRaceType] = useState(editPhase?.race_type || "road_race");
  const [racePriority, setRacePriority] = useState(editPhase?.race_priority || "B");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const data: any = {
        phase_type: phaseType,
        name: name || `${meta[phaseType]?.label || phaseType}期`,
        start_date: startDate,
        end_date: endDate,
        target_tss_week: targetTss ? parseInt(targetTss) : null,
        target_ftp_w: targetFtp ? parseInt(targetFtp) : null,
        notes: notes || null,
        is_race: isRace,
        race_type: isRace ? raceType : null,
        race_priority: isRace ? racePriority : null,
      };
      if (editPhase) {
        await api.phasesUpdate(editPhase.id, data);
      } else {
        await api.phasesCreate(data);
      }
      onSaved();
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded shadow-sm w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="text-lg font-semibold">
            {editPhase ? "编辑训练阶段" : "新建训练阶段"}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* 阶段类型 */}
          <div>
            <label className="text-xs text-text-muted">阶段类型</label>
            <div className="grid grid-cols-4 gap-2 mt-1">
              {Object.entries(meta).map(([key, m]: any) => {
                const c = PHASE_COLORS[key] || PHASE_COLORS.base;
                const sel = phaseType === key;
                return (
                  <button
                    key={key}
                    onClick={() => setPhaseType(key)}
                    className={clsx(
                      "p-2 rounded border-2 text-center transition-all",
                      sel ? `${c.bg} ${c.border} ` : "border-border hover:border-slate-300"
                    )}
                  >
                    <div className="text-xl">{m.icon}</div>
                    <div className="text-xs font-medium mt-1">{m.label}</div>
                  </button>
                );
              })}
            </div>
            <div className="text-xs text-text-muted mt-1">
              {meta[phaseType]?.description}
            </div>
          </div>

          {/* 名称 */}
          <div>
            <label className="text-xs text-text-muted">阶段名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`e.g. 9月强化期`}
              className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {/* 时间范围 */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-text-muted">起始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
          </div>

          {/* 目标 */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-text-muted">周目标 TSS (可选)</label>
              <input
                type="number"
                value={targetTss}
                onChange={(e) => setTargetTss(e.target.value)}
                placeholder="e.g. 400"
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted">目标 FTP W (可选)</label>
              <input
                type="number"
                value={targetFtp}
                onChange={(e) => setTargetFtp(e.target.value)}
                placeholder="e.g. 260"
                className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded"
              />
            </div>
          </div>

          {/* 备注 */}
          <div>
            <label className="text-xs text-text-muted">备注</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. 重点提升 Z4 threshold"
              rows={2}
              className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded resize-none"
            />
          </div>

          {/* 比赛 */}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isRace}
              onChange={(e) => setIsRace(e.target.checked)}
              className="rounded"
            />
            <span>标记为比赛日 (出现在"下一场比赛"卡片)</span>
          </label>

          {isRace && (
            <div className="space-y-2 pl-6 border-l-2 border-border">
              <div>
                <label className="text-xs text-text-muted">比赛类型</label>
                <div className="mt-1">
                  <RaceTypePicker value={raceType} onChange={setRaceType} />
                </div>
              </div>
              <div>
                <label className="text-xs text-text-muted">比赛优先级</label>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {[
                    { v: "A", label: "A · 最重要", color: "border-accent-danger bg-status-danger text-accent-danger" },
                    { v: "B", label: "B · 重要", color: "border-border bg-status-warning text-accent-warning" },
                    { v: "C", label: "C · 训练赛", color: "border-slate-300 bg-bg-subtle text-text-secondary" },
                  ].map((p) => (
                    <button
                      key={p.v}
                      type="button"
                      onClick={() => setRacePriority(p.v)}
                      className={clsx(
                        "px-2 py-1.5 text-xs rounded border-2 transition",
                        racePriority === p.v
                          ? `${p.color} ring-1 ring-accent-primary`
                          : "border-border hover:border-slate-300"
                      )}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && <div className="text-xs text-accent-danger">{error}</div>}
        </div>

        <div className="p-4 border-t border-border flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded hover:bg-slate-100">
            取消
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? "保存中..." : editPhase ? "更新" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ----- B1-3: 应用到日历模态框 -----

function ApplyToCalendarModal({ phase, onClose, onApplied }: {
  phase: TrainingPhase;
  onClose: () => void;
  onApplied: () => void;
}) {
  const toast = useToast();
  const today = new Date();
  // 默认起始日期: 阶段开始日期 (or 今天 if later)
  const defaultStart = (() => {
    const phaseStart = new Date(phase.start_date);
    return (phaseStart > today ? phaseStart : today).toISOString().slice(0, 10);
  })();
  const [startDate, setStartDate] = useState(defaultStart);
  const [weeks, setWeeks] = useState(4);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!startDate) {
      setError("请选择起始日期");
      return;
    }
    if (weeks < 1 || weeks > 52) {
      setError("周数需在 1-52 之间");
      return;
    }
    setApplying(true);
    setError(null);
    try {
      const res = await api.applyPhaseToCalendar(phase.id, startDate, weeks);
      toast.success(`已生成 ${res.applied_count} 个 workout 到日历`);
      onApplied();
    } catch (e: any) {
      const msg = String(e?.message || e);
      setError(msg);
      toast.error("应用失败: " + msg);
    } finally {
      setApplying(false);
    }
  };

  const phaseWeeks = Math.max(
    1,
    Math.round(
      (new Date(phase.end_date).getTime() - new Date(phase.start_date).getTime()) / (7 * 86400_000)
    ) + 1
  );

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded shadow-sm w-full max-w-md">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="text-lg font-semibold flex items-center gap-2">
            <CalendarPlus className="w-5 h-5 text-accent-success" />
            应用阶段到日历
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="text-sm text-text-muted">
            <div>阶段: <span className="font-medium text-text-primary">{phase.name}</span></div>
            <div>范围: {phase.start_date} → {phase.end_date} ({phaseWeeks} 周)</div>
          </div>

          <div className="p-3 bg-status-warning border border-border rounded-md text-xs text-accent-warning leading-relaxed">
            💡 将按阶段周模板 (week_index + day_of_week) 循环生成 PlannedWorkout。
            例如 4 周阶段 → 4 周各 1 次循环。
          </div>

          <div>
            <label className="text-xs text-text-muted">起始日期</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="text-xs text-text-muted">应用周数</label>
            <input
              type="number"
              value={weeks}
              onChange={(e) => setWeeks(parseInt(e.target.value || "0"))}
              min={1}
              max={52}
              className="w-full mt-1 px-3 py-1.5 text-sm border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <div className="text-[10px] text-text-muted mt-1">
              week_index 超出阶段定义的最大周时会自动循环回 week 1
            </div>
          </div>

          {error && (
            <div className="text-xs text-accent-danger bg-status-danger border border-border rounded p-2">
              {error}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded hover:bg-slate-100"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={applying}
            className="px-3 py-1.5 text-sm rounded bg-accent-success text-white hover:bg-accent-success-hover disabled:opacity-50 flex items-center gap-1.5"
          >
            <CalendarPlus className="w-3.5 h-3.5" />
            {applying ? "应用中..." : `生成 ${weeks} 周`}
          </button>
        </div>
      </div>
    </div>
  );
}
