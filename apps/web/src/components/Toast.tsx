// V0.7.5.4 UX-3: 全局 Toast 替换 alert
// 用法: const toast = useToast(); toast.success("保存成功"); toast.error("失败")
import { useEffect, useState, useCallback } from "react";
import { CheckCircle2, XCircle, AlertCircle, Info, X } from "lucide-react";
import clsx from "clsx";

export type ToastKind = "success" | "error" | "warn" | "info";
export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  ttl: number; // ms
}

let _id = 0;
let _listeners: Array<(items: ToastItem[]) => void> = [];
let _items: ToastItem[] = [];

function emit() {
  _listeners.forEach((fn) => fn(_items));
}

function push(kind: ToastKind, message: string, ttl = 3500) {
  const item: ToastItem = { id: ++_id, kind, message, ttl };
  _items = [..._items, item];
  emit();
  setTimeout(() => {
    _items = _items.filter((x) => x.id !== item.id);
    emit();
  }, ttl);
}

export const toast = {
  success: (msg: string, ttl?: number) => push("success", msg, ttl),
  error: (msg: string, ttl?: number) => push("error", msg, ttl),
  warn: (msg: string, ttl?: number) => push("warn", msg, ttl),
  info: (msg: string, ttl?: number) => push("info", msg, ttl),
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
  success: "bg-emerald-500/95 text-white border-emerald-600",
  error: "bg-red-500/95 text-white border-red-600",
  warn: "bg-amber-500/95 text-white border-amber-600",
  info: "bg-sky-500/95 text-white border-sky-600",
};

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
              "pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg border min-w-[260px] max-w-[480px] backdrop-blur",
              COLORS[item.kind]
            )}
            role="status"
          >
            <Icon size={16} className="flex-shrink-0" />
            <div className="text-sm font-medium flex-1 whitespace-pre-line break-words">{item.message}</div>
            <button
              onClick={() => {
                _items = _items.filter((x) => x.id !== item.id);
                emit();
              }}
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
