// 周报 PDF 下载按钮 — V0.7.3

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import clsx from "clsx";

export function ReportDownloadButton({ days = 7, label = "导出周报" }: { days?: number; label?: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/reports/weekly?days=${days}`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const today = new Date().toISOString().slice(0, 10);
      a.download = `cycling-coach-weekly-${today}-d${days}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "下载失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={clsx(
        "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition",
        loading
          ? "bg-slate-100 text-slate-400 cursor-wait"
          : "bg-indigo-600 text-white hover:bg-indigo-700"
      )}
    >
      {loading ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <FileDown className="w-3.5 h-3.5" />
      )}
      {loading ? "生成中…" : label}
      {error && <span className="ml-1 text-rose-300">({error})</span>}
    </button>
  );
}
