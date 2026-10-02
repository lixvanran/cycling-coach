// 单条消息气泡(模仿 Z 项目 ChatPage 风格)
// V0.8.3: 提取 workout JSON 检测 + "加入 Builder" 按钮逻辑
//   - 检测 ```workout ... ``` 代码块 (正则)
//   - 解析失败 → 按钮不显示 (容错)
//   - 解析成功 → 在气泡下方显示 "➕ 加入 Builder" 按钮
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";  // V0.7.5.4 DEV-17: 防 XSS
import { Brain, User, Wand2 } from "lucide-react";
import { useState } from "react";
import type { ChatMsg } from "../store/useAppStore";
import type { Block } from "../lib/builderBlocks";
import clsx from "clsx";

interface Props {
  msg: ChatMsg;
  // V0.8.3: 外部注入 (ChatPage 流式完成后算一遍)
  workoutBlocks?: Block[] | null;
  workoutTitle?: string;
  onAddToBuilder?: (blocks: Block[], title: string) => void;
}

// V0.8.3: 提取 workout 代码块 (markdown ```workout ... ```)
const WORKOUT_BLOCK_RE = /```workout\s*\n([\s\S]+?)\n```/;

export function ChatMessage({
  msg,
  workoutBlocks,
  workoutTitle,
  onAddToBuilder,
}: Props) {
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
            className="text-xs text-text-muted hover:text-text-secondary mb-1.5 flex items-center gap-1 px-2 py-0.5 rounded hover:bg-bg-subtle"
          >
            <Brain size={11} />
            {showThinking ? "隐藏思考" : `思考过程(${msg.thinking.length}字)`}
          </button>
        )}
        {!isUser && showThinking && msg.thinking && (
          <div className="text-xs text-text-muted bg-bg-base border border-border rounded p-3 mb-1.5 max-w-full italic leading-relaxed">
            {msg.thinking}
          </div>
        )}
        {/* 主内容 */}
        {isUser ? (
          <div
            className="px-4 py-2.5 rounded rounded-tr-sm bg-accent-primary text-white text-sm leading-relaxed whitespace-pre-wrap shadow-sm"
          >
            {msg.content}
          </div>
        ) : (
          <div className="px-4 py-3 rounded rounded-tl-sm bg-white border border-border text-text-primary text-sm leading-relaxed prose prose-sm max-w-none shadow-sm">
            {msg.content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                {msg.content}
              </ReactMarkdown>
            ) : msg.error ? (
              <span className="text-accent-danger">⚠ {msg.error}</span>
            ) : (
              <span className="text-text-muted">思考中…</span>
            )}
          </div>
        )}
        {/* V0.8.3: workout 加入 Builder 按钮 (在 bubble 下方) */}
        {!isUser && workoutBlocks && workoutBlocks.length > 0 && onAddToBuilder && (
          <button
            onClick={() => onAddToBuilder(workoutBlocks, workoutTitle || "Chat 生成的训练")}
            className="mt-1.5 ml-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold bg-accent-warning text-white hover:opacity-90 transition-all shadow-sm"
            title={`把 ${workoutBlocks.length} 个块导入到 Builder`}
          >
            <Wand2 size={12} />
            ➕ 加入 Builder
            <span className="text-[10px] opacity-80 ml-0.5">({workoutBlocks.length}块)</span>
          </button>
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
        <div className="w-8 h-8 rounded-full bg-bg-subtle flex items-center justify-center flex-shrink-0">
          <User size={16} className="text-text-secondary" />
        </div>
      )}
    </div>
  );
}

/**
 * V0.8.3: 从 AI 回复里提取 workout JSON, 转成 Builder 的 Block[]
 *
 * 规则:
 * 1. 正则找出 ```workout ... ``` 块
 * 2. JSON.parse → { title, steps[] }
 * 3. steps[] → Block[]:
 *    - 单个 warmup/cooldown/recovery → kind="single"
 *    - 连续多个 main 之间夹 recovery → 自动组合成 kind="loop" 循环块
 *      (4x8min: main(8min) + recovery(2min) × 3 + main(8min) → loop(4 reps))
 *
 * 容错:
 *  - 无 ```workout 块 → 返回 null (按钮不显示)
 *  - JSON parse 失败 → 返回 null
 *  - steps 为空 → 返回 null
 */
export function extractWorkoutFromContent(content: string): {
  title: string;
  blocks: Block[];
} | null {
  if (!content) return null;
  const m = WORKOUT_BLOCK_RE.exec(content);
  if (!m) return null;
  const raw = m[1].trim();
  let parsed: any;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || !Array.isArray(parsed.steps)) return null;
  const steps = parsed.steps.filter(isValidStep);
  if (steps.length === 0) return null;

  // 转换为 Builder Block[]
  const blocks = stepsToBlocks(steps);
  return { title: parsed.title || "Chat 生成的训练", blocks };
}

function isValidStep(s: any): boolean {
  if (!s || typeof s !== "object") return false;
  const k = s.kind;
  if (k !== "warmup" && k !== "main" && k !== "recovery" && k !== "cooldown") return false;
  if (typeof s.duration_s !== "number" || s.duration_s <= 0) return false;
  return true;
}

function rid() {
  return Math.random().toString(36).slice(2, 10);
}

/**
 * V0.8.3: 把 step[] 转成 Block[]
 *
 * 算法:
 *  - 扫描 steps, 找连续 [main, recovery, main, recovery, ..., main] 模式
 *  - 检测到第一个 main 时开始积累: repMain, repRest
 *  - 遇到下一个 main: 同一组, 重复数 +1
 *  - 遇到非 main/recovery (warmup/cooldown) 或序列结尾: 落盘 loop 块
 *  - 单个 warmup/cooldown/recovery 落 single 块
 */
function stepsToBlocks(steps: any[]): Block[] {
  const out: Block[] = [];
  let i = 0;
  while (i < steps.length) {
    const s = steps[i];
    if (s.kind !== "main") {
      // 单块
      out.push({ id: rid(), kind: "single", step: toStep(s) });
      i++;
      continue;
    }
    // main 起始, 找完整 loop 序列
    const work = toStep(s);
    let reps = 1;
    let rest: any = null;
    let j = i + 1;
    while (j < steps.length && steps[j].kind === "recovery") {
      rest = toStep(steps[j]);
      j++;
    }
    // 紧跟的 main (j 是 main 位置) 算重复次数
    while (j < steps.length && steps[j].kind === "main") {
      reps++;
      j++;
      while (j < steps.length && steps[j].kind === "recovery") {
        // 多个 recovery 也算同一组 (用第一个)
        if (!rest) rest = toStep(steps[j]);
        j++;
      }
    }
    if (reps === 1 && !rest) {
      // 真的就一个 main, 不必包成 loop
      out.push({ id: rid(), kind: "single", step: work });
    } else {
      const block: Block = {
        id: rid(),
        kind: "loop",
        reps,
        work,
        rest: rest || null,
        label: work.label || `${reps}×${Math.round(work.duration_s / 60)}min`,
      };
      out.push(block);
    }
    i = j;
  }
  return out;
}

function toStep(s: any) {
  return {
    kind: s.kind,
    duration_s: s.duration_s,
    power_pct_ftp: typeof s.power_pct_ftp === "number" ? s.power_pct_ftp : undefined,
    hr_pct_lthr: typeof s.hr_pct_lthr === "number" ? s.hr_pct_lthr : undefined,
    cadence_rpm: typeof s.cadence_rpm === "number" ? s.cadence_rpm : undefined,
    label: s.label || "",
  };
}