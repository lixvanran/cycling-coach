// 单次训练详情 — 模仿 TP 风格布局
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  RefreshCw,
  FileText,
  AlertCircle,
  Clock,
  Target,
} from "lucide-react";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import type { ActivityDetail as ActivityDetailT } from "../lib/types";
import { useAppStore } from "../store/useAppStore";
import { MetricCard } from "../components/MetricCard";
import { PowerCurveChart } from "../components/PowerCurveChart";
import { PowerZoneChart } from "../components/PowerZoneChart";
import { HRZoneChart } from "../components/HRZoneChart";
import { PowerHrTimeChart } from "../components/PowerHrTimeChart";
import { WbalChart } from "../components/WbalChart";
import { ElevationProfileChart } from "../components/ElevationProfileChart";
import { DecouplingCard } from "../components/DecouplingCard";
import { GPSMap } from "../components/GPSMap";
import { RPEEditor, RPEBadge } from "../components/RPEEditor";

export function ActivityDetail() {
  const selectedId = useAppStore((s) => s.selectedActivityId);
  const setView = useAppStore((s) => s.setView);
  const [activity, setActivity] = useState<ActivityDetailT | null>(null);
  const [athlete, setAthlete] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [powerCurve, setPowerCurve] = useState<any>(null);
  const [powerZonesDetailed, setPowerZonesDetailed] = useState<any>(null);
  const [wbal, setWbal] = useState<any>(null);
  const [cpEstimate, setCpEstimate] = useState<any>(null);
  const [decoupling, setDecoupling] = useState<any>(null);
  const [ftpEstimate, setFtpEstimate] = useState<any>(null);
  const [ftpLoading, setFtpLoading] = useState(false);

  const estimateFtp = async () => {
    if (!activity) return;
    setFtpLoading(true);
    try {
      const e = await api.ftpEstimate(activity.id, "auto");
      setFtpEstimate(e);
    } catch (e) {
      console.error("FTP 估算失败:", e);
    } finally {
      setFtpLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    Promise.all([
      api.getActivity(selectedId),
      api.getAthlete(),
      api.getPowerCurve(selectedId).catch(() => null),
      api.getPowerZonesDetailed(selectedId).catch(() => null),
      api.getWbal(selectedId).catch(() => null),
      api.getCpEstimate(selectedId).catch(() => null),
      api.getDecoupling(selectedId).catch(() => null),
    ])
      .then(([a, at, pc, pzd, wb, cp3, dec]) => {
        setActivity(a);
        setAthlete(at);
        setPowerCurve(pc);
        setPowerZonesDetailed(pzd);
        setWbal(wb);
        setCpEstimate(cp3);
        setDecoupling(dec);
      })
      .finally(() => setLoading(false));
  }, [selectedId]);

  if (!selectedId) {
    return (
      <div className="h-full flex items-center justify-center text-text-muted">
        未选择训练
      </div>
    );
  }

  if (loading || !activity) {
    return <div className="p-6 text-text-muted">加载中…</div>;
  }

  const m = activity.metrics;
  const dt = new Date(activity.start_time);
  const ftp = athlete?.ftp || m?.ftp_estimated || 250;
  const lthr = athlete?.lthr || Math.round((athlete?.max_hr || 190) * 0.89);

  const onAnalyze = async () => {
    setAnalyzing(true);
    try {
      await api.analyzeActivity(activity.id);
      const poll = setInterval(async () => {
        const a = await api.getActivity(activity.id);
        setActivity(a);
        if (a.report_status === "done" || a.report_status === "failed") {
          clearInterval(poll);
          setAnalyzing(false);
        }
      }, 2000);
      setTimeout(() => {
        clearInterval(poll);
        setAnalyzing(false);
      }, 60000);
    } catch (e) {
      setAnalyzing(false);
      toast.error("触发分析失败:" + (e as Error).message);
    }
  };

  // 报告状态判断
  const hasReport = !!(activity.report && activity.report.trim());
  const reportFailed = activity.report_status === "failed";
  const reportRunning =
    activity.report_status === "analyzing" || analyzing;

  return (
    <div className="overflow-y-auto h-full">
      {/* 顶部导航 */}
      <div className="sticky top-0 z-10 bg-bg-base/80 backdrop-blur-glass border-b border-border px-6 py-3 flex items-center gap-3">
        <button onClick={() => setView("activities")} className="btn-ghost p-1.5">
          <ArrowLeft size={16} />
        </button>
        <div>
          <div className="text-lg font-semibold text-text-primary">
            {dt.toLocaleDateString("zh-CN", {
              year: "numeric",
              month: "long",
              day: "numeric",
              weekday: "long",
            })}
          </div>
          <div className="text-xs text-text-muted flex items-center gap-2 mt-0.5">
            <Clock size={11} />
            {dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
            {activity.device && ` · ${activity.device}`}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={onAnalyze} disabled={reportRunning} className="btn-primary">
            <RefreshCw size={14} className={reportRunning ? "animate-spin" : ""} />
            {reportRunning
              ? "分析中..."
              : hasReport
              ? "重新分析"
              : "AI 分析"}
          </button>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* 1. 核心指标 6 卡 */}
        <section>
          <div className="grid grid-cols-6 gap-3">
            <MetricCard label="时长" value={formatDuration(activity.duration_s)} />
            <MetricCard
              label="距离"
              value={activity.distance_m ? (activity.distance_m / 1000).toFixed(1) : "—"}
              unit="km"
            />
            <MetricCard label="平均功率" value={activity.avg_power} unit="W" />
            <MetricCard
              label="归一化功率"
              value={m?.normalized_power}
              unit="W"
              accent="primary"
            />
            <MetricCard
              label="IF"
              value={m?.intensity_factor?.toFixed(2)}
              hint={`FTP ${ftp}W`}
            />
            <MetricCard
              label="TSS"
              value={m?.tss}
              accent={
                (m?.tss || 0) >= 150
                  ? "danger"
                  : (m?.tss || 0) >= 100
                  ? "warning"
                  : "default"
              }
            />
          </div>
        </section>

        {/* 2. 训练全景图(功率 + 心率 + 踏频 + 海拔) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">
              训练图
            </div>
            <div className="text-xs text-text-muted">点击 legend 可切换显示</div>
          </div>
          <PowerHrTimeChart samples={activity.samples} ftp={ftp} />
        </section>

        {/* 1.5 海拔剖面图 (V0.6.1 增强) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">海拔剖面</div>
            <div className="text-xs text-text-muted">爬升/下降 + 自动识别主要爬升段 (红虚线)</div>
          </div>
          <div className="p-4">
            <ElevationProfileChart samples={activity.samples} height={200} />
          </div>
        </section>

        {/* 1.5 FTP 估算 (V0.6.1 新增) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              <Target className="w-4 h-4 text-accent" />
              FTP 估算 (学术: 4 协议综合)
            </div>
            <button
              onClick={estimateFtp}
              disabled={ftpLoading}
              className="text-xs text-primary hover:underline"
            >
              {ftpLoading ? "估算中..." : ftpEstimate ? "重新估算" : "运行估算"}
            </button>
          </div>
          <div className="p-4">
            {ftpEstimate ? (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-xs text-text-muted">估算方法</div>
                    <div className="text-sm font-medium">{ftpEstimate.method_label}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted">FTP 估算</div>
                    <div className="text-2xl font-bold font-mono">
                      {ftpEstimate.ftp_w} <span className="text-sm text-text-muted">W</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted">置信度</div>
                    <div className="text-sm font-mono">{Math.round(ftpEstimate.confidence * 100)}%</div>
                  </div>
                </div>
                {ftpEstimate.notes && ftpEstimate.notes.length > 0 && (
                  <div className="text-xs text-text-muted space-y-0.5 pt-2 border-t border-border">
                    {ftpEstimate.notes.map((n: string, i: number) => (
                      <div key={i}>· {n}</div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-text-muted text-center py-2">
                点击右上角"运行估算", 4 种协议 (Coggan 20min / Carmichael 8min / CP 3-param / Ramp) 综合分析
              </div>
            )}
          </div>
        </section>

        {/* 1.6 GPS 地图 (V0.6.1 新增) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">GPS 路线地图</div>
            <div className="text-xs text-text-muted">绿 = 起点 · 红 = 终点 · OpenStreetMap 瓦片</div>
          </div>
          <div className="p-4">
            <GPSMap samples={activity.samples} height={360} />
          </div>
        </section>

        {/* 3. 功率区间 + 心率区间 */}
        <section className="grid grid-cols-2 gap-4">
          <div className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">
                功率区间(Coggan 7 区)
              </div>
              <div className="text-xs text-text-muted">基于 FTP {ftp}W</div>
            </div>
            <div className="p-4">
              <PowerZoneChart zones={powerZonesDetailed || m?.power_zones || {}} />
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">
                心率区间{lthr ? " (LTHR 7 区)" : " (max_hr 5 区)"}
              </div>
              <div className="text-xs text-text-muted">
                HR Drift: {m?.hr_drift ?? "—"} bpm
              </div>
            </div>
            <div className="p-4">
              <HRZoneChart zones={m?.hr_zones || {}} />
            </div>
          </div>
        </section>

        {/* 3.5 W'bal 详细分析 — V0.6 GoldenCheetah 对标 */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">
              W\'bal 曲线 (Skiba 模型)
            </div>
            <div className="text-xs text-text-muted">
              {cpEstimate?.cp_estimated
                ? `CP≈${cpEstimate.cp_estimated}W, W'≈${(cpEstimate.w_prime_estimated || 20000)/1000}kJ, 置信度 ${(cpEstimate.confidence*100).toFixed(0)}%`
                : "CP 估算加载中..."}
            </div>
          </div>
          <div className="p-4">
            <WbalChart wbal={wbal} />
          </div>
        </section>

        {/* 3.6 Pa:HR Decoupling (V0.6.1 GC 杀手锏) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary">Pa:HR Decoupling (有氧效率衰减)</div>
            <div className="text-xs text-text-muted">心率-功率解耦 · Joe Friel / Coggan 标准</div>
          </div>
          <div className="p-4">
            <DecouplingCard data={decoupling} />
          </div>
        </section>

        {/* 3.7 RPE 主观疲劳 (V0.6.1 新增) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              RPE 主观疲劳 (Borg CR-10)
              {activity.rpe != null && <RPEBadge rpe={activity.rpe} rpeNote={activity.rpe_note} />}
            </div>
            <div className="text-xs text-text-muted">训练后 30 分钟内填最准</div>
          </div>
          <div className="p-4">
            <RPEEditor
              activityId={activity.id}
              initialRpe={activity.rpe}
              initialNote={activity.rpe_note}
              onSaved={(rpe, note) => setActivity({ ...activity, rpe, rpe_note: note })}
            />
          </div>
        </section>

        {/* 4. 功率曲线 + 踏频分布 */}
        <section className="grid grid-cols-2 gap-4">
          <div className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">
                功率曲线 (MMP)
              </div>
              <div className="text-xs text-text-muted">各时长最大平均功率</div>
            </div>
            <div className="p-4">
              <PowerCurveChart
                data={powerCurve ?? undefined}
                powerCurve={m?.power_curve}
                ftp={ftp}
              />
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">
                踏频分布
              </div>
              <div className="text-xs text-text-muted">4 区训练学标准</div>
            </div>
            <div className="p-4">
              <HRZoneChart zones={m?.cadence_zones || {}} />
            </div>
          </div>
        </section>

        {/* 5. 间歇表 Laps */}
        {activity.laps && activity.laps.length > 1 && (
          <section className="panel">
            <div className="panel-header">
              <div className="text-sm font-medium text-text-primary">
                间歇/分段 ({activity.laps.length})
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-bg-elevated">
                  <tr className="text-xs text-text-secondary uppercase tracking-wider">
                    <th className="text-left px-4 py-2 font-medium">#</th>
                    <th className="text-left px-4 py-2 font-medium">标签</th>
                    <th className="text-right px-4 py-2 font-medium">时长</th>
                    <th className="text-right px-4 py-2 font-medium">平均功率</th>
                    <th className="text-right px-4 py-2 font-medium">平均心率</th>
                    <th className="text-right px-4 py-2 font-medium">踏频</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.laps.map((lap, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-4 py-2 text-text-muted font-mono">{i + 1}</td>
                      <td className="px-4 py-2 text-text-primary">
                        {lap.label || `Lap ${i + 1}`}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-primary">
                        {formatDuration(lap.duration_s)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-primary">
                        {lap.avg_power ?? "—"} W
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-primary">
                        {lap.avg_hr ?? "—"} bpm
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-text-primary">
                        {lap.avg_cadence ?? "—"} rpm
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 6. 进阶指标 */}
        <section className="grid grid-cols-4 gap-3">
          <MetricCard
            label="效率因子 EF"
            value={m?.efficiency_factor?.toFixed(2)}
            hint="NP / Avg HR"
          />
          <MetricCard
            label="变异性指数 VI"
            value={m?.variability_index?.toFixed(2)}
            hint="NP / Avg Power"
          />
          <MetricCard
            label="平均心率"
            value={activity.avg_hr}
            unit="bpm"
          />
          <MetricCard
            label="平均踏频"
            value={activity.avg_cadence}
            unit="rpm"
          />
        </section>

        {/* 7. AI 教练报告(修复空报告 + 时间戳) */}
        <section className="panel">
          <div className="panel-header">
            <div className="text-sm font-medium text-text-primary flex items-center gap-2">
              <FileText size={14} />
              AI 教练报告
            </div>
            <div className="flex items-center gap-2">
              {activity.report_status === "done" && hasReport && (
                <span className="badge bg-accent-success/15 text-accent-success">
                  已生成
                </span>
              )}
              {reportRunning && (
                <span className="badge bg-accent-warning/15 text-accent-warning">
                  分析中
                </span>
              )}
              {reportFailed && (
                <span className="badge bg-accent-danger/15 text-accent-danger">
                  失败
                </span>
              )}
              {activity.report_status === "pending" && !hasReport && (
                <span className="badge bg-bg-elevated text-text-muted">未生成</span>
              )}
            </div>
          </div>
          <div className="p-4 prose prose-sm max-w-none">
            {hasReport ? (
              <>
                <Markdown text={activity.report!} />
                <div className="mt-4 pt-3 border-t border-border text-xs text-text-muted not-prose">
                  生成于 {new Date(activity.start_time).toLocaleString("zh-CN")}
                  {activity.report!.length > 0 &&
                    ` · ${activity.report!.length} 字`}
                </div>
              </>
            ) : reportRunning ? (
              <div className="text-text-muted text-sm flex items-center gap-2">
                <RefreshCw size={14} className="animate-spin" />
                AI 正在分析中,通常需要 15-30 秒…
              </div>
            ) : reportFailed ? (
              <div className="text-accent-danger text-sm flex items-center gap-2">
                <AlertCircle size={14} />
                上次分析失败。点击右上角「重新分析」重试。
              </div>
            ) : (
              <div className="text-text-muted text-sm">
                点击右上角「AI 分析」生成报告。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// 轻量 Markdown 渲染
function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div>
      {lines.map((line, i) => {
        if (line.startsWith("# ")) {
          return <h1 key={i} className="text-xl font-semibold mt-4 mb-2 text-text-primary">{line.slice(2)}</h1>;
        }
        if (line.startsWith("## ")) {
          return <h2 key={i} className="text-base font-semibold mt-3 mb-1.5 text-text-primary">{line.slice(3)}</h2>;
        }
        if (line.startsWith("### ")) {
          return <h3 key={i} className="text-sm font-semibold mt-2 mb-1 text-text-primary">{line.slice(4)}</h3>;
        }
        if (line.startsWith("- ")) {
          return <li key={i} className="ml-4 list-disc text-text-primary text-sm leading-relaxed">{renderInline(line.slice(2))}</li>;
        }
        if (/^\d+\.\s/.test(line)) {
          return <li key={i} className="ml-4 list-decimal text-text-primary text-sm leading-relaxed">{renderInline(line.replace(/^\d+\.\s/, ""))}</li>;
        }
        if (line.startsWith("> ")) {
          return <blockquote key={i} className="border-l-2 border-accent-primary pl-3 text-text-secondary text-sm italic my-2">{line.slice(2)}</blockquote>;
        }
        if (line.trim() === "") return <br key={i} />;
        return <p key={i} className="text-text-primary text-sm leading-relaxed">{renderInline(line)}</p>;
      })}
    </div>
  );
}

function renderInline(s: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={key++} className="bg-bg-elevated px-1 rounded text-accent-cyan text-xs">{tok.slice(1, -1)}</code>);
    else parts.push(<em key={key++}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}

function formatDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h${m}m`;
  return `${m}m`;
}
