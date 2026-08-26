// 单条消息气泡(模仿 Z 项目 ChatPage 风格)
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Brain, User } from "lucide-react";
import { useState } from "react";
import type { ChatMsg } from "../store/useAppStore";
import clsx from "clsx";

interface Props {
  msg: ChatMsg;
}

export function ChatMessage({ msg }: Props) {
  const [showThinking, setShowThinking] = useState(false);
  const isUser = msg.role === "user";

  return (
    <div className={clsx("flex gap-3 mb-4", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-accent-primary/20 flex items-center justify-center flex-shrink-0">
          <Brain size={16} className="text-accent-primary" />
        </div>
      )}
      <div className={clsx("flex flex-col max-w-[80%]", isUser ? "items-end" : "items-start")}>
        {/* 思考过程(可折叠) */}
        {!isUser && msg.thinking && (
          <button
            onClick={() => setShowThinking(!showThinking)}
            className="text-xs text-text-muted hover:text-text-secondary mb-1.5 flex items-center gap-1 px-2 py-0.5 rounded hover:bg-bg-elevated"
          >
            <Brain size={11} />
            {showThinking ? "隐藏思考" : `思考过程(${msg.thinking.length}字)`}
          </button>
        )}
        {!isUser && showThinking && msg.thinking && (
          <div className="text-xs text-text-muted bg-bg-base border border-border rounded-lg p-3 mb-1.5 max-w-full italic leading-relaxed">
            {msg.thinking}
          </div>
        )}
        {/* 主内容 */}
        {isUser ? (
          <div
            className="px-4 py-2.5 rounded-2xl rounded-tr-sm text-white text-sm leading-relaxed whitespace-pre-wrap shadow-sm"
            style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)" }}
          >
            {msg.content}
          </div>
        ) : (
          <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white/90 backdrop-blur border border-border text-text-primary text-sm leading-relaxed prose prose-sm max-w-none shadow-sm">
            {msg.content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
            ) : msg.error ? (
              <span className="text-accent-danger">⚠ {msg.error}</span>
            ) : (
              <span className="text-text-muted">思考中…</span>
            )}
          </div>
        )}
        {/* 时间戳 */}
        <div className="text-[10px] text-text-muted mt-1 px-1">
          {new Date(msg.timestamp).toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-bg-elevated flex items-center justify-center flex-shrink-0">
          <User size={16} className="text-text-secondary" />
        </div>
      )}
    </div>
  );
}
