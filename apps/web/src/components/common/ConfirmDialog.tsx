// ConfirmDialog — V0.8.0 替代 window.confirm
// 用法:
//   const [open, setOpen] = useState(false);
//   <ConfirmDialog
//     open={open}
//     title="确定删除?"
//     message="删除后无法恢复"
//     variant="danger"
//     onConfirm={() => { setOpen(false); doDelete(); }}
//     onCancel={() => setOpen(false)}
//   />
import { AlertTriangle, Info, X } from "lucide-react";
import { useEffect } from "react";
import clsx from "clsx";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string | React.ReactNode;
  variant?: "default" | "danger";
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  variant = "default",
  confirmText = "确定",
  cancelText = "取消",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const Icon = variant === "danger" ? AlertTriangle : Info;
  const iconClass = variant === "danger" ? "text-red-600 bg-red-100" : "text-sky-600 bg-sky-100";
  const btnClass = variant === "danger" ? "btn-danger" : "btn-primary";

  return (
    <div
      className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-border max-w-md w-[90%] p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start gap-4">
          <div className={clsx("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0", iconClass)}>
            <Icon size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-text-primary mb-1.5">{title}</h3>
            <div className="text-sm text-text-secondary whitespace-pre-line">{message}</div>
          </div>
          <button
            onClick={onCancel}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated flex-shrink-0"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex items-center justify-end gap-2 mt-5">
          <button onClick={onCancel} className="btn-ghost">
            {cancelText}
          </button>
          <button onClick={onConfirm} className={btnClass}>
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
