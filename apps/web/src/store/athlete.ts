// Athlete Store — V0.8.0 拆分
// 运动员档案 + 训练历史概览
// 注: 大部分页面用 useState 本地存, 这里只放跨页面共享的 (e.g. athlete 档案)
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

export interface AthleteProfile {
  id: number;
  name: string;
  ftp: number | null;
  max_hr: number | null;
  lthr?: number | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  // 后端 Athlete 类型的其他字段由页面按需拉, 这里只缓存最常用的几项
}

export interface ActivitySummaryItem {
  id: number;
  date: string;
  title?: string;
  distance_m?: number;
  duration_s?: number;
  avg_power?: number;
  tss?: number;
}

interface AthleteState {
  athlete: AthleteProfile | null;
  activities: ActivitySummaryItem[];        // 最近列表缓存
  activitiesLoading: boolean;
  lastFetched: number | null;                // ms timestamp, 用来 TTL 缓存

  setAthlete: (a: AthleteProfile | null) => void;
  setActivities: (list: ActivitySummaryItem[]) => void;
  setActivitiesLoading: (b: boolean) => void;
  clear: () => void;
}

export const useAthleteStore = create<AthleteState>()(
  subscribeWithSelector((set) => ({
    athlete: null,
    activities: [],
    activitiesLoading: false,
    lastFetched: null,
    setAthlete: (a) => set({ athlete: a }),
    setActivities: (list) =>
      set({ activities: list, lastFetched: Date.now(), activitiesLoading: false }),
    setActivitiesLoading: (b) => set({ activitiesLoading: b }),
    clear: () =>
      set({ athlete: null, activities: [], activitiesLoading: false, lastFetched: null }),
  }))
);
