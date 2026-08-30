// 聊天页 — 模仿 Z 项目 ChatPage 风格(简洁对话 + 流式响应)
import { useEffect, useRef, useState } from "react";
import { Send, StopCircle, Trash2, MessageCircle, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import { ChatMessage } from "../components/ChatMessage";

const SUGGESTIONS = [
  "我的 NP 最近 3 个月下降了 10W,可能是为什么?",
  "本周累计 TSS 500 是不是太高了?",
  "周末比赛,赛前 3 天该怎么调整?",
  "FTP 怎么测才比较准?",
];

export function ChatPage() {
  const messages = useAppStore((s) => s.chatMessages);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const addMsg = useAppStore((s) => s.addChatMessage);
  const updateLast = useAppStore((s) => s.updateLastAssistant);
  const clearChat = useAppStore((s) => s.clearChat);
  const setStreaming = useAppStore((s) => s.setStreaming);

  const [input, setInput] = useState("");
  const [sources, setSources] = useState<Array<{title: string; path: string; snippet: string}> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 滚到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || isStreaming) return;

    // 1) 加用户消息
    const userMsg = {
      id: `u-${Date.now()}`,
      role: "user" as const,
      content,
      timestamp: Date.now(),
    };
    addMsg(userMsg);

    // 2) 加空的 assistant 消息(用于流式填充)
    const assistantId = `a-${Date.now()}`;
    addMsg({
      id: assistantId,
      role: "assistant" as const,
      content: "",
      thinking: "",
      timestamp: Date.now(),
    });

    // 3) 准备请求
    setInput("");
    setStreaming(true);
    setSources(null);

    const history = [...messages, userMsg]
      .filter((m) => m.role !== "assistant" || m.content) // 跳过空的 assistant
      .map((m) => ({ role: m.role, content: m.content }));

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let fullText = "";
    let fullThink = "";
    try {
      for await (const evt of api.chatStream(
        history.slice(0, -1), // 历史不包含当前用户消息
        content,
        ctrl.signal
      )) {
        if (evt.type === "text") {
          // 区分 [THINK]xxx[/THINK] 和普通文本
          const chunk = evt.data;
          let i = 0;
          while (i < chunk.length) {
            const thinkStart = chunk.indexOf("[THINK]", i);
            if (thinkStart === -1) {
              // 剩余全是普通文本
              fullText += chunk.slice(i);
              i = chunk.length;
              updateLast({ content: fullText, thinking: fullThink });
            } else {
              // THINK 开始
              if (thinkStart > i) {
                fullText += chunk.slice(i, thinkStart);
              }
              const thinkEnd = chunk.indexOf("[/THINK]", thinkStart);
              if (thinkEnd === -1) {
                // THINK 没结束(可能跨 chunk)— 暂存
                fullText += chunk.slice(i);
                i = chunk.length;
                updateLast({ content: fullText, thinking: fullThink });
                break;
              }
              fullThink += chunk.slice(thinkStart + 7, thinkEnd);
              i = thinkEnd + 8;
              updateLast({ content: fullText, thinking: fullThink });
            }
          }
        } else if (evt.type === "error") {
          updateLast({ error: evt.data, content: fullText || "(生成失败)" });
          break;
        } else if (evt.type === "sources") {
          // V0.5: RAG 引用源
          setSources(evt.data as Array<{title: string; path: string; snippet: string}>);
        } else if (evt.type === "done") {
          // 流结束
          break;
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        updateLast({ error: e?.message || "未知错误", content: "" });
      } else {
        // 用户主动停止
        updateLast({ content: fullText || "(已停止)" });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const onStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const onClear = () => {
    if (confirm("清空所有对话?这不会影响训练数据。")) {
      onStop();
      clearChat();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Sparkles size={16} className="text-accent-primary" />
            AI 教练对话
          </h1>
          <p className="text-xs text-text-muted mt-0.5">
            数据说话,不灌鸡汤 · Powered by minimax M3
          </p>
        </div>
        <button
          onClick={onClear}
          disabled={messages.length === 0}
          className="btn-ghost text-xs"
          title="清空对话"
        >
          <Trash2 size={12} />
          清空
        </button>
      </div>

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-accent-primary/10 flex items-center justify-center mb-4">
              <MessageCircle size={28} className="text-accent-primary" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary mb-2">
              开始和你的 AI 教练对话
            </h2>
            <p className="text-sm text-text-muted mb-6">
              可以问训练相关问题,也可以描述场景让教练分析。
              任何时候按 <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs">Ctrl+K</kbd> 清空。
            </p>
            <div className="grid grid-cols-2 gap-2 w-full">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={isStreaming}
                  className="panel p-3 text-left text-sm text-text-secondary hover:text-text-primary hover:border-accent-primary transition-colors disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <ChatMessage key={m.id} msg={m} />
            ))}
            {/* V0.5: RAG 引用源 */}
            {sources && sources.length > 0 && (
              <div className="mt-4 panel p-3 bg-accent-primary/5 border-accent-primary/20">
                <div className="text-xs font-semibold text-accent-primary mb-2 flex items-center gap-1.5">
                  <Sparkles size={12} /> 知识库参考 · {sources.length} 条 (来源: 潘震(公路车教练))
                </div>
                <div className="space-y-2">
                  {sources.map((s, i) => (
                    <details key={i} className="text-xs">
                      <summary className="cursor-pointer text-text-secondary hover:text-text-primary">
                        {i + 1}. {s.title}
                        <span className="text-text-muted ml-2 text-[10px]">— {s.path}</span>
                      </summary>
                      <div className="mt-1 p-2 bg-bg-base rounded text-text-muted text-[11px] leading-relaxed">
                        {s.snippet}
                      </div>
                    </details>
                  ))}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* 输入区 */}
      <form
        onSubmit={onSubmit}
        className="border-t border-border bg-bg-base/95 backdrop-blur px-6 py-3"
      >
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="问教练一个问题…(Enter 发送,Shift+Enter 换行)"
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-bg-input border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-primary resize-none max-h-32 disabled:opacity-50"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="btn-ghost border border-accent-danger text-accent-danger hover:bg-accent-danger/10"
            >
              <StopCircle size={14} />
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="btn-primary"
            >
              <Send size={14} />
              发送
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
