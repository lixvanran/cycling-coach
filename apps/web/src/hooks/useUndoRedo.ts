import { useState, useCallback } from "react";

/**
 * 通用 undo/redo hook
 *
 * 用法:
 *   const [blocks, setBlocks, { undo, redo, canUndo, canRedo }] = useUndoRedo<Block[]>(initialBlocks);
 *
 *   // 改 state 时:
 *   setBlocks(newBlocks, true);  // 第二个参数 true = push history
 *
 *   // 触发 undo:
 *   undo();  // setBlocks 自动变成 history[last]
 *
 * 设计:
 *   - history stack 最大 30 步, 避免内存爆炸
 *   - 每次 push 都会清空 redo stack (新分支)
 *   - setBlocks(value, false) 不记录 (用于 redo/undo 内部)
 */
export function useUndoRedo<T>(
  initial: T,
  options: { maxHistory?: number } = {},
) {
  const max = options.maxHistory ?? 30;
  const [present, setPresent] = useState<T>(initial);
  const [history, setHistory] = useState<T[]>([]);
  const [future, setFuture] = useState<T[]>([]);

  const set = useCallback(
    (value: T | ((prev: T) => T), record: boolean = true) => {
      const newValue =
        typeof value === "function"
          ? (value as (prev: T) => T)(present)
          : value;
      if (newValue === present) return;

      if (record) {
        setHistory((h) => {
          const next = [...h, present];
          return next.length > max ? next.slice(next.length - max) : next;
        });
        setFuture([]);
      }
      setPresent(newValue);
    },
    [present, max],
  );

  const undo = useCallback(() => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setHistory((h) => h.slice(0, -1));
    setFuture((f) => [present, ...f]);
    setPresent(prev);
  }, [history, present]);

  const redo = useCallback(() => {
    if (future.length === 0) return;
    const next = future[0];
    setFuture((f) => f.slice(1));
    setHistory((h) => [...h, present]);
    setPresent(next);
  }, [future, present]);

  const reset = useCallback((value: T) => {
    setPresent(value);
    setHistory([]);
    setFuture([]);
  }, []);

  return {
    value: present,
    set,
    undo,
    redo,
    reset,
    canUndo: history.length > 0,
    canRedo: future.length > 0,
    historyLength: history.length,
  };
}