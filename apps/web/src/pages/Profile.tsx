// 个人画像
import { useEffect, useState } from "react";
import { Save, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { Athlete } from "../lib/types";
import { MetricCard } from "../components/MetricCard";

export function Profile() {
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [editing, setEditing] = useState<Partial<Athlete>>({});
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    api.getAthlete().then(setAthlete);
  }, []);

  if (!athlete) {
    return <div className="p-6 text-text-muted">加载中…</div>;
  }

  const onSave = async () => {
    setSaving(true);
    try {
      const updated = await api.updateAthlete(editing);
      setAthlete(updated);
      setEditing({});
    } catch (e) {
      alert("保存失败:" + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const onRefreshFtp = async () => {
    setRefreshing(true);
    try {
      await fetch("/api/athlete/refresh-ftp", { method: "POST" });
      const updated = await api.getAthlete();
      setAthlete(updated);
    } catch (e) {
      alert("重算失败:" + (e as Error).message);
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
          {fields.map((f) => (
            <div key={f.key} className="grid grid-cols-3 items-center gap-3">
              <div className="text-sm text-text-secondary">
                {f.label}
                {f.unit && <span className="text-text-muted ml-1">({f.unit})</span>}
              </div>
              <div className="col-span-2">
                <input
                  type={typeof athlete[f.key] === "number" ? "number" : "text"}
                  defaultValue={String(athlete[f.key] ?? "")}
                  placeholder={String(athlete[f.key] ?? "未设置")}
                  onChange={(e) =>
                    setEditing((prev) => ({
                      ...prev,
                      [f.key]:
                        typeof athlete[f.key] === "number"
                          ? e.target.value === ""
                            ? null
                            : Number(e.target.value)
                          : e.target.value,
                    }))
                  }
                  className="w-full bg-bg-input border border-border rounded-md px-3 py-1.5 text-sm text-text-primary font-mono focus:outline-none focus:border-accent-primary"
                />
              </div>
            </div>
          ))}
          <div className="flex justify-end pt-2">
            <button
              onClick={onSave}
              disabled={saving || Object.keys(editing).length === 0}
              className="btn-primary"
            >
              <Save size={14} />
              {saving ? "保存中..." : "保存修改"}
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
        </ul>
      </section>
    </div>
  );
}
