// 指标卡 — TrainingPeaks 风格
import clsx from "clsx";
import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  unit?: string;
  trend?: "up" | "down" | "flat";
  hint?: string;
  size?: "sm" | "md" | "lg";
  accent?: "default" | "primary" | "success" | "warning" | "danger";
}

export function MetricCard({
  label,
  value,
  unit,
  hint,
  size = "md",
  accent = "default",
}: MetricCardProps) {
  const sizeClasses = {
    sm: "p-3",
    md: "p-4",
    lg: "p-5",
  };
  const valueClasses = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-3xl",
  };
  const accentClass = {
    default: "text-text-primary",
    primary: "text-accent-primary",
    success: "text-accent-success",
    warning: "text-accent-warning",
    danger: "text-accent-danger",
  }[accent];

  return (
    <div className={clsx("metric-card", sizeClasses[size])}>
      <div className="metric-label">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <div className={clsx("font-mono font-semibold", valueClasses[size], accentClass)}>
          {value ?? "—"}
        </div>
        {unit && <div className="text-xs text-text-muted">{unit}</div>}
      </div>
      {hint && <div className="mt-1 text-xs text-text-muted">{hint}</div>}
    </div>
  );
}
