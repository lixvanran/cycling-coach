// 训练日记 — V0.7.4.2
// 借鉴: 训练百科 - 训练日记 (KB caafd85d) + TrainingPeaks Daily Notes + WKO5 Daily Diary
import { useEffect, useState, useCallback } from "react";
import {
  ChevronLeft, ChevronRight, Save, Trash2, BookOpen, Sun, Moon,
  Smile, Frown, Calendar as CalendarIcon, Sparkles, Plus,
  Activity as ActivityIcon, Star, Cloud, Wrench, AlertCircle,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import type { Diary, DiaryTemplate } from "../lib/types";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}
function isoOffset(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
function cnDateLabel(iso: string) {
  const d = new Date(iso + "T00:00:00");
  const today = todayISO();
  const yesterday = isoOffset(-1);
  if (iso === today) return "今天";
  if (iso === yesterday) return "昨天";
  const wd = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 ${wd}`;
}

function Rating({ value, onChange, scale }: {
  value: number | null;
  onChange: (v: number) => void;
  scale?: string;
}) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          onClick={() => onChange(value === n ? 0 : n)}
          className={clsx(
            "w-9 h-9 rounded-md flex items-center justify-center text-sm font-medium transition-all",
            value && value >= n
              ? "bg-amber-400 text-white shadow-sm scale-105"
              : "bg-bg-elevated text-text-muted hover:bg-bg-elevated/80 border border-border"
          )}
          title={scale || `${n} 分`}
        >
          {n}
        </button>
      ))}
      {value ? <span className="ml-2 text-xs text-text-muted">{value}/5</span> : null}
    </div>
  );
}

export function DiaryPage() {
  const [date, setDate] = useState(todayISO());
  const [item, setItem] = useState<Diary | null>(null);
  const [exists, setExists] = useState(false);
  const [tpl, setTpl] = useState<DiaryTemplate | null>(null);
  const [activities, setActivities] = useState<any[]>([]);
  const [recent, setRecent] = useState<Diary[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showTips, setShowTips] = useState(true);

  // 字段
  const [trainingFeel, setTrainingFeel] = useState<number | null>(null);
  const [mood, setMood] = useState<number | null>(null);
  const [sleepH, setSleepH] = useState<string>("");
  const [sleepQuality, setSleepQuality] = useState<number | null>(null);
  const [content, setContent] = useState("");
  const [weather, setWeather] = useState("");
  const [equipmentNotes, setEquipmentNotes] = useState("");
  const [painNotes, setPainNotes] = useState("");
  const [activityId, setActivityId] = useState<number | null>(null);

  // 加载
  const loadDay = useCallback(async (d: string) => {
    const r = await api.diaryGet(d);
    setExists(r.exists);
    setItem(r.item);
    if (r.item) {
      setTrainingFeel(r.item.training_feel);
      setMood(r.item.mood);
      setSleepH(r.item.sleep_h != null ? String(r.item.sleep_h) : "");
      setSleepQuality(r.item.sleep_quality);
      setContent(r.item.content || "");
      setWeather(r.item.weather || "");
      setEquipmentNotes(r.item.equipment_notes || "");
      setPainNotes(r.item.pain_notes || "");
      setActivityId(r.item.activity_id);
    } else {
      setTrainingFeel(null); setMood(null); setSleepH(""); setSleepQuality(null);
      setContent(""); setWeather(""); setEquipmentNotes(""); setPainNotes("");
      setActivityId(null);
    }
    setSaved(false);
  }, []);

  useEffect(() => { loadDay(date); }, [date, loadDay]);

  useEffect(() => {
    (async () => {
      try {
        const t = await api.diaryTemplate();
        setTpl(t);
        const r = await api.diaryList(30);
        setRecent(r.items);
        const a = await api.listActivities({ limit: 50 });
        setActivities((a as any).activities || (a as any).items || []);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  // 同步保存
  useEffect(() => {
    if (!exists) return;
    const timer = setTimeout(async () => {
      try {
        await save(false);
      } catch {}
    }, 1500);
    return () => clearTimeout(timer);
  }, [trainingFeel, mood, sleepH, sleepQuality, content, weather, equipmentNotes, painNotes, activityId]);

  async function save(showFeedback = true) {
    setSaving(true);
    try {
      const payload: any = { date };
      if (trainingFeel != null) payload.training_feel = trainingFeel;
      if (mood != null) payload.mood = mood;
      if (sleepH) payload.sleep_h = parseFloat(sleepH);
      if (sleepQuality != null) payload.sleep_quality = sleepQuality;
      if (content) payload.content = content;
      if (weather) payload.weather = weather;
      if (equipmentNotes) payload.equipment_notes = equipmentNotes;
      if (painNotes) payload.pain_notes = painNotes;
      if (activityId != null) payload.activity_id = activityId;
      const r = await api.diaryUpsert(payload);
      setItem(r.item);
      setExists(true);
      // 刷新最近
      const list = await api.diaryList(30);
      setRecent(list.items);
      if (showFeedback) {
        setSaved(true);
        setTimeout(() => setSaved(false), 1500);
      }
    } catch (e: any) {
      console.error("保存失败", e);
      toast.error(`保存失败: ${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!exists) return;
    if (!confirm(`删除 ${date} 的训练日记?`)) return;
    try {
      await api.diaryDelete(date);
      setItem(null);
      setExists(false);
      setTrainingFeel(null); setMood(null); setSleepH(""); setSleepQuality(null);
      setContent(""); setWeather(""); setEquipmentNotes(""); setPainNotes("");
      setActivityId(null);
      const list = await api.diaryList(30);
      setRecent(list.items);
    } catch (e: any) {
      toast.error(`删除失败: ${e?.message || e}`);
    }
  }

  function insertPrompt(p: string) {
    setContent((c) => c ? `${c}\n- ${p}` : `- ${p}`);
  }

  return (
    <div className="h-full overflow-y-auto bg-bg-base">
      <div className="max-w-6xl mx-auto px-5 py-4">

        {/* 顶部: 日期选择 + 标题 */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center"
                 style={{ background: "linear-gradient(135deg, #f59e0b 0%, #f43f5e 100%)" }}>
              <BookOpen size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-text-primary">训练日记</h1>
              <p className="text-xs text-text-muted">
                主观记录每一天 · 训练学: 重要! 复盘/教练沟通依据
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTips(!showTips)}
              className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-bg-elevated transition-colors"
            >
              {showTips ? "隐藏提示" : "显示提示"}
            </button>
            {exists && (
              <button
                onClick={remove}
                className="px-3 py-1.5 text-xs rounded-md border border-red-300 text-red-600 hover:bg-red-50 transition-colors flex items-center gap-1"
              >
                <Trash2 size={12} /> 删除
              </button>
            )}
            <button
              onClick={() => save(true)}
              disabled={saving}
              className={clsx(
                "px-4 py-1.5 text-sm rounded-md font-medium flex items-center gap-1.5 transition-all",
                saved
                  ? "bg-green-500 text-white"
                  : "bg-accent text-white hover:opacity-90",
                saving && "opacity-50"
              )}
            >
              <Save size={14} /> {saving ? "保存中..." : saved ? "已保存" : "保存"}
            </button>
          </div>
        </div>

        {/* 日期导航 */}
        <div className="bg-bg-card border border-border rounded-lg p-3 mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDate(isoOffset(-1))}
              className="w-8 h-8 rounded-md border border-border hover:bg-bg-elevated flex items-center justify-center"
              title="前一天"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => setDate(todayISO())}
              className="px-3 py-1.5 text-sm bg-accent/10 text-accent border border-accent/30 rounded-md font-medium flex items-center gap-1"
            >
              <CalendarIcon size={12} /> 今天
            </button>
            <button
              onClick={() => setDate(isoOffset(1))}
              className="w-8 h-8 rounded-md border border-border hover:bg-bg-elevated flex items-center justify-center"
              title="后一天"
            >
              <ChevronRight size={14} />
            </button>
          </div>
          <div className="text-center">
            <div className="text-base font-semibold text-text-primary">
              {cnDateLabel(date)}
            </div>
            <div className="text-xs text-text-muted">{date}</div>
          </div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-2 py-1 text-xs border border-border rounded-md bg-bg-elevated"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* 主编辑区 */}
          <div className="lg:col-span-2 space-y-4">

            {/* 训练感受 + 心情 */}
            <div className="bg-bg-card border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-1.5">
                <Sparkles size={14} className="text-amber-500" />
                主观感受
              </h3>
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-text-muted mb-1.5">
                    训练感受 <span className="text-text-muted/70">(1=很累 → 5=很轻松)</span>
                  </div>
                  <Rating value={trainingFeel} onChange={setTrainingFeel} scale="1=很累 5=很轻松" />
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1.5">
                    心情 <span className="text-text-muted/70">(1=很差 → 5=很好)</span>
                  </div>
                  <Rating value={mood} onChange={setMood} scale="1=很差 5=很好" />
                </div>
              </div>
            </div>

            {/* 睡眠 */}
            <div className="bg-bg-card border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-1.5">
                <Moon size={14} className="text-indigo-500" />
                睡眠
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-text-muted mb-1.5">睡眠时长 (小时)</div>
                  <input
                    type="number"
                    step="0.1"
                    value={sleepH}
                    onChange={(e) => setSleepH(e.target.value)}
                    placeholder="如 7.5"
                    className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated"
                  />
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1.5">睡眠质量 (1-5)</div>
                  <Rating value={sleepQuality} onChange={setSleepQuality} scale="1=很差 5=很好" />
                </div>
              </div>
            </div>

            {/* 主观笔记 */}
            <div className="bg-bg-card border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-1.5">
                <BookOpen size={14} className="text-emerald-500" />
                主观笔记 <span className="text-xs text-text-muted font-normal">(支持 Markdown)</span>
              </h3>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={10}
                placeholder="记录今天训练的细节感受, 例如:&#10;- 热身 15min, 感觉大腿有点紧&#10;- 间歇 4x5min @ 90% FTP, 第 3 组开始心脏难受&#10;- 冲刺用了 53x11 齿比, 感觉很爽"
                className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated font-mono leading-relaxed"
              />
            </div>

            {/* 天气/装备/疼痛 (折叠) */}
            <details className="bg-bg-card border border-border rounded-lg p-4">
              <summary className="text-sm font-semibold text-text-primary cursor-pointer flex items-center gap-1.5">
                <Cloud size={14} className="text-sky-500" />
                天气 / 装备 / 疼痛 (选填)
              </summary>
              <div className="mt-3 space-y-3">
                <div>
                  <div className="text-xs text-text-muted mb-1.5 flex items-center gap-1">
                    <Cloud size={11} /> 天气
                  </div>
                  <input
                    type="text"
                    value={weather}
                    onChange={(e) => setWeather(e.target.value)}
                    placeholder="如 晴 28°C 微风"
                    className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated"
                  />
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1.5 flex items-center gap-1">
                    <Wrench size={11} /> 装备/补记
                  </div>
                  <input
                    type="text"
                    value={equipmentNotes}
                    onChange={(e) => setEquipmentNotes(e.target.value)}
                    placeholder="如 换了新锁片, 喝了 1.5L 水, 吃了 2 个胶"
                    className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated"
                  />
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1.5 flex items-center gap-1">
                    <AlertCircle size={11} /> 疼痛/不适
                  </div>
                  <input
                    type="text"
                    value={painNotes}
                    onChange={(e) => setPainNotes(e.target.value)}
                    placeholder="如 右膝轻微不适 (不影响骑车), 牙疼"
                    className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated"
                  />
                </div>
                <div>
                  <div className="text-xs text-text-muted mb-1.5 flex items-center gap-1">
                    <ActivityIcon size={11} /> 关联活动
                  </div>
                  <select
                    value={activityId ?? ""}
                    onChange={(e) => setActivityId(e.target.value ? Number(e.target.value) : null)}
                    className="w-full px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated"
                  >
                    <option value="">不关联</option>
                    {activities.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.start_time?.slice(0, 10)} · {a.title || a.file_name || `活动 ${a.id}`} · {Math.round((a.duration_s || 0) / 60)}min
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </details>
          </div>

          {/* 侧栏: 模板提示 + 最近 */}
          <div className="space-y-4">
            {showTips && tpl && (
              <div className="bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-amber-900 mb-2 flex items-center gap-1.5">
                  <Sparkles size={14} /> KB 训练日记模板
                </h3>
                <p className="text-[10px] text-amber-700 mb-3">{tpl.source}</p>
                <div className="mb-3">
                  <div className="text-xs font-semibold text-amber-800 mb-1.5">📝 可点击插入笔记</div>
                  <div className="space-y-1">
                    {tpl.prompts.slice(0, 6).map((p, i) => (
                      <button
                        key={i}
                        onClick={() => insertPrompt(p)}
                        className="w-full text-left text-xs px-2 py-1.5 bg-white/70 hover:bg-white rounded border border-amber-200 transition-colors"
                      >
                        · {p}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-amber-800 mb-1.5">🌅 影响训练的因素</div>
                  <div className="flex flex-wrap gap-1">
                    {tpl.daily_factors.slice(0, 8).map((f, i) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 bg-white/70 rounded-full border border-amber-200">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 最近 7 天 */}
            <div className="bg-bg-card border border-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-2 flex items-center gap-1.5">
                <CalendarIcon size={14} /> 最近 30 天
              </h3>
              <div className="space-y-1 max-h-96 overflow-y-auto">
                {recent.length === 0 && (
                  <div className="text-xs text-text-muted py-2">还没有日记</div>
                )}
                {recent.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setDate(d.date)}
                    className={clsx(
                      "w-full text-left px-2 py-1.5 rounded text-xs transition-colors",
                      d.date === date
                        ? "bg-accent/10 text-accent border border-accent/30"
                        : "hover:bg-bg-elevated"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{cnDateLabel(d.date)}</span>
                      <span className="text-text-muted text-[10px]">{d.date.slice(5)}</span>
                    </div>
                    {d.content && (
                      <div className="text-text-muted text-[10px] mt-0.5 line-clamp-1">
                        {d.content.slice(0, 40)}
                      </div>
                    )}
                    <div className="flex gap-1 mt-1">
                      {d.training_feel != null && (
                        <span className="text-[9px] px-1 bg-amber-100 text-amber-700 rounded">感受 {d.training_feel}/5</span>
                      )}
                      {d.mood != null && (
                        <span className="text-[9px] px-1 bg-pink-100 text-pink-700 rounded">心情 {d.mood}/5</span>
                      )}
                      {d.sleep_h != null && (
                        <span className="text-[9px] px-1 bg-indigo-100 text-indigo-700 rounded">💤 {d.sleep_h}h</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
