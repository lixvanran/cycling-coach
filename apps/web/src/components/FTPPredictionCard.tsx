// FTPPredictionCard — V0.8.0 Dashboard 顶部 FTP 预测卡
// 调用 POST /api/ml/predict/ftp 拿数据
// 显示: 大数字 + 区间条 (P10/P50/P90) + 置信度 + 操作按钮

import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { TrendingUp, TrendingDown, RefreshCw, Activity, AlertCircle, ChevronRight, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import type { FTPPredictionResponse } from "../lib/types";
import clsx from "clsx";

interface Props {
  athleteId?: number;
  className?: string;
}

const CONFIDENCE_LABEL: Record<string, { label: string; color: string; bg: string }> = {
  high: { label: "高", color: "text-emerald-700", bg: "bg-emerald-50 border-emerald-200" },
  medium: { label: "中", color: "text-amber-700", bg: "bg-amber-50 border-amber-200" },
  low: { label: "低", color: "text-rose-700", bg: "bg-rose-50 border-rose-200" },
};

export function FTPPredictionCard({ athleteId: _athleteId, className }: Props) {
  const navigate = useNavigate();
  const [data, setData] = useState<FTPPredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modelRegistered, setModelRegistered] = useState(true);
  const [retryKey, setRetryKey] = useState(0);

  const fetchPrediction = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.predictFtp();
      setData(res);
    } catch (e: any) {
      const msg = e?.message || "预测失败";
      setError(msg);
      // 检测模型未注册
      if (msg.includes("未注册") || msg.includes("not registered") || msg.includes("ModelNotFound")) {
        setModelRegistered(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPrediction();
  }, [fetchPrediction, retryKey]);

  // 加载 skeleton
  if (loading) {
    return (
      <div className={clsx("panel p-5", className)}>
        <div className="flex items-center justify-between mb-3">
          <div className="h-4 w-24 bg-bg-input rounded animate-pulse" />
          <div className="h-3 w-12 bg-bg-input rounded animate-pulse" />
        </div>
        <div className="h-12 w-40 bg-bg-input rounded animate-pulse mb-2" />
        <div className="h-6 w-32 bg-bg-input rounded animate-pulse mb-3" />
        <div className="h-8 w-full bg-bg-input rounded animate-pulse" />
      </div>
    );
  }

  // 错误态(模型未注册等)
  if (error) {
    return (
      <div className={clsx("panel p-5 border-l-4 border-l-rose-400 bg-rose-50/30", className)}>
        <div className="flex items-start gap-2.5">
          <AlertCircle className="w-5 h-5 text-rose-500 mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-rose-700">模型未注册</div>
            <div className="text-xs text-text-secondary mt-1 leading-relaxed">
              ftp-predictor 模型尚未注册到 MLModelMeta。{!modelRegistered && "请前往 "}
              {!modelRegistered && (
                <button
                  onClick={() => navigate("/settings")}
                  className="text-accent-primary underline hover:no-underline"
                >
                  个人设置
                </button>
              )}
              {!modelRegistered && " 或运行 bin/sync_ftp_model.sh 完成注册。"}
            </div>
            {error && !modelRegistered && (
              <div className="text-[10px] text-text-muted mt-1.5 font-mono break-all">{error}</div>
            )}
            <button
              onClick={() => setRetryKey((k) => k + 1)}
              className="btn-ghost text-xs mt-2"
            >
              <RefreshCw className="w-3 h-3" />
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const conf = CONFIDENCE_LABEL[data.confidence] || CONFIDENCE_LABEL.low;
  const isPositive = (data.delta ?? 0) >= 0;

  return (
    <div className={clsx("panel p-5 relative overflow-hidden", className)}>
      {/* 顶饰 — 渐变条 */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-accent-primary via-accent-cyan to-accent-primary opacity-60" />

      {/* 标题行 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Activity className="w-4 h-4 text-accent-primary" />
          <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide">
            预测 FTP
          </h3>
          <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-medium border", conf.color, conf.bg)}>
            置信度 {conf.label}
          </span>
        </div>
        <span className="text-[10px] text-text-muted font-mono">
          {data.data_window}
        </span>
      </div>

      {/* 大数字 + Delta */}
      <div className="flex items-baseline gap-3 mb-3">
        <div className="text-5xl font-bold font-mono text-text-primary tabular-nums leading-none">
          {Math.round(data.predicted_ftp)}
          <span className="text-xl text-text-secondary ml-1">W</span>
        </div>
        {data.delta !== null && data.delta !== undefined && (
          <div className={clsx(
            "flex items-center gap-1 text-sm font-semibold font-mono",
            isPositive ? "text-emerald-600" : "text-rose-600",
          )}>
            {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            {isPositive ? "+" : ""}{data.delta} W
            <span className="text-[10px] text-text-muted font-normal">
              vs 档案 {data.current_ftp}W
            </span>
          </div>
        )}
      </div>

      {/* 区间条 (SVG) */}
      <FTPIntervalBar
        lower={data.lower_80}
        point={data.predicted_ftp}
        upper={data.upper_80}
        current={data.current_ftp ?? 0}
      />

      {/* 数字标注 */}
      <div className="flex items-center justify-between mt-1.5 text-[10px] text-text-muted font-mono">
        <span>P10: {Math.round(data.lower_80)}W</span>
        <span className="text-accent-primary font-semibold">点估: {Math.round(data.predicted_ftp)}W</span>
        <span>P90: {Math.round(data.upper_80)}W</span>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-border/60">
        <div className="text-[10px] text-text-muted leading-relaxed">
          <div>模型: <span className="font-mono">{data.model_name}@{data.model_version}</span></div>
          <div>推理耗时: {data.inference_ms}ms · {data.model_format}</div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => navigate("/training/trends")}
            className="text-[11px] px-2.5 py-1.5 rounded border border-border hover:border-accent-primary hover:text-accent-primary transition-colors flex items-center gap-1"
          >
            <Sparkles className="w-3 h-3" />
            查看趋势
            <ChevronRight className="w-3 h-3" />
          </button>
          <button
            onClick={() => setRetryKey((k) => k + 1)}
            className="text-[11px] px-2.5 py-1.5 rounded bg-accent-primary text-white hover:bg-accent-primary-hover transition-colors flex items-center gap-1"
            title="重新预测"
          >
            <RefreshCw className="w-3 h-3" />
            重新预测
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 区间条 — SVG 自画
// ============================================================

function FTPIntervalBar({
  lower,
  point,
  upper,
  current,
}: {
  lower: number;
  point: number;
  upper: number;
  current: number;
}) {
  // 范围: 包含 lower/upper/current
  const min = Math.min(lower, current) - 10;
  const max = Math.max(upper, current) + 10;
  const range = max - min;

  // 归一化坐标
  const toX = (v: number) => ((v - min) / range) * 100;
  const lowerPct = toX(lower);
  const upperPct = toX(upper);
  const pointPct = toX(point);
  const currentPct = toX(current);

  return (
    <div className="mt-2 px-1">
      <div className="relative h-7">
        <svg
          viewBox="0 0 100 28"
          preserveAspectRatio="none"
          className="w-full h-full"
        >
          {/* 底色 — 全宽浅灰 */}
          <rect x={0} y={11} width={100} height={6} rx={3} fill="rgb(241 245 249)" />

          {/* 区间条 — 绿色 */}
          <rect
            x={lowerPct}
            y={9}
            width={Math.max(0, upperPct - lowerPct)}
            height={10}
            rx={2}
            fill="rgb(16 185 100)"
            fillOpacity={0.35}
            stroke="rgb(16 185 100)"
            strokeOpacity={0.5}
            strokeWidth={0.5}
          />

          {/* 当前档案 — 灰色虚线 */}
          {current > 0 && (
            <>
              <line
                x1={currentPct}
                x2={currentPct}
                y1={3}
                y2={25}
                stroke="rgb(100 116 139)"
                strokeWidth={1.2}
                strokeDasharray="2 2"
              />
              <text
                x={currentPct}
                y={1.5}
                textAnchor="middle"
                fontSize="3.5"
                fill="rgb(100 116 139)"
                className="font-mono"
              >
                当前
              </text>
            </>
          )}

          {/* 点估 — 蓝色实心圆 + 标签 */}
          <circle
            cx={pointPct}
            cy={14}
            r={3.5}
            fill="rgb(79 70 229)"
            stroke="white"
            strokeWidth={1.5}
          />
          <text
            x={pointPct}
            y={27}
            textAnchor="middle"
            fontSize="3.8"
            fontWeight="600"
            fill="rgb(79 70 229)"
            className="font-mono"
          >
            {Math.round(point)}W
          </text>
        </svg>
      </div>
    </div>
  );
}
