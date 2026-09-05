// EmptyState — V0.8.0 统一空状态
// 替换 Dashboard / KB / 各种 "无数据" 重复块
import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import clsx from "clsx";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  cta?: ReactNode;             // 主 CTA 按钮
  secondary?: ReactNode;        // 次按钮
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  cta,
  secondary,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={clsx(
        "h-full flex flex-col items-center justify-center text-center p-6",
        className
      )}
    >
      <div className="w-16 h-16 rounded-2xl bg-bg-elevated mx-auto mb-4 flex items-center justify-center text-text-muted">
        {icon ?? <Inbox size={28} />}
      </div>
      <h2 className="text-lg font-semibold text-text-primary mb-2">{title}</h2>
      {description && (
        <p className="text-sm text-text-muted mb-6 max-w-md">{description}</p>
      )}
      {(cta || secondary) && (
        <div className="flex items-center gap-3">
          {cta}
          {secondary}
        </div>
      )}
    </div>
  );
}
