// Trends 趋势页可配置 — V0.7.2 新加
// 用户能选择显示哪些 section, 存 localStorage

import { useState, useEffect } from "react";
import { Settings, X, RotateCcw, Eye, EyeOff } from "lucide-react";

interface TrendsConfig {
  volume: boolean;       // 1. 训练量趋势
  zones: boolean;        // 2. 7 区分布
  metrics: boolean;      // 3. 关键指标 (NP/IF/HR)
  rpe: boolean;          // 4. RPE 主观疲劳
  acwr: boolean;         // 5. ACWR
  pmc: boolean;          // 6. PMC
  elevation: boolean;    // 7. 海拔
}

const DEFAULT: TrendsConfig = {
  volume: true,
  zones: true,
  metrics: true,
  rpe: true,
  acwr: true,
  pmc: true,
  elevation: true,
};

const STORAGE_KEY = "trends.visibleSections.v1";

const SECTIONS: Array<{ key: keyof TrendsConfig; label: string; emoji: string }> = [
  { key: "volume", label: "训练量 (TSS)", emoji: "📊" },
  { key: "zones", label: "7 区分布", emoji: "🎨" },
  { key: "metrics", label: "关键指标 (NP/IF/HR)", emoji: "📈" },
  { key: "rpe", label: "RPE 主观疲劳", emoji: "💪" },
  { key: "acwr", label: "ACWR 急慢性", emoji: "⚠️" },
  { key: "pmc", label: "PMC (CTL/ATL/TSB)", emoji: "🎯" },
  { key: "elevation", label: "海拔", emoji: "⛰️" },
];

export function useTrendsConfig(): [TrendsConfig, (c: TrendsConfig) => void] {
  const [config, setConfig] = useState<TrendsConfig>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return { ...DEFAULT, ...JSON.parse(stored) };
      }
    } catch {}
    return DEFAULT;
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {}
  }, [config]);

  return [config, setConfig];
}

export function TrendsConfigBar({
  config,
  onChange,
}: {
  config: TrendsConfig;
  onChange: (c: TrendsConfig) => void;
}) {
  const [open, setOpen] = useState(false);
  const visible = Object.values(config).filter(Boolean).length;
  const total = Object.keys(config).length;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition"
      >
        <Settings className="w-3.5 h-3.5" />
        配置 · {visible}/{total}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-indigo-600" />
                <h2 className="text-base font-semibold text-slate-800">趋势页配置</h2>
              </div>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-500 mb-3">
              选择要在趋势页显示哪些 section. 配置存浏览器 localStorage.
            </p>

            <div className="space-y-1.5">
              {SECTIONS.map((s) => {
                const on = config[s.key];
                return (
                  <button
                    key={s.key}
                    onClick={() => onChange({ ...config, [s.key]: !on })}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border transition ${
                      on
                        ? "bg-indigo-50 border-indigo-200 text-indigo-700"
                        : "bg-slate-50 border-slate-200 text-slate-500"
                    }`}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-base">{s.emoji}</span>
                      <span className="font-medium">{s.label}</span>
                    </div>
                    {on ? (
                      <Eye className="w-4 h-4" />
                    ) : (
                      <EyeOff className="w-4 h-4 text-slate-300" />
                    )}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-200">
              <button
                onClick={() => onChange(DEFAULT)}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700"
              >
                <RotateCcw className="w-3 h-3" />
                重置
              </button>
              <button
                onClick={() => setOpen(false)}
                className="px-4 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
