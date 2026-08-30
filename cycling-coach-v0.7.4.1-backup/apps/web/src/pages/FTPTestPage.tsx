// FTP 测试管理页 — V0.6.1
// 4 种协议 + 估算 + 历史 + 智能推荐
import { useEffect, useState } from "react";
import {
  Target,
  Plus,
  Trash2,
  Sparkles,
  Zap,
  TrendingUp,
  Activity,
  Calendar,
  ChevronRight,
  Award,
  Timer,
  BarChart3,
  Save,
  X,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import clsx from "clsx";
import { api } from "../lib/api";
import type { FTPTest, FTPRecommend, FTPEstimate } from "../lib/types";

export function FTPTestPage() {
  const [methods, setMethods] = useState<Record<string, any>>({});
  const [history, setHistory] = useState<FTPTest[]>([]);
  const [recommend, setRecommend] = useState<FTPRecommend | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [estimate, setEstimate] = useState<FTPEstimate | null>(null);
  const [estimateActivityId, setEstimateActivityId] = useState<string>("");
  const [estimateMethod, setEstimateMethod] = useState<string>("auto");
  const [activities, setActivities] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    Promise.all([
      api.ftpMethods(),
      api.ftpHistory(730),
      api.ftpRecommend(),
      api.listActivities({ limit: 50, sort: "start_time", order: "desc" }),
    ]).then(([m, h, r, acts]) => {
      setMethods(m.methods);
      setHistory(h);
      setRecommend(r);
      setActivities(acts.activities || []);
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
  }, []);

  const onEstimate = async () => {
    const id = parseInt(estimateActivityId);
    if (!id) return;
    try {
      const e = await api.ftpEstimate(id, estimateMethod);
      setEstimate(e);
    } catch (e: any) {
      alert("估算失败: " + (e?.message || e));
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm("确定删除这次 FTP 测试记录?")) return;
    await api.ftpDelete(id);
    load();
  };

  const onSaveEstimate = async () => {
    if (!estimate) return;
    const today = new Date().toISOString().slice(0, 10);
    await api.ftpRecord({
      test_date: today,
      method: estimate.method,
      ftp_w: estimate.ftp_w,
      confidence: estimate.confidence,
      notes: estimate.notes.join("; "),
      source_activity_id: estimate.source_activity_id,
    });
    setEstimate(null);
    setShowForm(false);
    load();
  };

  const currentFtp = history[0]?.ftp_w;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary flex items-center gap-2">
            <Target className="w-6 h-6 text-accent" />
            FTP 测试
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Functional Threshold Power · 训练区校准的基准
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setShowForm(!showForm);
              setEstimate(null);
            }}
            className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" /> 手动录入
          </button>
        </div>
      </div>

      {/* 顶部 3 卡: 当前 FTP / 推荐 / 估算 */}
      <div className="grid grid-cols-3 gap-4">
        {/* 当前 FTP */}
        <div className="panel p-4 border-l-4 border-accent">
          <div className="text-xs text-text-muted">当前 FTP</div>
          {currentFtp ? (
            <>
              <div className="text-3xl font-bold font-mono mt-1">
                {currentFtp} <span className="text-base text-text-muted">W</span>
              </div>
              <div className="text-xs text-text-muted mt-1">
                {history[0].w_per_kg ? `${history[0].w_per_kg} W/kg` : "—"}
                {" · "}来自 {history[0].method_label}
              </div>
              <div className="text-xs text-text-muted mt-0.5">
                {history[0].days_since} 天前测试
              </div>
            </>
          ) : (
            <div className="text-sm text-text-muted mt-2">未测过</div>
          )}
        </div>

        {/* 推荐 */}
        {recommend && (
          <div
            className={clsx(
              "panel p-4 border-l-4",
              recommend.priority === "high" ? "border-rose-300 bg-rose-50" :
              recommend.priority === "medium" ? "border-amber-300 bg-amber-50" :
              "border-emerald-300 bg-emerald-50"
            )}
          >
            <div className="text-xs text-text-muted flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> 智能推荐
            </div>
            <div
              className={clsx(
                "text-sm font-semibold mt-1",
                recommend.priority === "high" ? "text-rose-700" :
                recommend.priority === "medium" ? "text-amber-700" :
                "text-emerald-700"
              )}
            >
              {recommend.should_test ? "✓ 建议测试" : "— 暂不需要"}
            </div>
            <div className="text-xs text-text-muted mt-1 leading-relaxed">
              {recommend.reason}
            </div>
            {recommend.avg_if_last_14d != null && recommend.avg_if_last_14d != undefined && (
              <div className="text-xs text-text-muted mt-0.5">
                近期 14 天 IF 均值: {recommend.avg_if_last_14d}
              </div>
            )}
          </div>
        )}

        {/* 估算入口 */}
        <div className="panel p-4 border-l-4 border-blue-300 bg-blue-50">
          <div className="text-xs text-text-muted flex items-center gap-1">
            <Zap className="w-3 h-3" /> 快速估算
          </div>
          <div className="text-sm font-semibold text-blue-700 mt-1">
            从已有活动估算
          </div>
          <div className="mt-2 space-y-1">
            <select
              value={estimateActivityId}
              onChange={(e) => setEstimateActivityId(e.target.value)}
              className="w-full text-xs px-2 py-1 border border-border rounded"
            >
              <option value="">选择活动...</option>
              {activities.map((a) => (
                <option key={a.id} value={a.id}>
                  #{a.id} {a.start_time?.split("T")[0]} {a.duration_s ? Math.round(a.duration_s/60) + "min" : ""} {a.avg_power ? a.avg_power + "W" : ""}
                </option>
              ))}
            </select>
            <div className="flex gap-1">
              <select
                value={estimateMethod}
                onChange={(e) => setEstimateMethod(e.target.value)}
                className="flex-1 text-xs px-2 py-1 border border-border rounded"
              >
                {Object.entries(methods).map(([k, m]: any) => (
                  <option key={k} value={k}>{m.short}</option>
                ))}
              </select>
              <button
                onClick={onEstimate}
                disabled={!estimateActivityId}
                className="px-2 py-1 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50"
              >
                估算
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 估算结果 */}
      {estimate && (
        <div className="panel p-4 border-2 border-blue-300 space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-semibold flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-500" />
              估算结果
              {estimate.activity_summary && (
                <span className="text-xs text-text-muted font-normal">
                  · 活动 #{estimate.activity_summary.id} ({estimate.activity_summary.duration_min}min)
                </span>
              )}
            </div>
            <button onClick={() => setEstimate(null)} className="p-1 rounded hover:bg-slate-100">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-xs text-text-muted">方法</div>
              <div className="text-sm font-medium">{estimate.method_label}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">FTP 估算</div>
              <div className="text-2xl font-bold font-mono">
                {estimate.ftp_w} <span className="text-sm text-text-muted">W</span>
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">置信度</div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={clsx(
                      "h-full",
                      estimate.confidence > 0.7 ? "bg-emerald-500" :
                      estimate.confidence > 0.4 ? "bg-amber-500" :
                      "bg-rose-500"
                    )}
                    style={{ width: `${estimate.confidence * 100}%` }}
                  />
                </div>
                <div className="text-sm font-mono">{Math.round(estimate.confidence * 100)}%</div>
              </div>
            </div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">算法解读</div>
            <div className="space-y-0.5">
              {estimate.notes.map((n, i) => (
                <div key={i} className="text-xs flex gap-1.5">
                  <span className={n.startsWith("⚠") ? "text-rose-500" : "text-text-muted"}>
                    {n.startsWith("⚠") ? "⚠" : "·"}
                  </span>
                  <span>{n.replace(/^[⚠·]\s*/, "")}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex gap-2 pt-2 border-t border-border">
            <button onClick={onSaveEstimate} className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5">
              <Save className="w-3.5 h-3.5" /> 录入此次测试
            </button>
            <button onClick={() => setEstimate(null)} className="px-3 py-1.5 text-sm rounded hover:bg-slate-100">
              取消
            </button>
          </div>
        </div>
      )}

      {/* 4 种方法说明 */}
      <div>
        <h2 className="text-sm uppercase tracking-wider text-text-secondary mb-3">
          4 种测试协议 + 学术依据
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(methods).filter(([k]) => k !== "auto").map(([k, m]: any) => (
            <div key={k} className="panel p-3">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{m.icon}</span>
                <div>
                  <div className="text-sm font-semibold">{m.label}</div>
                  <div className="text-xs text-text-muted">{m.duration_min ? `${m.duration_min}分钟` : "无需专门测试"}</div>
                </div>
              </div>
              <div className="text-xs text-text-muted mt-2 leading-relaxed">
                <div className="font-mono text-[10px] text-text-primary bg-slate-50 px-1.5 py-0.5 rounded mb-1">
                  {m.formula}
                </div>
                <div className="text-[10px]">{m.protocol}</div>
              </div>
              <div className="text-[10px] text-text-muted mt-1 italic">
                学术: {m.academic}
              </div>
              <div className="text-[10px] text-text-muted mt-0.5">
                适合: {m.best_for}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 手动录入表单 */}
      {showForm && (
        <FTPForm
          methods={methods}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            load();
          }}
        />
      )}

      {/* 历史 + 趋势 */}
      {history.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm uppercase tracking-wider text-text-secondary">
            历史趋势 ({history.length} 次)
          </h2>
          <FTPHistoryChart history={[...history].reverse()} />
          <div className="space-y-1.5">
            {history.map((t) => (
              <div key={t.id} className="panel p-3 flex items-center gap-3">
                <div className="text-2xl">
                  {methods[t.method]?.icon || "📏"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold">{t.ftp_w} W</div>
                    {t.w_per_kg && (
                      <div className="text-xs text-text-muted font-mono">
                        ({t.w_per_kg} W/kg)
                      </div>
                    )}
                    {t.ftp_change_w != null && t.ftp_change_w !== 0 && (
                      <span
                        className={clsx(
                          "text-xs font-mono",
                          t.ftp_change_w > 0 ? "text-emerald-500" : "text-rose-500"
                        )}
                      >
                        {t.ftp_change_w > 0 ? "↑" : "↓"}{Math.abs(t.ftp_change_w)}W
                        ({t.ftp_change_pct}%)
                      </span>
                    )}
                    {t.ftp_change_w === 0 && (
                      <span className="text-xs text-text-muted">→ 持平</span>
                    )}
                  </div>
                  <div className="text-xs text-text-muted mt-0.5 flex gap-3">
                    <span>📅 {t.test_date} ({t.days_since}天前)</span>
                    <span>📋 {t.method_label}</span>
                    {t.hr_bpm && <span>❤️ {t.hr_bpm} bpm</span>}
                    {t.cp_w && t.w_prime_kj && (
                      <span>📊 CP {t.cp_w}W, W' {t.w_prime_kj}kJ</span>
                    )}
                    {t.confidence < 1 && (
                      <span className={t.confidence > 0.7 ? "text-emerald-500" : t.confidence > 0.4 ? "text-amber-500" : "text-rose-500"}>
                        置信度 {Math.round(t.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  {t.notes && (
                    <div className="text-xs text-text-muted mt-1 italic">💡 {t.notes}</div>
                  )}
                </div>
                <button
                  onClick={() => onDelete(t.id)}
                  className="p-1.5 rounded hover:bg-rose-50"
                  title="删除"
                >
                  <Trash2 className="w-3.5 h-3.5 text-text-muted hover:text-rose-500" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// FTP 历史趋势图
function FTPHistoryChart({ history }: { history: FTPTest[] }) {
  if (history.length < 2) {
    return (
      <div className="panel p-4 text-center text-text-muted text-sm">
        至少 2 次测试才能画趋势图
      </div>
    );
  }
  const data = history.map((t) => ({
    date: t.test_date,
    ftp: t.ftp_w,
    wkg: t.w_per_kg,
  }));
  return (
    <div className="panel p-4">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} />
          <YAxis stroke="#86909d" style={{ fontSize: 10, fontFamily: "monospace" }} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{ backgroundColor: "rgba(255,255,255,0.95)", border: "1px solid rgba(15,23,42,0.12)", borderRadius: 8, fontSize: 12 }}
          />
          <Line type="monotone" dataKey="ftp" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 5 }} isAnimationActive={false} name="FTP (W)" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// 手动录入表单
function FTPForm({ methods, onClose, onSaved }: any) {
  const [method, setMethod] = useState("coggan_20min");
  const today = new Date().toISOString().slice(0, 10);
  const [testDate, setTestDate] = useState(today);
  const [ftpW, setFtpW] = useState("");
  const [hrBpm, setHrBpm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const ftp = parseInt(ftpW);
      if (!ftp || ftp < 50 || ftp > 600) {
        setError("FTP 必须在 50-600 W 之间");
        return;
      }
      await api.ftpRecord({
        test_date: testDate,
        method,
        ftp_w: ftp,
        confidence: 0.9,  // 手动录入假定高置信度
        hr_bpm: hrBpm ? parseInt(hrBpm) : null,
        weight_kg: weightKg ? parseFloat(weightKg) : null,
        notes: notes || null,
      });
      onSaved();
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="text-lg font-semibold flex items-center gap-2">
            <Plus className="w-4 h-4" /> 录入 FTP 测试
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-text-muted">协议</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              {Object.entries(methods).filter(([k]) => k !== "auto").map(([k, m]: any) => (
                <button
                  key={k}
                  onClick={() => setMethod(k)}
                  className={clsx(
                    "p-2 rounded border-2 text-left transition-all",
                    method === k ? "border-primary bg-primary/5" : "border-border hover:border-slate-300"
                  )}
                >
                  <div className="text-base">{m.icon}</div>
                  <div className="text-xs font-medium">{m.short}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-text-muted">测试日期</label>
              <input
                type="date"
                value={testDate}
                onChange={(e) => setTestDate(e.target.value)}
                className="w-full mt-1 px-2 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted">FTP (W) *</label>
              <input
                type="number"
                value={ftpW}
                onChange={(e) => setFtpW(e.target.value)}
                placeholder="e.g. 250"
                className="w-full mt-1 px-2 py-1.5 text-sm border border-border rounded"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-text-muted">测试心率 (bpm)</label>
              <input
                type="number"
                value={hrBpm}
                onChange={(e) => setHrBpm(e.target.value)}
                placeholder="e.g. 170"
                className="w-full mt-1 px-2 py-1.5 text-sm border border-border rounded"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted">体重 (kg)</label>
              <input
                type="number"
                step="0.1"
                value={weightKg}
                onChange={(e) => setWeightKg(e.target.value)}
                placeholder="e.g. 72"
                className="w-full mt-1 px-2 py-1.5 text-sm border border-border rounded"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-text-muted">备注</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. 状态好, 全力测试"
              rows={2}
              className="w-full mt-1 px-2 py-1.5 text-sm border border-border rounded resize-none"
            />
          </div>
          {error && <div className="text-xs text-rose-500">{error}</div>}
        </div>
        <div className="p-4 border-t border-border flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded hover:bg-slate-100">
            取消
          </button>
          <button
            onClick={save}
            disabled={saving || !ftpW}
            className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? "保存中..." : "录入"}
          </button>
        </div>
      </div>
    </div>
  );
}
