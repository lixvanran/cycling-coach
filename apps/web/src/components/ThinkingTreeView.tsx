// ThinkingTreeView — V0.8.0 战术规划 mode 思维树可视化
// 用途: 显示 multi-mind 的 9 stage 思维树
// 节点状态: pending(灰) / running(蓝色脉冲) / done(绿) / pruned(红删)
//
// 视觉: SVG 画节点 + 连线, 树状布局
//   Router
//     ├─ Decomposer
//     │   ├─ Aggressive Track (executor_a_1, executor_a_2, ...)
//     │   └─ Conservative Track (executor_c_1, executor_c_2, ...)
//     ├─ Critic
//     └─ Integrator
//
// 实时流式更新: 通过 nodes prop 传入, 父组件从 SSE 事件构造

import { useState, useMemo } from "react";
import { Brain, CheckCircle2, XCircle, Loader2, GitBranch, Sparkles, ChevronRight } from "lucide-react";
import clsx from "clsx";
import type { ThinkingNode, ThinkingNodeStatus } from "../lib/types";

interface Props {
  nodes: ThinkingNode[];
  // 可选: 选中节点回调(用于在 chat 中展开)
  onNodeClick?: (node: ThinkingNode) => void;
}

// ============================================================
// 节点类型映射(根据 stage 推断中文 label / 轨道)
// ============================================================

const STAGE_META: Record<string, { label: string; track: "shared" | "aggressive" | "conservative" }> = {
  router: { label: "Router", track: "shared" },
  decomposer: { label: "Decomposer", track: "shared" },
  executor_a: { label: "激进执行", track: "aggressive" },
  executor_c: { label: "保守执行", track: "conservative" },
  critic: { label: "Critic", track: "shared" },
  integrator: { label: "Integrator", track: "shared" },
};

const STATUS_STYLE: Record<ThinkingNodeStatus, { bg: string; border: string; text: string; icon: any; ring: string }> = {
  pending: {
    bg: "bg-slate-50",
    border: "border-slate-300",
    text: "text-slate-500",
    ring: "ring-slate-200",
    icon: null,
  },
  running: {
    bg: "bg-blue-50",
    border: "border-blue-400",
    text: "text-blue-700",
    ring: "ring-blue-200",
    icon: Loader2,
  },
  done: {
    bg: "bg-emerald-50",
    border: "border-emerald-400",
    text: "text-emerald-700",
    ring: "ring-emerald-200",
    icon: CheckCircle2,
  },
  pruned: {
    bg: "bg-rose-50",
    border: "border-rose-300",
    text: "text-rose-500 line-through",
    ring: "ring-rose-200",
    icon: XCircle,
  },
};

const TRACK_COLOR: Record<string, string> = {
  shared: "text-slate-500",
  aggressive: "text-orange-600",
  conservative: "text-cyan-700",
};

// ============================================================
// 布局算法 — 自上而下分层布局
// ============================================================

interface LayoutNode {
  node: ThinkingNode;
  x: number;       // 列(层)
  y: number;       // 行
  width: number;
  height: number;
}

const NODE_W = 130;
const NODE_H = 56;
const H_GAP = 32;   // 水平间距
const V_GAP = 18;   // 垂直间距

function layoutTree(nodes: ThinkingNode[]): { layout: LayoutNode[]; width: number; height: number } {
  if (nodes.length === 0) return { layout: [], width: 320, height: 100 };

  // 按 stage 推断 layer
  // Layer 0: router
  // Layer 1: decomposer
  // Layer 2: executors (aggressive + conservative)
  // Layer 3: critic
  // Layer 4: integrator
  const layerOf = (n: ThinkingNode): number => {
    const stage = n.stage.toLowerCase();
    if (stage.startsWith("router")) return 0;
    if (stage.startsWith("decomposer")) return 1;
    if (stage.startsWith("executor")) return 2;
    if (stage.startsWith("critic")) return 3;
    if (stage.startsWith("integrator")) return 4;
    return 1;  // default
  };

  // 分组到 layers
  const layers: ThinkingNode[][] = [[], [], [], [], []];
  for (const n of nodes) {
    layers[layerOf(n)].push(n);
  }

  const maxLayerSize = Math.max(...layers.map((l) => l.length), 1);
  const totalHeight = maxLayerSize * (NODE_H + V_GAP);
  const totalWidth = 5 * (NODE_W + H_GAP);

  const layout: LayoutNode[] = [];
  layers.forEach((layer, layerIdx) => {
    const layerSize = layer.length;
    // 居中该 layer
    const yStart = (totalHeight - layerSize * (NODE_H + V_GAP)) / 2;
    layer.forEach((node, i) => {
      layout.push({
        node,
        x: layerIdx * (NODE_W + H_GAP),
        y: yStart + i * (NODE_H + V_GAP),
        width: NODE_W,
        height: NODE_H,
      });
    });
  });

  return { layout, width: totalWidth, height: totalHeight };
}

// ============================================================
// 单个节点 (SVG)
// ============================================================

