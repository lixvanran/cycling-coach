// 聊天页 — V0.8.0 3 tab 模式: 训练答疑 (rag) | 战术规划 (workflow) | 随便聊聊 (chat)
import { useEffect, useRef, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Send, StopCircle, Trash2, Sparkles, Brain, MessageSquare, ChevronDown, ChevronUp, GitBranch, Zap } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import { ChatMessage } from "../components/ChatMessage";
import { ThinkingTreeView, makeNode } from "../components/ThinkingTreeView";
import { useChatStore, type ChatMode } from "../store/chat";
import type { ChatMsg } from "../store/useAppStore";
import type { ThinkingNode } from "../lib/types";

// ============================================================
// 3 个 tab 定义
// ============================================================

interface TabDef {
  mode: ChatMode;
  label: string;
  icon: any;
  description: string;
  suggestions: string[];
  color: string;
}

const TABS: TabDef[] = [
  {
    mode: "rag",
    label: "训练答疑",
    icon: Sparkles,
    description: "RAG 知识库 + 你的训练数据",
    color: "text-accent-primary",
    suggestions: [
      "我的 NP 最近 3 个月下降了 10W,可能是为什么?",
      "本周累计 TSS 500 是不是太高了?",
      "FTP 怎么测才比较准?",
      "减量周怎么安排比较合理?",
    ],
  },
  {
    mode: "workflow",
    label: "战术规划",
    icon: GitBranch,
    description: "multi-mind 9 stage 思维扩散",
    color: "text-amber-600",
    suggestions: [
      "周末 100km 公路赛,配速怎么安排?",
      "FTP 220W 备战 60km 山地赛,赛前 4 周怎么练?",
      "周中 3 小时有氧 + 周末比赛,补给策略?",
      "和队友配合的双人计时赛,如何分配功率?",
    ],
  },
  {
    mode: "chat",
    label: "随便聊聊",
    icon: MessageSquare,
    description: "纯 LLM 简洁回答,不读 KB",
    color: "text-cyan-700",
    suggestions: [
      "今天有点累,要不要训练?",
      "给我讲个骑行的冷知识",
      "推荐一本公路车训练的书",
      "我最近心情不错,能聊聊吗?",
    ],
  },
];

// ============================================================
// 主组件
// ============================================================

