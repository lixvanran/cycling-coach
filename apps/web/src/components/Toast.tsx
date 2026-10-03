// V0.7.5.4 UX-3: 全局 Toast 替换 alert
// V0.8.2 UX-25: 加 action 字段支持 undo
// V0.8.3.1 P1: 砍 backdrop-blur (B3 视觉换皮"严肃克制"风格; backdrop-blur 是"AI 玻璃味")
// 用法: const toast = useToast();
//       toast.success("保存成功")
//       toast.error("失败")
//       toast.show("info", "已删除", { action: { label: "撤销", onClick: () => restore() } })
import { useEffect, useState, useCallback } from "react";
import { CheckCircle2, XCircle, AlertCircle, Info, X } from "lucide-react";
import clsx from "clsx";

export type ToastKind = "success" | "error" | "warn" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  ttl?: number;
  action?: ToastAction;
}

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  ttl: number; // ms
  action?: ToastAction;
}

let _id = 0;
let _listeners: Array<(items: ToastItem[]) => void> = [];
let _items: ToastItem[] = [];

function emit() {
  _listeners.forEach((fn) => fn(_items));
}

function push(kind: ToastKind, message: string, opts: ToastOptions = {}) {
  const { ttl = 3500, action } = opts;
  // 有 action 时延长 ttl, 给用户时间点
  const effectiveTtl = action ? Math.max(ttl, 6000) : ttl;
  const item: ToastItem = { id: ++_id, kind, message, ttl: effectiveTtl, action };
  _items = [..._items, item];
  emit();
  setTimeout(() => {
    _items = _items.filter((x) => x.id !== item.id);
    emit();
  }, effectiveTtl);
}

export const toast = {
  success: (msg: string, opts?: ToastOptions) => push("success", msg, opts),
  error: (msg: string, opts?: ToastOptions) => push("error", msg, opts),
  warn: (msg: string, opts?: ToastOptions) => push("warn", msg, opts),
  info: (msg: string, opts?: ToastOptions) => push("info", msg, opts),
};

export function useToast() {
  return toast;
}

const ICONS: Record<ToastKind, any> = {
  success: CheckCircle2,
  error: XCircle,
  warn: AlertCircle,
  info: Info,
};

const COLORS: Record<ToastKind, string> = {
  success: "bg-status-success/95 text-white border-accent-success",
  error: "bg-accent-danger/95 text-white border-accent-danger",
  warn: "bg-status-warning text-white border-accent-warning",
  info: "bg-status-info text-white border-accent-primary",
};

function dismiss(id: number) {
  _items = _items.filter((x) => x.id !== id);
  emit();
}

export function ToastContainer() {
  const [items, setItems] = useState<ToastItem[]>(_items);
  useEffect(() => {
    const fn = (next: ToastItem[]) => setItems(next);
    _listeners.push(fn);
    return () => {
      _listeners = _listeners.filter((x) => x !== fn);
    };
  }, []);
  if (items.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-[9999] space-y-2 pointer-events-none">
      {items.map((item) => {
        const Icon = ICONS[item.kind];
        return (
          <div
            key={item.id}
            className={clsx(
              "pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded shadow-sm border min-w-[260px] max-w-[480px]",
              COLORS[item.kind]
            )}
            role="status"
          >
            <Icon size={16} className="flex-shrink-0" />
            <div className="text-sm font-medium flex-1 whitespace-pre-line break-words">{item.message}</div>
            {item.action && (
              <button
                onClick={() => {
                  item.action!.onClick();
                  dismiss(item.id);
                }}
                className="px-2 py-0.5 rounded text-sm font-semibold underline-offset-2 hover:underline whitespace-nowrap"
              >
                {item.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(item.id)}
              className="opacity-70 hover:opacity-100"
              aria-label="关闭"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
