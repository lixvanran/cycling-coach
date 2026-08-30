// RPE 主观疲劳 (Borg CR-10) 编辑器
// 训练后 30 分钟内填最准
import { useState } from "react";
import { Save, X } from "lucide-react";
import { api } from "../lib/api";

interface Props {
  activityId: number;
  initialRpe: number | null;
  initialNote: string | null;
  onSaved?: (rpe: number | null, note: string | null) => void;
}

const RPE_LABELS: Record<number, { label: string; color: string; desc: string }> = {
  0: { label: "没练", color: "bg-slate-100 text-slate-500", desc: "完全没感觉 / 休息日" },
  1: { label: "极轻", color: "bg-emerald-50 text-emerald-700", desc: "Active recovery" },
  2: { label: "很轻", color: "bg-emerald-50 text-emerald-700", desc: "Z1 恢复骑" },
  3: { label: "轻松", color: "bg-emerald-100 text-emerald-700", desc: "Z2 endurance" },
  4: { label: "温和", color: "bg-lime-100 text-lime-700", desc: "Z2-Z3" },
  5: { label: "中等", color: "bg-yellow-100 text-yellow-700", desc: "Z3 tempo" },
  6: { label: "稍难", color: "bg-amber-100 text-amber-700", desc: "Sweet spot" },
  7: { label: "困难", color: "bg-orange-100 text-orange-700", desc: "Z4 threshold" },
  8: { label: "很困难", color: "bg-rose-100 text-rose-700", desc: "Z4 重复" },
  9: { label: "极累", color: "bg-rose-200 text-rose-800", desc: "VO2max 间歇" },
  10: { label: "极限", color: "bg-rose-300 text-rose-900", desc: "全身炸裂" },
};

export function RPEEditor({ activityId, initialRpe, initialNote, onSaved }: Props) {
  const [rpe, setRpe] = useState<number | null>(initialRpe);
  const [note, setNote] = useState<string>(initialNote || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await api.updateRpe(activityId, rpe, note || null);
      onSaved?.(result.rpe, result.rpe_note);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    setSaving(true);
    try {
      await api.updateRpe(activityId, null, null);
      setRpe(null);
      setNote("");
      onSaved?.(null, null);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const current = rpe != null ? RPE_LABELS[rpe] : null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-text-muted">
          训练学标准 (Borg CR-10, 0-10) · 训练后 30 分钟内填最准
        </div>
        {rpe != null && (
          <button
            onClick={clear}
            disabled={saving}
            className="text-xs text-text-muted hover:text-rose-500 flex items-center gap-1"
          >
            <X className="w-3 h-3" /> 清除
          </button>
        )}
      </div>

      {/* 0-10 滑块/按钮组 */}
      <div className="grid grid-cols-11 gap-1">
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => {
          const l = RPE_LABELS[n];
          const selected = rpe === n;
          return (
            <button
              key={n}
              onClick={() => setRpe(n)}
              className={`px-1 py-2 rounded text-xs font-bold transition-all ${
                selected
                  ? `${l.color} ring-2 ring-primary scale-105`
                  : "bg-slate-50 text-slate-400 hover:bg-slate-100"
              }`}
              title={l.desc}
            >
              {n}
            </button>
          );
        })}
      </div>

      {/* 当前选择描述 */}
      {current && (
        <div className={`px-3 py-2 rounded-md ${current.color}`}>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{rpe}</span>
            <span className="text-sm font-semibold">{current.label}</span>
            <span className="text-xs opacity-75">· {current.desc}</span>
          </div>
        </div>
      )}

      {/* 备注 */}
      <div>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="备注 (e.g. 腿很沉, 大腿酸, 状态好)"
          className="w-full px-3 py-1.5 text-sm border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary"
          maxLength={64}
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="btn-primary px-3 py-1.5 text-sm flex items-center gap-1.5"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? "保存中..." : rpe != null ? "更新" : "保存 RPE"}
        </button>
        {error && <span className="text-xs text-rose-500">{error}</span>}
      </div>
    </div>
  );
}

// 只读显示 (ActivityList / 详情头部)
export function RPEBadge({ rpe, rpeNote }: { rpe: number | null; rpeNote?: string | null }) {
  if (rpe == null) return null;
  const l = RPE_LABELS[rpe];
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold ${l.color}`}
      title={l.desc + (rpeNote ? " · " + rpeNote : "")}
    >
      RPE {rpe}
    </span>
  );
}
