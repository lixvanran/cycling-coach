// 比赛类型选择器 — 7 种 (TT / 单日 / 多日 / 长距离 / 绕圈 / 爬坡 / 其他)

import { useEffect, useState } from "react";

interface RaceTypeInfo {
  code: string;
  label: string;
  tsb_target: [number, number];
  taper: { short: { days: number; reduction_pct: number }; long: { days: number; reduction_pct: number } };
  description: string;
  notes: string;
}

interface Props {
  value: string;
  onChange: (code: string) => void;
}

export function RaceTypePicker({ value, onChange }: Props) {
  const [types, setTypes] = useState<Record<string, RaceTypeInfo> | null>(null);

  useEffect(() => {
    fetch("/api/race-prep/types")
      .then((r) => r.json())
      .then((j) => setTypes(j.types))
      .catch(() => {});
  }, []);

  if (!types) return null;
  const current = types[value];

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {Object.values(types).map((t) => {
          const isActive = value === t.code;
          return (
            <button
              key={t.code}
              type="button"
              onClick={() => onChange(t.code)}
              className={`text-left p-3 rounded border transition ${
                isActive
                  ? "border-accent-primary bg-status-info ring-1 ring-accent-primary"
                  : "border-border hover:border-slate-300 bg-white"
              }`}
            >
              <div className="text-sm font-semibold text-text-primary">{t.label}</div>
              <div className="text-[10px] text-text-secondary mt-0.5">
                TSB {`${t.tsb_target[0] >= 0 ? "+" : ""}${t.tsb_target[0]}`}~{`${t.tsb_target[1] >= 0 ? "+" : ""}${t.tsb_target[1]}`} · Taper {t.taper.short.days}d
              </div>
            </button>
          );
        })}
      </div>
      {current && (
        <div className="text-xs text-text-secondary bg-bg-subtle rounded p-3 border border-border">
          <div className="font-semibold text-text-secondary mb-1">{current.label}</div>
          <div className="leading-relaxed">{current.description}</div>
          <div className="text-text-secondary mt-1 italic">{current.notes}</div>
        </div>
      )}
    </div>
  );
}