export function ChatPage() {
  const toast = useToast();
  const navigate = useNavigate();

  // V0.8.0: 直接用 useChatStore(V0.8.0 拆分的 chat store)
  const activeMode = useChatStore((s) => s.activeMode);
  const setActiveMode = useChatStore((s) => s.setActiveMode);
  const chatMessagesRag = useChatStore((s) => s.chatMessagesRag);
  const chatMessagesWorkflow = useChatStore((s) => s.chatMessagesWorkflow);
  const chatMessagesChat = useChatStore((s) => s.chatMessagesChat);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const updateLastMessage = useChatStore((s) => s.updateLastMessage);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const setStreaming = useChatStore((s) => s.setStreaming);

  // 根据 activeMode 选消息列表
  const messages = useMemo<ChatMsg[]>(() => {
    if (activeMode === "workflow") return chatMessagesWorkflow as unknown as ChatMsg[];
    if (activeMode === "chat") return chatMessagesChat as unknown as ChatMsg[];
    return chatMessagesRag as unknown as ChatMsg[];
  }, [activeMode, chatMessagesRag, chatMessagesWorkflow, chatMessagesChat]);

  const chatMode = activeMode;

  const [input, setInput] = useState("");
  const [sources, setSources] = useState<Array<{title: string; path: string; snippet: string}> | null>(null);
  const [thinkingNodes, setThinkingNodes] = useState<ThinkingNode[]>([]);
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 当前 tab
  const currentTab = TABS.find((t) => t.mode === chatMode) || TABS[0];

  // 切换 mode 时清空 sources + 思维树(避免跨 tab 残留)
  useEffect(() => {
    setSources(null);
    setThinkingNodes([]);
    setTreeCollapsed(false);
  }, [chatMode]);

  // 滚到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ============================================================
  // 发送
  // ============================================================
  const send = async (text: string) => {
    const content = text.trim();
    if (!content || isStreaming) return;

    // 1) 加用户消息
    const userMsg: ChatMsg = {
      id: `u-${Date.now()}`,
      role: "user",
      content,
      timestamp: Date.now(),
    };
    appendMessage(chatMode, userMsg as any);

    // 2) 加空的 assistant 消息(用于流式填充)
    const assistantId = `a-${Date.now()}`;
    appendMessage(chatMode, {
      id: assistantId,
      role: "assistant",
      content: "",
      thinking: "",
      timestamp: Date.now(),
    } as any);

    setInput("");
    setStreaming(true);
    setSources(null);
    setThinkingNodes([]);  // 重置思维树
    setTreeCollapsed(false);

    // 准备历史(从当前 mode 桶拿)
    const history = [...messages, userMsg]
      .filter((m) => m.role !== "assistant" || m.content) // 跳过空的 assistant
      .map((m) => ({ role: m.role, content: m.content }));

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let fullText = "";
    let fullThink = "";
    // workflow 模式下的思维树节点缓冲
    const nodeMap = new Map<string, ThinkingNode>();

    try {
      for await (const evt of api.chatStreamV2(chatMode, history.slice(0, -1), content, ctrl.signal)) {
        if (evt.type === "text") {
          // 区分 [THINK]xxx[/THINK] 和普通文本
          const chunk = evt.data;
          let i = 0;
          while (i < chunk.length) {
            const thinkStart = chunk.indexOf("[THINK]", i);
            if (thinkStart === -1) {
              fullText += chunk.slice(i);
              i = chunk.length;
              updateLastMessage(chatMode, { content: fullText, thinking: fullThink } as any);
            } else {
              if (thinkStart > i) {
                fullText += chunk.slice(i, thinkStart);
              }
              const thinkEnd = chunk.indexOf("[/THINK]", thinkStart);
              if (thinkEnd === -1) {
                fullText += chunk.slice(i);
                i = chunk.length;
                updateLastMessage(chatMode, { content: fullText, thinking: fullThink } as any);
                break;
              }
              fullThink += chunk.slice(thinkStart + 7, thinkEnd);
              i = thinkEnd + 8;
              updateLastMessage(chatMode, { content: fullText, thinking: fullThink } as any);
            }
          }
        } else if (evt.type === "node") {
          // workflow: 思维树节点事件
          const d = evt.data;
          if (!d || !d.id) continue;
          const existing = nodeMap.get(d.id);
          const stage = (d.stage || d.id || "").toString();
          // 推断 track
          let track: "shared" | "aggressive" | "conservative" = "shared";
          if (stage.includes("a") && stage.startsWith("executor")) track = "aggressive";
          else if (stage.includes("c") && stage.startsWith("executor")) track = "conservative";
          else if (d.track) track = d.track;

          const newNode: ThinkingNode = existing
            ? {
                ...existing,
                status: d.status || existing.status,
                content: d.content !== undefined ? d.content : existing.content,
                score: d.score !== undefined ? d.score : existing.score,
                started_at: d.started_at || existing.started_at,
                finished_at: d.finished_at || existing.finished_at,
                error: d.error || existing.error,
              }
            : makeNode({
                id: d.id,
                stage,
                parent_id: d.parent_id || null,
                status: d.status || "running",
                content: d.content,
                score: d.score,
                track,
              });
          // 首次见到 → 加 started_at
          if (!newNode.started_at) newNode.started_at = Date.now();
          if (d.status === "done" || d.status === "pruned") newNode.finished_at = Date.now();
          nodeMap.set(d.id, newNode);

          // 更新到 React state(思维树是 UI 状态, 不持久化到 message)
          setThinkingNodes(Array.from(nodeMap.values()));
        } else if (evt.type === "final") {
          // 最终建议帧
          if (typeof evt.data === "string") {
            fullText += evt.data;
          } else if (evt.data?.content) {
            fullText += evt.data.content;
          }
          updateLastMessage(chatMode, { content: fullText, thinking: fullThink } as any);
        } else if (evt.type === "error") {
          updateLastMessage(chatMode, { error: evt.data, content: fullText || "(生成失败)" } as any);
          break;
        } else if (evt.type === "sources") {
          setSources(evt.data as Array<{title: string; path: string; snippet: string}>);
        } else if (evt.type === "done") {
          break;
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        updateLastMessage(chatMode, { error: e?.message || "未知错误", content: "" } as any);
      } else {
        updateLastMessage(chatMode, { content: fullText || "(已停止)" } as any);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  // 30s 慢响应 + 120s 硬超时
  useEffect(() => {
    if (!isStreaming) return;
    const slowTimer = setTimeout(() => {
      toast.warn("AI 响应较慢 (已等 30s), 可点停止按钮取消", 5000);
    }, 30_000);
    const hardTimer = setTimeout(() => {
      abortRef.current?.abort();
      toast.error("AI 响应超时 (120s), 已自动取消", 5000);
    }, 120_000);
    return () => {
      clearTimeout(slowTimer);
      clearTimeout(hardTimer);
    };
  }, [isStreaming]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    send(input);
  };

  const onStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const onClear = () => {
    if (confirm(`清空"${currentTab.label}"模式的所有对话?`)) {
      onStop();
      clearMessages(chatMode);
    }
  };

  // ============================================================
  // 渲染
  // ============================================================
  return (
    <div className="flex flex-col h-full">
      {/* 顶部 — 标题 + tab + 清空 */}
      <div className="border-b border-border bg-bg-elevated/50 backdrop-blur">
        <div className="px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-text-primary flex items-center gap-2">
              <Brain size={16} className="text-accent-primary" />
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
            title="清空当前模式对话"
          >
            <Trash2 size={12} />
            清空
          </button>
        </div>

        {/* V0.8.0: 3 tab segmented control (iOS 风) */}
        <div className="px-6 pb-3">
          <SegmentedControl
            options={TABS.map((t) => ({
              value: t.mode,
              label: t.label,
              icon: t.icon,
            }))}
            value={chatMode}
            onChange={(v) => setActiveMode(v as ChatMode)}
          />
          {/* 当前 mode 描述 */}
          <div className="mt-2 text-[10px] text-text-muted flex items-center gap-1.5">
            <span className={clsx("w-1.5 h-1.5 rounded-full", currentTab.color.replace("text-", "bg-"))} />
            {currentTab.description}
            <span className="ml-auto text-text-muted">
              历史 {messages.length} 条
            </span>
          </div>
        </div>
      </div>

      {/* 主体 — workflow 模式: 思维树 + 消息, 其他模式: 全屏消息 */}
      {chatMode === "workflow" ? (
        <WorkflowLayout
          messages={messages}
          thinkingNodes={thinkingNodes}
          treeCollapsed={treeCollapsed}
          onToggleTree={() => setTreeCollapsed(!treeCollapsed)}
          sources={sources}
          messagesEndRef={messagesEndRef}
          currentTab={currentTab}
          isStreaming={isStreaming}
          onSuggestion={send}
          onNavigate={navigate}
        />
      ) : (
        <DefaultLayout
          messages={messages}
          sources={sources}
          messagesEndRef={messagesEndRef}
          currentTab={currentTab}
          isStreaming={isStreaming}
          onSuggestion={send}
        />
      )}

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
            placeholder={
              chatMode === "rag"
                ? "问训练相关问题…(Enter 发送,Shift+Enter 换行)"
                : chatMode === "workflow"
                ? "描述战术场景,multi-mind 会展开 9 stage 思维过程…"
                : "随便聊聊…"
            }
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

// ============================================================
// Segmented Control (iOS 风) — V0.8.0
// ============================================================

interface SegmentedOption<T> {
  value: T;
  label: string;
  icon?: any;
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="relative inline-flex bg-bg-input rounded-lg p-1 w-full">
      {/* 高亮背景(动) */}
      <div
        className="absolute top-1 bottom-1 rounded-md bg-white shadow-sm transition-all duration-200 ease-out"
        style={{
          width: `calc((100% - 8px) / ${options.length})`,
          left: `calc(4px + ${options.findIndex((o) => o.value === value)} * (100% - 8px) / ${options.length})`,
        }}
      />
      {options.map((opt) => {
        const isActive = opt.value === value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={clsx(
              "relative z-10 flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors duration-200",
              isActive
                ? "text-accent-primary"
                : "text-text-muted hover:text-text-secondary",
            )}
          >
            {Icon && <Icon size={13} className={isActive ? "text-accent-primary" : ""} />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ============================================================
// 默认布局 (rag / chat 模式)
// ============================================================

function DefaultLayout({
  messages,
  sources,
  messagesEndRef,
  currentTab,
  isStreaming,
  onSuggestion,
}: {
  messages: ChatMsg[];
  sources: Array<{title: string; path: string; snippet: string}> | null;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  currentTab: TabDef;
  isStreaming: boolean;
  onSuggestion: (s: string) => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto">
          <div className="w-16 h-16 rounded-2xl bg-accent-primary/10 flex items-center justify-center mb-4">
            <currentTab.icon size={28} className="text-accent-primary" />
          </div>
          <h2 className="text-lg font-semibold text-text-primary mb-2">
            {currentTab.label}
          </h2>
          <p className="text-sm text-text-muted mb-6">
            {currentTab.description}
          </p>
          <div className="grid grid-cols-2 gap-2 w-full">
            {currentTab.suggestions.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestion(s)}
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
          {sources && sources.length > 0 && (
            <div className="mt-4 panel p-3 bg-accent-primary/5 border-accent-primary/20">
              <div className="text-xs font-semibold text-accent-primary mb-2 flex items-center gap-1.5">
                <Sparkles size={12} /> 知识库参考 · {sources.length} 条
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
  );
}

// ============================================================
// Workflow 布局 — 思维树 + 消息
// ============================================================

function WorkflowLayout({
  messages,
  thinkingNodes,
  treeCollapsed,
  onToggleTree,
  sources,
  messagesEndRef,
  currentTab,
  isStreaming,
  onSuggestion,
  onNavigate,
}: {
  messages: ChatMsg[];
  thinkingNodes: ThinkingNode[];
  treeCollapsed: boolean;
  onToggleTree: () => void;
  sources: Array<{title: string; path: string; snippet: string}> | null;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  currentTab: TabDef;
  isStreaming: boolean;
  onSuggestion: (s: string) => void;
  onNavigate: (path: string) => void;
}) {
  // 思维树只在 streaming / 有节点时显示
  const showTree = thinkingNodes.length > 0 || isStreaming;

  // 找最后一条 assistant 用于展示最终建议
  const lastAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i];
    }
    return null;
  }, [messages]);

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* 思维树区(上半, 可折叠) */}
      {showTree && (
        <div
          className={clsx(
            "border-b border-border bg-white/50 transition-all duration-200 overflow-hidden",
            treeCollapsed ? "h-9" : "h-[42%] min-h-[280px]",
          )}
        >
          {/* 折叠条 */}
          <div className="h-9 px-4 flex items-center justify-between border-b border-border bg-bg-elevated/40">
            <div className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-xs font-semibold text-text-primary">思维树 (multi-mind)</span>
              <span className="text-[10px] text-text-muted font-mono">
                {thinkingNodes.filter((n) => n.status === "done").length}/
                {thinkingNodes.length} 完成
              </span>
            </div>
            <button
              onClick={onToggleTree}
              className="text-text-muted hover:text-text-primary p-0.5"
              title={treeCollapsed ? "展开思维树" : "折叠思维树"}
            >
              {treeCollapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
            </button>
          </div>
          {!treeCollapsed && (
            <div className="h-[calc(100%-2.25rem)]">
              <ThinkingTreeView nodes={thinkingNodes} />
            </div>
          )}
        </div>
      )}

      {/* 消息区(下半) */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && !showTree ? (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-amber-500/10 flex items-center justify-center mb-4">
              <GitBranch size={28} className="text-amber-600" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary mb-2">
              战术规划
            </h2>
            <p className="text-sm text-text-muted mb-6">
              multi-mind 9 stage 思维扩散:Router → Decomposer → 双轨执行 → Critic → Integrator
            </p>
            <div className="grid grid-cols-2 gap-2 w-full">
              {currentTab.suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggestion(s)}
                  disabled={isStreaming}
                  className="panel p-3 text-left text-sm text-text-secondary hover:text-text-primary hover:border-amber-500 transition-colors disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
            <button
              onClick={() => onNavigate("/ai/chat")}
              className="text-xs text-text-muted hover:text-text-primary mt-4"
            >
              ← 切回训练答疑模式
            </button>
          </div>
        ) : (
          <>
            {/* 思维树隐藏时, 显示完整历史 */}
            {!showTree && messages.map((m) => (
              <ChatMessage key={m.id} msg={m} />
            ))}

            {/* 思维树显示时, 只显示最后一条 assistant 的最终建议(详情在思维树里看) */}
            {showTree && lastAssistant && (
              <div className="panel p-4 border-amber-200/50 bg-amber-50/20">
                <div className="text-[10px] font-semibold text-amber-700 mb-1.5 flex items-center gap-1">
                  <Sparkles size={11} /> 最终建议
                </div>
                <ChatMessage msg={lastAssistant} />
                {sources && sources.length > 0 && (
                  <div className="mt-3 panel p-2 bg-white/60 text-xs">
                    <div className="text-text-secondary font-semibold mb-1">📚 知识库参考</div>
                    {sources.map((s, i) => (
                      <div key={i} className="text-text-muted">
                        {i + 1}. {s.title} <span className="text-[10px]">— {s.path}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 空 + tree 显示中(用户消息刚发出, assistant 还在跑) */}
            {showTree && !lastAssistant && messages.length > 0 && messages.map((m) => (
              <ChatMessage key={m.id} msg={m} />
            ))}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>
    </div>
  );
}
