// ScheduleModal — V0.8.3 复用组件
// 从 LibraryPage 提取, 共用于 Builder "保存并加入日历" 流程
// props: workoutTitle, onCancel, onConfirm(date: string)
import { useState } from "react";

export interface ScheduleModalProps {
  workoutTitle: string;
  onCancel: () => void;
  onConfirm: (date: string) => void;
}

export function ScheduleModal({
  workoutTitle,
  onCancel,
  onConfirm,
}: ScheduleModalProps) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  return (
    <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center">
      <div className="bg-bg-subtle rounded p-5 w-[360px] border border-border">
        <h3 className="font-semibold mb-2">排到日历</h3>
        <p className="text-xs text-text-muted mb-3">
          将课程 <span className="text-accent">{workoutTitle}</span> 加到:
        </p>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full px-3 py-2 bg-bg-base border border-border rounded text-sm mb-3"
        />
        <p className="text-[10px] text-text-muted mb-3">
          💡 当天有活动会自动关联,完成度会更新
        </p>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 px-3 py-2 bg-bg-base border border-border rounded text-sm"
          >
            取消
          </button>
          <button
            onClick={() => onConfirm(date)}
            className="flex-1 px-3 py-2 bg-accent text-bg-base rounded text-sm font-medium"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}