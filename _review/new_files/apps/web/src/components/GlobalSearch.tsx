// V0.8.2 UX-1: Cmd+K 全局搜索 (替代 TopBar 死按钮)
// 搜索范围: 活动 (按日期/距离/TSS 粗筛) + 知识库 (FTS5)
// 快捷键: Cmd+K (Mac) / Ctrl+K (Win/Linux)
import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bike, BookOpen, X, CornerDownLeft, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";

interface ActivityHit {
  id: number;
  date: string;
  title: string;
  distance_km: number | null;
  duration_s: number;
  tss: number | null;
}

interface KbHit {
  path: string;
  title: string;
  snippet: string;
}

type Hit = { type: "activity"; data: ActivityHit } | { type: "kb"; data: KbHit };

function fmtDur(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h${m.toString().padStart(2, "0")}m` : `${m}min`;
}

export function GlobalSearch() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Cmd+K / Ctrl+K 快捷键
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 打开时聚焦 input
  useEffect(() => {
    if (open) {
      setQ("");
      setHits([]);
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // 防抖搜索
  useEffect(() => {
    const query = q.trim();
    if (!query) {
      setHits([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const [acts, kb] = await Promise.allSettled([
          api.listActivities({ limit: 5, sort: "start_time", order: "desc" }).catch(() => null),
          api.kbSearch(query, 5).catch(() => null),
        ]);
        const results: Hit[] = [];
        if (acts.status === "fulfilled" && acts.value) {
          // 客户端再过滤 (后端没文本搜索)
          const lower = query.toLowerCase();
          for (const a of acts.value.activities || []) {
            const dateStr = a.start_time?.slice(0, 10) || "";
            const hit =
              dateStr.includes(query) ||
              a.id?.toString() === query ||
              (a.device || "").toLowerCase().includes(lower) ||
              (a.tss != null && a.tss.toString().includes(query));
            if (hit) {
              results.push({
                type: "activity",
                data: {
                  id: a.id,
                  date: dateStr,
                  title: dateStr || `活动 #${a.id}`,
                  distance_km: a.distance_m ? a.distance_m / 1000 : null,
                  duration_s: a.duration_s || 0,
                  tss: a.tss,
                },
              });
            }
          }
        }
        if (kb.status === "fulfilled" && kb.value) {
          for (const r of kb.value.results || []) {
            results.push({
              type: "kb",
              data: {
                path: r.document_path,
                title: r.document_title || r.document_path,
                snippet: r.snippet || "",
              },
            });
          }
        }
        setHits(results.slice(0, 8));
        setActiveIdx(0);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const goHit = useCallback(
    (hit: Hit) => {
      setOpen(false);
      if (hit.type === "activity") {
        navigate(`/training/activities/${hit.data.id}`);
      } else {
        navigate(`/data/knowledge?path=${encodeURIComponent(hit.data.path)}`);
      }
    },
    [navigate]
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && hits[activeIdx]) {
      e.preventDefault();
      goHit(hits[activeIdx]);
    }
  };

  return (
    <>
      {/* 触发按钮 (替代 TopBar 死 input) */}
      <button
        onClick={() => setOpen(true)}
        className="bg-bg-input border border-border rounded-md px-3 py-1.5 text-sm text-text-muted flex items-center gap-2 w-72 hover:border-accent-primary transition-colors"
        title="搜索 (Cmd+K / Ctrl+K)"
      >
        <Search size={14} />
        <span className="flex-1 text-left">搜索活动 / 知识库…</span>
        <kbd className="text-[10px] bg-bg-elevated px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
      </button>

      {/* 搜索弹窗 */}
      {open && (
        <div
          className="fixed inset-0 z-[9997] bg-black/40 backdrop-blur-sm flex items-start justify-center pt-[10vh]"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-border w-[640px] max-w-[92vw] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
              <Search size={16} className="text-text-muted" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="搜索活动 (日期 / 编号) 或知识库…"
                className="flex-1 outline-none text-sm text-text-primary placeholder-text-muted"
              />
              <kbd className="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded font-mono">ESC</kbd>
              <button onClick={() => setOpen(false)} className="text-text-muted hover:text-text-primary">
                <X size={14} />
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto">
              {!q && (
                <div className="p-6 text-sm text-text-muted text-center">
                  试试搜日期 (如 2026-08-26) / 活动编号 / 训练学关键词 (FTP / 甜区 / 阈值)
                </div>
              )}
              {q && loading && hits.length === 0 && (
                <div className="p-6 text-sm text-text-muted text-center">搜索中…</div>
              )}
              {q && !loading && hits.length === 0 && (
                <div className="p-6 text-sm text-text-muted text-center">没找到匹配结果</div>
              )}
              {hits.map((h, i) => (
                <button
                  key={`${h.type}-${h.type === "activity" ? h.data.id : h.data.path}`}
                  onClick={() => goHit(h)}
                  onMouseEnter={() => setActiveIdx(i)}
                  className={clsx(
                    "w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors",
                    i === activeIdx ? "bg-accent-primary/10" : "hover:bg-bg-elevated"
                  )}
                >
                  {h.type === "activity" ? (
                    <>
                      <div className="w-8 h-8 rounded-md bg-accent-primary/15 text-accent-primary flex items-center justify-center flex-shrink-0">
                        <Bike size={14} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-text-primary truncate">
                          {h.data.date} 训练
                        </div>
                        <div className="text-xs text-text-muted">
                          {h.data.distance_km != null ? `${h.data.distance_km.toFixed(1)} km` : "—"}
                          {" · "}
                          {fmtDur(h.data.duration_s)}
                          {h.data.tss != null ? ` · TSS ${h.data.tss}` : ""}
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="w-8 h-8 rounded-md bg-amber-100 text-amber-700 flex items-center justify-center flex-shrink-0">
                        <BookOpen size={14} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-text-primary truncate">{h.data.title}</div>
                        <div className="text-xs text-text-muted truncate">{h.data.path}</div>
                      </div>
                    </>
                  )}
                  <ArrowRight size={14} className="text-text-muted flex-shrink-0" />
                </button>
              ))}
            </div>

            {hits.length > 0 && (
              <div className="px-4 py-2 border-t border-border bg-bg-elevated/50 text-[11px] text-text-muted flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <kbd className="bg-bg-base px-1 py-0.5 rounded">↑</kbd>
                  <kbd className="bg-bg-base px-1 py-0.5 rounded">↓</kbd>
                  切换
                </span>
                <span className="flex items-center gap-1">
                  <CornerDownLeft size={10} />
                  打开
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="bg-bg-base px-1 py-0.5 rounded">ESC</kbd>
                  关闭
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
