// ErrorBoundary — V0.8.0 统一错误边界
// 包裹关键页面, 防止一个组件挂掉整页白屏
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** 错误时是否显示技术细节 (开发模式默认 true) */
  showDetails?: boolean;
  /** 错误时是否 reset 到根路由 */
  resetOnError?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ error, errorInfo: info });
    // V0.8.0: 实际生产可接 Sentry / LogRocket
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info);
  }

  reset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      const showDetails = this.props.showDetails ?? (typeof import.meta !== "undefined" && (import.meta as any).env?.DEV) ?? false;
      return (
        <div className="h-full flex items-center justify-center p-6">
          <div className="max-w-lg w-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-red-100 mx-auto mb-4 flex items-center justify-center">
              <AlertTriangle size={28} className="text-red-600" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary mb-2">
              页面出错了
            </h2>
            <p className="text-sm text-text-muted mb-4">
              组件渲染时遇到问题, 已经隔离, 其他页面不受影响。
            </p>
            {showDetails && this.state.error && (
              <pre className="text-left text-[11px] text-text-muted bg-bg-elevated rounded-lg p-3 mb-4 overflow-auto max-h-40 font-mono">
                {this.state.error.message}
                {this.state.errorInfo?.componentStack?.slice(0, 600)}
              </pre>
            )}
            <button onClick={this.reset} className="btn-primary">
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
