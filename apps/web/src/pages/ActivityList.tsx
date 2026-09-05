// 训练列表 — 多维过滤 + 排序 + 分页 (V0.3.4)
//
// 对标 TP Activity Search:
// - 顶部多维过滤栏(日期 / 距离 / TSS / NP / 功率 / 时长 / 心率 / 来源)
// - 顶部聚合统计(总活动数 / 总时长 / 总距离 / 总TSS)
// - 紧凑行 + 状态色(基于 TSS)
// - 排序 + 分页
import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Filter,
  X,
  Calendar,
  Bike,
  Clock,
  Activity as ActivityIcon,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  TrendingUp,
  Mountain,
  Heart,
  Zap,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { ActivitySummary } from "../lib/types";
import { RPEBadge } from "../components/RPEEditor";

// 排序选项
const SORT_OPTIONS = [
  { key: "start_time", label: "日期" },
  { key: "duration_s", label: "时长" },
  { key: "distance_m", label: "距离" },
  { key: "tss", label: "TSS" },
  { key: "avg_power", label: "平均功率" },
  { key: "avg_hr", label: "平均心率" },
] as const;

// 状态色 - 基于 TSS
function tssColor(tss: number | null | undefined): { bg: string; text: string; label: string } {
  if (tss == null) return { bg: "bg-bg-base", text: "text-text-muted", label: "—" };
  if (tss < 50) return { bg: "bg-sky-500/15", text: "text-sky-300", label: "轻松" };
  if (tss < 100) return { bg: "bg-emerald-500/15", text: "text-emerald-300", label: "中等" };
  if (tss < 150) return { bg: "bg-amber-500/15", text: "text-amber-300", label: "高强度" };
  return { bg: "bg-red-500/15", text: "text-red-300", label: "非常难" };
}