function TreeNodeView({ layout, onClick }: { layout: LayoutNode; onClick: () => void }) {
  const { node, x, y, width, height } = layout;
  const style = STATUS_STYLE[node.status];
  const meta = STAGE_META[node.stage.toLowerCase().split("_")[0]] || { label: node.stage, track: "shared" };
  const trackColor = TRACK_COLOR[meta.track];
  const Icon = style.icon;

  // running 状态: 蓝色脉冲
  const isRunning = node.status === "running";
  const isDone = node.status === "done";
  const isPruned = node.status === "pruned";

  return (
    <g
      transform={`translate(${x}, ${y})`}
      className="cursor-pointer"
      onClick={onClick}
    >
      {/* 外环 (done 显示绿环) */}
      {isDone && (
        <rect
          x={-3}
          y={-3}
          width={width + 6}
          height={height + 6}
          rx={12}
          fill="none"
          stroke="rgb(16 185 100)"
          strokeWidth={1.5}
          opacity={0.4}
        />
      )}
      {/* 卡片本体 */}
      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        rx={9}
        className={clsx(
          "transition-all duration-300",
          style.bg,
          style.border,
          isRunning && "animate-pulse",
        )}
        strokeWidth={1.5}
        fill="white"
        fillOpacity={isPruned ? 0.6 : 1}
      />
      {/* 顶部小点: 状态指示 */}
      <circle
        cx={12}
        cy={12}
        r={4}
        fill={
          isDone ? "rgb(16 185 100)" :
          isRunning ? "rgb(59 130 246)" :
          isPruned ? "rgb(244 63 94)" :
          "rgb(148 163 184)"
        }
      />
      {/* 轨道小标签 */}
      {meta.track !== "shared" && (
        <text
          x={width - 8}
          y={14}
          textAnchor="end"
          className={clsx("text-[9px] font-semibold uppercase tracking-wider", trackColor)}
          fill="currentColor"
        >
          {meta.track === "aggressive" ? "激进" : "保守"}
        </text>
      )}
      {/* 主标签 */}
      <text
        x={width / 2}
        y={height / 2 - 4}
        textAnchor="middle"
        className="text-[12px] font-semibold"
        fill="currentColor"
      >
        {meta.label}
      </text>
      {/* 子标签 / 编号 */}
      {node.stage.includes("_") && (
        <text
          x={width / 2}
          y={height / 2 + 11}
          textAnchor="middle"
          className="text-[9px] font-mono"
          fill="rgb(100 116 139)"
        >
          {node.id}
        </text>
      )}
      {/* score */}
      {typeof node.score === "number" && (
        <text
          x={width - 6}
          y={height - 6}
          textAnchor="end"
          className="text-[9px] font-mono font-semibold"
          fill="rgb(217 119 6)"
        >
          {node.score.toFixed(1)}
        </text>
      )}
      {/* 图标 */}
      {Icon && (
        <foreignObject x={width - 22} y={height - 22} width={18} height={18}>
          <Icon size={14} className={clsx(style.text, isRunning && "animate-spin")} />
        </foreignObject>
      )}
    </g>
  );
}

// ============================================================
// 边(连线)
// ============================================================

function TreeEdge({ from, to, isActive }: { from: LayoutNode; to: LayoutNode; isActive: boolean }) {
  const x1 = from.x + from.width;
  const y1 = from.y + from.height / 2;
  const x2 = to.x;
  const y2 = to.y + to.height / 2;
  const midX = (x1 + x2) / 2;
  const d = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
  return (
    <path
      d={d}
      stroke={isActive ? "rgb(59 130 246)" : "rgb(148 163 184)"}
      strokeWidth={isActive ? 1.8 : 1}
      fill="none"
      strokeDasharray={isActive ? "0" : "3 3"}
      opacity={isActive ? 0.9 : 0.5}
      className="transition-all duration-300"
    />
  );
}

// ============================================================
// 主组件
// ============================================================

