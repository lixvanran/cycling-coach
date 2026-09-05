// Card — V0.8.0 统一卡片组件
// 替换 26 个组件里重复的 "border rounded-lg shadow p-4" 模式
// 用法:
//   <Card>内容</Card>
//   <Card hoverable>可悬浮</Card>
//   <Card padding="none">无内边距 (自己管)</Card>
import clsx from "clsx";
import type { ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  className?: string;
  /** 是否可悬浮 (有 hover 阴影) */
  hoverable?: boolean;
  /** 内边距档位 */
  padding?: "none" | "sm" | "md" | "lg";
  /** 点击事件 */
  onClick?: () => void;
}

const PAD: Record<NonNullable<CardProps["padding"]>, string> = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
};

export function Card({
  children,
  className,
  hoverable = false,
  padding = "md",
  onClick,
}: CardProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        "bg-white/80 backdrop-blur-glass border border-border rounded-xl shadow-panel",
        hoverable && "transition-all hover:shadow-elevated cursor-pointer",
        PAD[padding],
        onClick && "cursor-pointer",
        className
      )}
    >
      {children}
    </div>
  );
}

/**
 * CardHeader — 卡片头部 (panel-header 的 Card 版本)
 */
export function CardHeader({
  children,
  className,
  action,
}: {
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <div
      className={clsx(
        "px-5 py-3.5 border-b border-border flex items-center justify-between",
        className
      )}
    >
      <div className="flex-1 min-w-0">{children}</div>
      {action && <div className="flex-shrink-0 ml-3">{action}</div>}
    </div>
  );
}