function fmtDur(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h${m.toString().padStart(2, "0")}m` : `${m}min`;
}

function fmtKm(m: number | null) {
  if (!m) return "—";
  return `${(m / 1000).toFixed(1)}km`;
}

function fmtDate(s: string) {
  const d = new Date(s);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function ActivityList() {
  const navigate = useNavigate();

  // 过滤状态
  const [filters, setFilters] = useState<{
    date_from: string;
    date_to: string;
    min_distance_km: string;
    max_distance_km: string;
    min_tss: string;
    max_tss: string;
    min_avg_power: string;
    max_avg_power: string;
    min_duration_min: string;
    max_duration_min: string;
    min_avg_hr: string;
    max_avg_hr: string;
  }>({
    date_from: "",
    date_to: "",
    min_distance_km: "",
    max_distance_km: "",
    min_tss: "",
    max_tss: "",
    min_avg_power: "",
    max_avg_power: "",
    min_duration_min: "",
    max_duration_min: "",
    min_avg_hr: "",
    max_avg_hr: "",
  });
  const [sort, setSort] = useState<string>("start_time");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const [pageSize] = useState(20);

  // 数据
  const [activities, setActivities] = useState<ActivitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [aggregate, setAggregate] = useState<{
    count: number; total_duration_s: number; total_tss: number; total_distance_m: number;
  }>({ count: 0, total_duration_s: 0, total_tss: 0, total_distance_m: 0 });
  const [loading, setLoading] = useState(false);

  // 加载
  useEffect(() => {
    loadActivities();
  }, [sort, order, page]);

  async function loadActivities() {
    setLoading(true);
    try {
      // 把空字符串过滤掉
      const params: any = { sort, order, limit: pageSize, offset: page * pageSize };
      Object.entries(filters).forEach(([k, v]) => {
        if (v) params[k] = Number(v) || v;
      });
      const r = await api.listActivities(params);
      setActivities(r.activities);
      setTotal(r.total);
      setAggregate(r.aggregate);
    } catch (e) {
      console.error("load activities failed:", e);
    } finally {
      setLoading(false);
    }
  }

  function applyFilters() {
    setPage(0);
    loadActivities();
  }

  function resetFilters() {
    setFilters({
      date_from: "", date_to: "",
      min_distance_km: "", max_distance_km: "",
      min_tss: "", max_tss: "",
      min_avg_power: "", max_avg_power: "",
      min_duration_min: "", max_duration_min: "",
      min_avg_hr: "", max_avg_hr: "",
    });
    setPage(0);
    setTimeout(loadActivities, 0);
  }

  function toggleSort(field: string) {
    if (sort === field) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(field);
      setOrder("desc");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* ============== 顶部 sticky 工具栏 ============== */}
      <div className="flex-shrink-0 bg-bg-elevated border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <Bike className="w-5 h-5 text-accent" />
          <h1 className="text-lg font-semibold">训练列表</h1>
          <span className="text-xs text-text-muted">
            ({total} 条)
          </span>
        </div>
        <button
          onClick={() => navigate("/data/import")}
          className="px-3 py-1.5 bg-accent text-bg-base rounded-lg text-sm font-medium flex items-center gap-1.5"
        >
          <Zap className="w-3.5 h-3.5" />
          上传 FIT
        </button>
      </div>

      {/* ============== 聚合统计卡 ============== */}
      <div className="flex-shrink-0 grid grid-cols-4 gap-3 px-6 py-3 border-b border-border bg-bg-elevated/50">
        <StatCard icon={ActivityIcon} label="活动数" value={String(aggregate.count)} unit="次" color="accent" />
        <StatCard icon={Clock} label="总时长" value={fmtDur(aggregate.total_duration_s)} color="emerald" />
        <StatCard icon={Mountain} label="总距离" value={fmtKm(aggregate.total_distance_m)} color="sky" />
        <StatCard icon={TrendingUp} label="总 TSS" value={String(aggregate.total_tss)} color="amber" />
      </div>

      {/* ============== 过滤栏 ============== */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-border bg-bg-elevated/30">
        <div className="grid grid-cols-12 gap-2 items-end">
          {/* 日期范围 */}
          <div className="col-span-2">
            <FilterLabel icon={Calendar}>日期</FilterLabel>
            <div className="flex gap-1">
              <input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
          {/* 距离 */}
          <div className="col-span-2">
            <FilterLabel icon={Mountain}>距离(km)</FilterLabel>
            <div className="flex gap-1">
              <input type="number" placeholder="min" value={filters.min_distance_km} onChange={(e) => setFilters({ ...filters, min_distance_km: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="number" placeholder="max" value={filters.max_distance_km} onChange={(e) => setFilters({ ...filters, max_distance_km: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
          {/* TSS */}
          <div className="col-span-2">
            <FilterLabel icon={TrendingUp}>TSS</FilterLabel>
            <div className="flex gap-1">
              <input type="number" placeholder="min" value={filters.min_tss} onChange={(e) => setFilters({ ...filters, min_tss: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="number" placeholder="max" value={filters.max_tss} onChange={(e) => setFilters({ ...filters, max_tss: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
          {/* 功率 */}
          <div className="col-span-2">
            <FilterLabel icon={Zap}>平均功率(W)</FilterLabel>
            <div className="flex gap-1">
              <input type="number" placeholder="min" value={filters.min_avg_power} onChange={(e) => setFilters({ ...filters, min_avg_power: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="number" placeholder="max" value={filters.max_avg_power} onChange={(e) => setFilters({ ...filters, max_avg_power: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
          {/* 时长 */}
          <div className="col-span-2">
            <FilterLabel icon={Clock}>时长(min)</FilterLabel>
            <div className="flex gap-1">
              <input type="number" placeholder="min" value={filters.min_duration_min} onChange={(e) => setFilters({ ...filters, min_duration_min: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="number" placeholder="max" value={filters.max_duration_min} onChange={(e) => setFilters({ ...filters, max_duration_min: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
          {/* 心率 */}
          <div className="col-span-2">
            <FilterLabel icon={Heart}>心率</FilterLabel>
            <div className="flex gap-1">
              <input type="number" placeholder="min" value={filters.min_avg_hr} onChange={(e) => setFilters({ ...filters, min_avg_hr: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
              <input type="number" placeholder="max" value={filters.max_avg_hr} onChange={(e) => setFilters({ ...filters, max_avg_hr: e.target.value })} className="w-full px-2 py-1 bg-bg-base border border-border rounded text-xs" />
            </div>
          </div>
        </div>
        <div className="flex gap-2 mt-3">
          <button
            onClick={applyFilters}
            className="px-4 py-1.5 bg-accent text-bg-base rounded-lg text-sm font-medium flex items-center gap-1.5"
          >
            <Search className="w-3.5 h-3.5" />
            应用过滤
          </button>
          <button
            onClick={resetFilters}
            className="px-4 py-1.5 bg-bg-base border border-border rounded-lg text-sm text-text-muted flex items-center gap-1.5 hover:border-accent/50"
          >
            <X className="w-3.5 h-3.5" />
            重置
          </button>
        </div>
      </div>

      {/* ============== 列表 ============== */}
      <div className="flex-1 overflow-auto px-6 py-3">
        {loading && <div className="text-center text-text-muted py-8">加载中...</div>}
        {!loading && activities.length === 0 && (
          <div className="text-center text-text-muted py-12">
            <ActivityIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <div>没有匹配的活动</div>
            <div className="text-xs mt-1">试试调整过滤条件,或点 "上传 FIT" 导入数据</div>
          </div>
        )}
        {!loading && activities.length > 0 && (
          <div className="bg-bg-elevated border border-border rounded-xl overflow-hidden">
            {/* 表头 */}
            <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-bg-base border-b border-border text-[10px] font-semibold text-text-muted uppercase">
              <SortHeader field="start_time" sort={sort} order={order} onClick={toggleSort} className="col-span-2">日期</SortHeader>
              <SortHeader field="duration_s" sort={sort} order={order} onClick={toggleSort} className="col-span-1">时长</SortHeader>
              <SortHeader field="distance_m" sort={sort} order={order} onClick={toggleSort} className="col-span-1">距离</SortHeader>
              <SortHeader field="avg_power" sort={sort} order={order} onClick={toggleSort} className="col-span-1">平均功率</SortHeader>
              <SortHeader field="tss" sort={sort} order={order} onClick={toggleSort} className="col-span-1">TSS</SortHeader>
              <SortHeader field="avg_hr" sort={sort} order={order} onClick={toggleSort} className="col-span-1">心率</SortHeader>
              <div className="col-span-2">NP/IF</div>
              <div className="col-span-1">来源</div>
              <div className="col-span-1">状态</div>
              <div className="col-span-2">标题</div>
            </div>
            {/* 数据行 */}
            {activities.map((a) => {
              const tss = a.tss;
              const c = tssColor(tss);
              return (
                <div
                  key={a.id}
                  onClick={() => {
                    navigate(`/training/activities/${a.id}`);
                  }}
                  className="grid grid-cols-12 gap-2 px-3 py-2.5 border-b border-border/50 text-xs hover:bg-bg-base cursor-pointer transition items-center"
                >
                  <div className="col-span-2 font-medium">{fmtDate(a.start_time)} <span className="text-text-muted text-[10px]">{new Date(a.start_time).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span></div>
                  <div className="col-span-1">{fmtDur(a.duration_s)}</div>
                  <div className="col-span-1">{fmtKm(a.distance_m)}</div>
                  <div className="col-span-1">{a.avg_power ? `${a.avg_power}W` : "—"}</div>
                  <div className="col-span-1 font-mono">{tss ?? "—"}</div>
                  <div className="col-span-1">{a.avg_hr ? `${a.avg_hr}bpm` : "—"}</div>
                  <div className="col-span-2 text-text-muted">
                    {a.normalized_power ? `NP ${a.normalized_power}W` : ""}
                  </div>
                  <div className="col-span-1 text-[10px] text-text-muted">{a.source}</div>
                  <div className="col-span-1">
                    <span className={clsx("px-2 py-0.5 rounded text-[10px] font-medium", c.bg, c.text)}>
                      {c.label}
                    </span>
                  </div>
                  <div className="col-span-1">
                    <RPEBadge rpe={a.rpe} rpeNote={a.rpe_note} />
                  </div>
                  <div className="col-span-2 truncate text-text-muted text-[10px]">
                    {a.has_report ? "📝" : ""} {a.start_time.split("T")[0]}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ============== 底部 sticky 分页 ============== */}
      {total > pageSize && (
        <div className="flex-shrink-0 bg-bg-elevated border-t border-border px-6 py-3 flex items-center justify-between sticky bottom-0">
          <div className="text-xs text-text-muted">
            第 {page * pageSize + 1} - {Math.min((page + 1) * pageSize, total)} 条 / 共 {total} 条
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="p-1.5 rounded hover:bg-bg-base disabled:opacity-30"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1 text-sm">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="p-1.5 rounded hover:bg-bg-base disabled:opacity-30"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// =============== 子组件 ===============

function StatCard({ icon: Icon, label, value, unit, color }: { icon: LucideIcon; label: string; value: string; unit?: string; color: string }) {
  return (
    <div className="bg-bg-base border border-border rounded-lg px-3 py-2 flex items-center gap-3">
      <Icon className={clsx("w-5 h-5", `text-${color}-400`)} />
      <div>
        <div className="text-[10px] text-text-muted">{label}</div>
        <div className="text-lg font-bold leading-tight">
          {value}
          {unit && <span className="text-xs text-text-muted ml-0.5">{unit}</span>}
        </div>
      </div>
    </div>
  );
}

function FilterLabel({ icon: Icon, children }: { icon: LucideIcon; children: React.ReactNode }) {
  return (
    <div className="text-[10px] text-text-muted mb-1 flex items-center gap-1">
      <Icon className="w-3 h-3" />
      {children}
    </div>
  );
}

function SortHeader({ field, sort, order, onClick, className, children }: {
  field: string;
  sort: string;
  order: "asc" | "desc";
  onClick: (f: string) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const active = sort === field;
  return (
    <button
      onClick={() => onClick(field)}
      className={clsx(
        "flex items-center gap-1 text-left hover:text-text-primary transition",
        active ? "text-accent" : "text-text-muted",
        className
      )}
    >
      {children}
      {active ? (order === "desc" ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />) : null}
    </button>
  );
}
