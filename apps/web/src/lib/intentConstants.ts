/**
 * 训练意图 (intent / intensity / goal) 的唯一真相源 — V0.9.1
 *
 * ## 为什么提到共享文件
 *
 * 这个概念原本散在三个地方, 互相不一致:
 *
 * | 位置 | 原值 |
 * |---|---|
 * | `CalendarPage.INTENT_LABEL` | 标准值(有中文) |
 * | `DailyRecommendationCard.WORKOUT_META` | `vo2`(无中文标签问题) |
 * | `LibraryPage` | **直接渲染原始英文**, 没有映射表 |
 *
 * 结果:
 * - 日历事件悬停显示 `甜点课 · undefined · 120min`(查不到映射)
 * - 课程库卡片徽章显示 `race` / `endurance` 而不是「比赛」「耐力 Z2」
 *   —— 同一个概念, 两个页面两种语言
 *
 * ## 与后端的契约
 *
 * 标准值来自 `cycling_coach/data/sqlite/models.py` 的注释, 由
 * `tools/check_intent_vocab.py` 在 CI 里强制校验:
 *
 *     recovery / endurance / tempo / threshold / vo2max / race
 *
 * 历史上同时存在 `vo2max` / `vo2` / `sweet_spot` 三套拼法。
 * `sweet_spot` 是 ACWR 的**负荷区间**(core/metrics/acwr.py), 同形异义。
 *
 * **改这里之前先跑 `python tools/check_intent_vocab.py`** ——
 * 改了会同时影响前后端契约。
 */

import type { WorkoutIntent } from "./types";

/** 标准意图全集 —— 与后端 models.py 注释一致 */
export const CANONICAL_INTENTS: WorkoutIntent[] = [
  "recovery",
  "endurance",
  "tempo",
  "threshold",
  "vo2max",
  "race",
];

/** 意图的中文标签(带强度区间后缀, 和日历图例一致) */
export const INTENT_LABEL: Record<WorkoutIntent, string> = {
  recovery: "恢复",
  endurance: "耐力 Z2",
  tempo: "节奏 Z3",
  threshold: "阈值 Z4",
  vo2max: "VO2 Z5",
  race: "比赛",
};

/**
 * 取意图的中文标签。
 *
 * ⚠️ 未知值**显式回落到原始字符串**, 而不是静默返回 undefined ——
 * undefined 渲染到界面上就是字面量 "undefined", 用户完全看不懂。
 * 而回落成原始值至少还能看出"这是个什么意图"。
 */
export function intentLabel(intent: string | null | undefined): string {
  if (!intent) return "";
  return INTENT_LABEL[intent as WorkoutIntent] ?? intent;
}