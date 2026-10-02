// 个人画像 — V0.8.2
// 改动:
//   U-3 自动保存: 任一字段变更 1500ms 后自动 PATCH, 显示 "已自动保存" 状态
//   U-3 离开警告: 有未保存变更时 beforeunload 提示
//   U-3 顶部加 dirty 状态条 (有 X 项待保存)
import { useEffect, useRef, useState } from "react";
import { Save, RefreshCw, AlertCircle, Check, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import type { Athlete } from "../lib/types";
import { MetricCard } from "../components/MetricCard";

type SaveState = "idle" | "dirty" | "saving" | "saved";

export function Profile() {
  const toast = useToast();
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [editing, setEditing] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.getAthlete().then(setAthlete);
  }, []);

  // U-3 离开页面前警告
  useEffect(() => {
    if (saveState !== "dirty" && saveState !== "saving") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "有未保存的修改, 确定要离开吗?";
      return e.returnValue;
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [saveState]);

  // 清理 timer
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  if (!athlete) {
    return <div className="p-6 text-text-muted">加载中…</div>;
  }

  const dirtyKeys = Object.keys(editing);

  // V0.8.3 B4 fix: 不能用 typeof original === "number" 判 null 字段 (typeof null === "object")
  // 显式列数字字段, 让初始 null 的 weight_kg / lthr / height_cm / ftp_estimated 也能正常输入
  const NUMERIC_FIELDS = new Set([
    "ftp", "ftp_estimated", "max_hr", "lthr", "weight_kg", "height_cm",
  ]);

  const onChange = (key: keyof Athlete, raw: string) => {
    const isNum = NUMERIC_FIELDS.has(key as string);
    let parsed: any;
    if (raw === "") {
      parsed = null;  // 显式清空 → 让 PATCH 走 null 路径
    } else if (isNum) {
      parsed = Number(raw);
      if (Number.isNaN(parsed)) return; // 非法输入不更新
    } else {
      parsed = raw;
    }
    setEditing((prev) => ({ ...prev, [key]: parsed }));
    setSaveState("dirty");
  };

  const doSave = async (showFeedback = true) => {
    if (dirtyKeys.length === 0) return;
    setSaving(true);
    setSaveState("saving");
    try {
      const updated = await api.updateAthlete(editing);
      setAthlete(updated);
      setEditing({});
      setSaveState("saved");
      if (showFeedback) toast.success("已保存");
      // 3 秒后回到 idle
      setTimeout(() => {
        setSaveState((s) => (s === "saved" ? "idle" : s));
      }, 3000);
    } catch (e) {
      setSaveState("dirty");
      toast.error("保存失败: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  // 防抖自动保存 (1.5s)
  useEffect(() => {
    if (saveState !== "dirty") return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doSave(false);
    }, 1500);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const onRefreshFtp = async () => {
    setRefreshing(true);
    try {
      await api.refreshAthleteFtp();
      const updated = await api.getAthlete();
      setAthlete(updated);
      toast.success("FTP 已重算");
    } catch (e) {
      toast.error("重算失败: " + (e as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  const fields: Array<{ key: keyof Athlete; label: string; unit?: string }> = [
    { key: "name", label: "姓名" },
    { key: "ftp", label: "FTP", unit: "W" },
    { key: "ftp_estimated", label: "FTP 估算", unit: "W" },
    { key: "max_hr", label: "最大心率", unit: "bpm" },
    { key: "lthr", label: "乳酸阈心率", unit: "bpm" },
    { key: "weight_kg", label: "体重", unit: "kg" },
    { key: "height_cm", label: "身高", unit: "cm" },
  ];

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">个人画像</h1>
        <p className="text-sm text-text-muted mt-1">
          这些数据用于计算强度因子(IF)、训练压力(TSS)等核心指标。
        </p>
      </div>

      {/* U-3 自动保存状态条 */}
      {saveState !== "idle" && (
        <div
          className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm ${
            saveState === "dirty"
              ? "bg-status-warning text-accent-warning border border-border"
              : saveState === "saving"
              ? "bg-status-info text-accent-primary border border-border"
              : "bg-status-success text-accent-success border border-border"
          }`}
        >
          {saveState === "dirty" && (
            <>
              <AlertCircle size={14} />
              <span>有 {dirtyKeys.length} 项待保存, 1.5 秒后自动保存</span>
            </>
          )}
          {saveState === "saving" && (
            <>
              <Loader2 size={14} className="animate-spin" />
              <span>正在保存…</span>
            </>
          )}
          {saveState === "saved" && (
            <>
              <Check size={14} />
              <span>已自动保存</span>
            </>
          )}
        </div>
      )}

      {/* 概览 */}
      <section className="grid grid-cols-4 gap-3">
        <MetricCard label="总训练" value={athlete.total_activities} unit="次" />
        <MetricCard label="本周 TSS" value={athlete.weekly_tss} accent="primary" />
        <MetricCard
          label="FTP"
          value={athlete.ftp || "—"}
          unit="W"
          accent="success"
        />
        <MetricCard
          label="FTP 估算"
          value={athlete.ftp_estimated || "—"}
          unit="W"
          hint="基于历史活动"
        />
      </section>

      {/* 编辑 */}
      <section className="panel">
        <div className="panel-header">
          <div className="text-sm font-medium text-text-primary">基础信息</div>
          <button
            onClick={onRefreshFtp}
            disabled={refreshing}
            className="btn-ghost text-xs"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            重算 FTP
          </button>
        </div>
        <div className="p-4 space-y-3">
          {fields.map((f) => {
            const isDirty = f.key in editing;
            const displayValue = isDirty
              ? String(editing[f.key] ?? "")
              : String(athlete[f.key] ?? "");
            return (
              <div key={f.key} className="grid grid-cols-3 items-center gap-3">
                <div className="text-sm text-text-secondary">
                  {f.label}
                  {f.unit && <span className="text-text-muted ml-1">({f.unit})</span>}
                </div>
                <div className="col-span-2 relative">
                  <input
                    type={typeof athlete[f.key] === "number" ? "number" : "text"}
                    value={displayValue}
                    onChange={(e) => onChange(f.key, e.target.value)}
                    placeholder={String(athlete[f.key] ?? "未设置")}
                    className={`w-full bg-bg-subtle border rounded-md px-3 py-1.5 text-sm text-text-primary font-mono focus:outline-none focus:border-accent-primary ${
                      isDirty ? "border-border bg-status-warning/50" : "border-border"
                    }`}
                  />
                  {isDirty && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-status-warning0" />
                  )}
                </div>
              </div>
            );
          })}
          <div className="flex justify-end pt-2">
            <button
              onClick={() => doSave(true)}
              disabled={saving || dirtyKeys.length === 0}
              className="btn-primary"
            >
              <Save size={14} />
              {saving ? "保存中..." : dirtyKeys.length > 0 ? `保存 (${dirtyKeys.length})` : "保存修改"}
            </button>
          </div>
        </div>
      </section>

      {/* 提示 */}
      <section className="panel p-4 text-sm text-text-muted">
        <div className="text-text-primary font-medium mb-2">数据说明</div>
        <ul className="space-y-1 ml-4 list-disc text-xs">
          <li>FTP 估算基于你过去 30 次训练中的最高 20 分钟平均功率 × 0.95</li>
          <li>最大心率用于计算 HR 区间分布(5 区法)</li>
          <li>乳酸阈心率(LTHR)用于精确划分有氧 / 无氧区间</li>
          <li>这些数据都存放在你本地的 SQLite,不上传</li>
          <li className="text-accent-primary font-medium">
            💡 V0.8.2 起: 字段修改后 1.5 秒自动保存, 无需手动点
          </li>
        </ul>
      </section>
    </div>
  );
}
