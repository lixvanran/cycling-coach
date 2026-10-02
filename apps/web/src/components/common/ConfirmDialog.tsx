// ConfirmDialog — V0.8.0 替代 window.confirm
// V0.8.2 UX-2: 加 useConfirm hook 让用法更顺
// 用法 1 (传统):
//   const [open, setOpen] = useState(false);
//   <ConfirmDialog open={open} title="..." onConfirm={...} onCancel={...} />
//
// 用法 2 (hook, 推荐):
//   const confirm = useConfirm();
//   if (await confirm({ title, message, variant: "danger" })) { doDelete(); }
import { AlertTriangle, Info, X } from "lucide-react";
import { useEffect, useState, useCallback, createContext, useContext } from "react";
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

// ===== useConfirm hook (V0.8.2 新增) =====
export interface ConfirmOptions {
  title: string;
  message: string | React.ReactNode;
  variant?: "default" | "danger";
  confirmText?: string;
  cancelText?: string;
}

interface ConfirmState extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm(): (opts: ConfirmOptions) => Promise<boolean> {
  const ctx = useContext(ConfirmContext);
  if (ctx) return ctx.confirm;
  // 没 Provider 时退化到 window.confirm (兜底, 不应走到)
  return (opts) => Promise.resolve(window.confirm(`${opts.title}\n${opts.message}`));
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({ ...opts, resolve });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state?.resolve(true);
    setState(null);
  }, [state]);

  const handleCancel = useCallback(() => {
    state?.resolve(false);
    setState(null);
  }, [state]);

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <ConfirmDialog
          open={true}
          title={state.title}
          message={state.message}
          variant={state.variant}
          confirmText={state.confirmText}
          cancelText={state.cancelText}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </ConfirmContext.Provider>
  );
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
  const iconClass = variant === "danger" ? "text-accent-danger bg-status-danger" : "text-accent-primary bg-status-info";
  const btnClass = variant === "danger" ? "btn-danger" : "btn-primary";

  return (
    <div
      className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded shadow-sm border border-border max-w-md w-[90%] p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start gap-4">
          <div className={clsx("w-10 h-10 rounded flex items-center justify-center flex-shrink-0", iconClass)}>
            <Icon size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-text-primary mb-1.5">{title}</h3>
            <div className="text-sm text-text-secondary whitespace-pre-line">{message}</div>
          </div>
          <button
            onClick={onCancel}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-subtle flex-shrink-0"
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
