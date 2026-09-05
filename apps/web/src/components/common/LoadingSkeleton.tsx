// LoadingSkeleton — V0.8.0 骨架屏
// 复用 ActivityDetailSkeleton 的模式, 提供通用 form
// 用法:
//   <LoadingSkeleton rows={4} />
//   <LoadingSkeleton variant="card" />
//   <LoadingSkeleton variant="detail" />  // 还原 ActivityDetail 布局
import clsx from "clsx";

export interface LoadingSkeletonProps {
  /** 行数 (rows 模式) */
  rows?: number;
  /** 预设形态 */
  variant?: "rows" | "card" | "detail" | "list";
  className?: string;
}

export function LoadingSkeleton({
  rows = 3,
  variant = "rows",
  className,
}: LoadingSkeletonProps) {
  if (variant === "detail") {
    return (
      <div className={clsx("p-6 space-y-4 animate-pulse", className)}>
        <div className="h-7 bg-bg-elevated rounded w-1/3" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 bg-bg-elevated rounded" />
          ))}
        </div>
        <div className="h-64 bg-bg-elevated rounded" />
        <div className="grid grid-cols-2 gap-3">
          <div className="h-40 bg-bg-elevated rounded" />
          <div className="h-40 bg-bg-elevated rounded" />
        </div>
      </div>
    );
  }
  if (variant === "card") {
    return (
      <div className={clsx("p-6 animate-pulse", className)}>
        <div className="h-32 bg-bg-elevated rounded-xl" />
      </div>
    );
  }
  if (variant === "list") {
    return (
      <div className={clsx("p-6 space-y-3 animate-pulse", className)}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="h-12 bg-bg-elevated rounded" />
        ))}
      </div>
    );
  }
  // rows (默认)
  return (
    <div className={clsx("p-6 space-y-3 animate-pulse", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-bg-elevated rounded"
          style={{ width: `${100 - i * 8}%` }}
        />
      ))}
    </div>
  );
}