export function ThinkingTreeView({ nodes, onNodeClick }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { layout, width, height } = useMemo(() => layoutTree(nodes), [nodes]);

  // 构造 id → layout 索引
  const layoutMap = useMemo(() => {
    const m = new Map<string, LayoutNode>();
    for (const l of layout) m.set(l.node.id, l);
    return m;
  }, [layout]);

  // 构造 edges — 根据 stage layer 自动连线
  const edges = useMemo(() => {
    const es: Array<{ from: LayoutNode; to: LayoutNode; isActive: boolean }> = [];
    for (const l of layout) {
      if (!l.node.parent_id) continue;
      const parent = layoutMap.get(l.node.parent_id);
      if (parent) {
        const bothDone = l.node.status === "done" && parent.node.status === "done";
        const anyRunning = l.node.status === "running" || parent.node.status === "running";
        es.push({ from: parent, to: l, isActive: bothDone || anyRunning });
      }
    }
    return es;
  }, [layout, layoutMap]);

  // 统计
  const stats = useMemo(() => {
    const total = nodes.length;
    const done = nodes.filter((n) => n.status === "done").length;
    const running = nodes.filter((n) => n.status === "running").length;
    const pruned = nodes.filter((n) => n.status === "pruned").length;
    return { total, done, running, pruned };
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-muted p-6">
        <Brain className="w-10 h-10 mb-2 opacity-30" />
        <div className="text-sm">思维树暂无节点</div>
        <div className="text-xs mt-1 opacity-60">发送问题后, multi-mind 会展开 9 stage 思维过程</div>
      </div>
    );
  }

  // 找到当前展开节点
  const expandedNode = expandedId ? nodes.find((n) => n.id === expandedId) : null;

  return (
    <div className="flex flex-col h-full">
      {/* 顶部状态栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-bg-elevated/50">
        <div className="flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5 text-text-secondary" />
          <span className="text-xs font-semibold text-text-primary">思维树</span>
          <span className="text-[10px] text-text-muted font-mono">
            {stats.done}/{stats.total} 完成
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          {stats.running > 0 && (
            <span className="flex items-center gap-1 text-blue-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              {stats.running} 进行中
            </span>
          )}
          {stats.pruned > 0 && (
            <span className="flex items-center gap-1 text-rose-500">
              <XCircle className="w-3 h-3" />
              {stats.pruned} 已剪枝
            </span>
          )}
          {stats.done === stats.total && stats.total > 0 && (
            <span className="flex items-center gap-1 text-emerald-600">
              <CheckCircle2 className="w-3 h-3" />
              完成
            </span>
          )}
        </div>
      </div>

      {/* 主图区 */}
      <div className="flex-1 overflow-auto p-3 relative bg-bg-base/30">
        <svg
          width={width + 16}
          height={height + 16}
          viewBox={`-8 -8 ${width + 16} ${height + 16}`}
          className="block mx-auto"
        >
          {/* 连线层(在节点下方) */}
          <g>
            {edges.map((e, i) => (
              <TreeEdge
                key={`e-${i}`}
                from={e.from}
                to={e.to}
                isActive={e.isActive}
              />
            ))}
          </g>
          {/* 节点层 */}
          <g>
            {layout.map((l) => (
              <TreeNodeView
                key={l.node.id}
                layout={l}
                onClick={() => {
                  setExpandedId(expandedId === l.node.id ? null : l.node.id);
                  onNodeClick?.(l.node);
                }}
              />
            ))}
          </g>
        </svg>

        {/* 选中节点的展开面板 */}
        {expandedNode && (
          <NodeDetailPanel
            node={expandedNode}
            onClose={() => setExpandedId(null)}
          />
        )}
      </div>

      {/* 图例 */}
      <div className="px-3 py-1.5 border-t border-border flex items-center gap-3 text-[10px] text-text-muted bg-bg-elevated/30">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-slate-400" /> 等待
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-500" /> 进行中
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500" /> 完成
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-rose-500" /> 已剪枝
        </span>
        <span className="ml-auto">点节点查看详情 →</span>
      </div>
    </div>
  );
}

// ============================================================
// 节点详情面板
// ============================================================

function NodeDetailPanel({ node, onClose }: { node: ThinkingNode; onClose: () => void }) {
  const meta = STAGE_META[node.stage.toLowerCase().split("_")[0]] || { label: node.stage, track: "shared" };
  return (
    <div className="absolute top-3 right-3 w-80 max-h-[80%] panel p-3 z-10 shadow-elevated overflow-auto">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-accent-primary" />
            <span className="text-sm font-semibold text-text-primary">{meta.label}</span>
            <span className="text-[10px] font-mono text-text-muted">{node.id}</span>
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">
            状态: <span className={STATUS_STYLE[node.status].text}>{node.status}</span>
            {typeof node.score === "number" && (
              <> · 评分: <span className="font-mono text-amber-600">{node.score.toFixed(2)}</span></>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary text-xs px-1"
          aria-label="关闭"
        >
          ×
        </button>
      </div>
      <div className="text-[11px] text-text-secondary leading-relaxed max-h-64 overflow-auto bg-bg-base rounded p-2 border border-border">
        {node.content ? (
          <pre className="whitespace-pre-wrap font-sans">{node.content}</pre>
        ) : node.error ? (
          <span className="text-rose-600">⚠ {node.error}</span>
        ) : (
          <span className="text-text-muted italic">暂无输出 (等待后端推送)</span>
        )}
      </div>
      {node.started_at && node.finished_at && (
        <div className="text-[10px] text-text-muted mt-1.5 font-mono">
          耗时: {((node.finished_at - node.started_at) / 1000).toFixed(2)}s
        </div>
      )}
    </div>
  );
}

// ============================================================
// 节点构造 helpers — 父组件从 SSE 事件创建节点
// ============================================================

export function makeNode(opts: {
  id: string;
  stage: string;
  parent_id?: string | null;
  status?: ThinkingNodeStatus;
  content?: string;
  score?: number | null;
  track?: "shared" | "aggressive" | "conservative";
}): ThinkingNode {
  return {
    id: opts.id,
    stage: opts.stage,
    label: opts.id,
    status: opts.status ?? "pending",
    parent_id: opts.parent_id ?? null,
    track: opts.track ?? "shared",
    content: opts.content,
    score: opts.score ?? null,
    started_at: undefined,
    finished_at: undefined,
  };
}
