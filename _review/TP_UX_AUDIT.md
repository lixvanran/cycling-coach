# TrainingPeaks UX 对标深度调研报告

> **作者**: Mavis Agent Team (M3)
> **时间**: 2026-09-19
> **对象**: `cycling-coach` V0.8.2 → V0.9.x 路线规划
> **方法**: 公开文档 + 应用商店描述 + 教练社区博客 + 第三方评测 + V0.8.2 现有代码逐项对照
> **原则**: 不照抄, 只挑工程价值高且符合 "AI 教练" 定位的特性

---

## 0. TL;DR (一页纸结论)

**TP 的护城河不是某一个炫酷功能, 而是一套完整训练闭环**:
数据采集 (Garmin/Suunto/Watch) → 结构化计划 (Calendar + Workout Builder) → 执行反馈 (Compliance + PMC) → 长期激励 (Peak Performances + StackUp) → 教练协作 (Bulk Copy + Limited Availability)。

我们 V0.8.2 已有:
- ✅ Calendar / Builder / Library (workout 库 + 拖拽)
- ✅ PMC (CTL/ATL/TSB)
- ✅ AI Chat (教练对话)
- ✅ FIT 导入 / W'bal / 功率曲线
- ✅ Daily Recommendation (借鉴 TP 命名)

**真正缺的 (按 P0 / P1 / P2 排序)**:
- 🔴 **P0**: Compliance 颜色系统 (日历一眼看出执行偏差)
- 🔴 **P0**: Peak Performances 自动 PR 检测 (跨活动跨年度纪录, 留住用户的"成就感")
- 🟡 **P1**: StackUp / 同龄同档对比 (社交激励, 但 V0.8.2 无云, 暂时降级)
- 🟡 **P1**: Workout Compliance 排序规则 (D / Dist / TSS 优先级)
- 🟡 **P1**: Calendar 今日训练一键完成 (Quick View + 一键上传/记录)
- 🟡 **P1**: Workout Builder "Ramp Up / Ramp Down" 块 (TP 有, 我们没有)
- 🟢 **P2**: Threshold 自动检测 + 自动应用
- 🟢 **P2**: Calendar export (.ics, 同 Google/Apple 日历同步)
- 🟢 **P2**: Custom Zones (自定义区间命名 / 区间边界)
- ⚪ **不做**: Coach workflow / 多人协作 / Limited Availability (个人产品方向, 不开)

**战略观察**:
我们不能也不应该对标 TP 全部。TP 是 SaaS (多人 + 教练 + 订阅), 我们是 desktop / self-host AI 教练。聚焦 "单人的深度训练闭环 + AI 辅助" 是差异化, 不要变成第 11 个 TP 克隆。

---

## 1. TP 核心 UX 特性清单 (12 项)

按用户日常使用频率排序:

| #  | 特性                       | 来源                            | 用户视角价值                     |
|----|----------------------------|--------------------------------|----------------------------------|
| 1  | **Calendar + Compliance**   | 主页 / Workout Card            | 每天打开看 "今天该做什么" + 完成度 |
| 2  | **PMC (Fitness/Form/Fatigue)** | 主页右侧三块                  | 知道何时状态好, 何时需要恢复      |
| 3  | **Peak Performances (PR)**  | Workout Card medal icon        | 成就感, 长期留存                  |
| 4  | **Workout Builder (8 blocks)** | 创建 workout                  | 计划训练核心                      |
| 5  | **StackUp**                 | 同龄同性别对比                  | 社交激励 (Premium 限定)           |
| 6  | **Limited Availability**    | 教练视角                       | 教练功能, 单人不优先              |
| 7  | **AI Workout Generator**    | 教练视角                       | 文本 → 结构化 workout             |
| 8  | **Bulk Copy & Paste**       | 教练视角                       | 复制一段日期区间                  |
| 9  | **Custom Zones**            | 教练 / Premium                 | 自定义区间命名                    |
| 10 | **Race Report Chart**       | 教练 / Dashboard               | 历史成绩一览                      |
| 11 | **Threshold Notifications** | Settings                       | 自动检测新 FTP, 可自动应用        |
| 12 | **Daily Email**             | Settings                       | 每日邮件推送今日训练              |

---

## 2. V0.8.2 现状对标 (逐项)

| TP 特性               | V0.8.2 现状                                            | 差距                                   | 等级 |
|-----------------------|-------------------------------------------------------|----------------------------------------|------|
| Calendar              | ✅ 月/周视图, 训练项卡片                              | 缺少 compliance 颜色 (V0.8.2 没做)     | P0   |
| Compliance 颜色       | ❌ 无 (训练项无颜色区分)                               | 完全缺失                               | P0   |
| PMC                   | ✅ `PMCStatusCard` + `PMCChart` (Dashboard/Insights)   | 已对标                                 | ✅   |
| Daily Workout         | ✅ `DailyRecommendationCard` (Dashboard 顶部)         | 已对标, 借鉴 TP 命名                   | ✅   |
| Peak Performances     | ⚠️ `power_curve` (单活动), 无跨活动聚合               | 缺 all-time / 年度峰值聚合             | P0   |
| Workout Builder       | ✅ 拖拽积木 (Scratch 风格), Warmup/Loop/Cooldown      | 缺 Ramp Up / Ramp Down 块              | P1   |
| StackUp               | ❌ 无 (无云, 无同龄数据)                              | 短期不做, 等云端                       | P1 (暂缓) |
| Limited Availability  | ❌ 无 (单人项目, 不需要)                              | 不做                                   | -    |
| AI Workout Generator  | ⚠️ 有 AI Chat, 但不支持 "text → structured workout"   | Chat 已有, 增强 prompt 即可            | P1   |
| Bulk Copy & Paste     | ⚠️ Builder 已有 copy plan 思路, Calendar 拖拽已有      | 已基本对标                             | ✅   |
| Custom Zones          | ⚠️ Coggan 7 区固定, 无自定义区间命名                    | 缺自定义区间方法 (Joe Friel / Coggan 多选) | P2   |
| Threshold Notif       | ⚠️ 有 FTP test, 但不会自动检测新 FTP 自动应用          | 缺自动检测逻辑                          | P2   |
| Daily Email           | ❌ 无                                                  | 后端可加, 但用户用 web 即时看, 不优先 | P3   |
| StackUp               | ❌ 无                                                  | 同上                                   | P3   |

---

## 3. 差距详细分析 (按 P0 排)

### 🔴 P0-1: Compliance 颜色系统

**TP 做法**:
日历 / 主页 workout card 用 4 色直观反映实际 vs 计划:
- 🟢 Green: ±20% 内 (达标)
- 🟡 Yellow: 50-79% 或 121-150% (略偏)
- 🟠 Orange: ±50% 以上 (严重偏差)
- ⚫ Grey: 计划但没做
- 🔴 Red: 未完成

**V0.8.2 现状**:
`CalendarPage.tsx` 的训练项没有颜色, 只能看 duration 数字估算。

**实现成本**: 🟢 低
- 后端: `cycling_coach/core/metrics/compliance.py` (新), 输入 (planned_tss/duration, actual_tss/duration) → 输出颜色 enum
- 前端: `CalendarPage.tsx` 加 `border-l-4` + `bg-*` 即可
- API: `/api/activities/{id}/compliance` 已有数据, 只需前端消费
- 复用: 跟 `useConfirm` / `EmptyState` 同等级改动量 (~150 行)

**为什么 P0**: 这是用户 "打开日历第一眼" 看到的信息, 价值最高、改动最小。

---

### 🔴 P0-2: Peak Performances (PR 自动检测)

**TP 做法**:
每次上传活动后自动检测 PR:
- 时间窗: 5s / 30s / 1min / 5min / 10min / 20min / 60min / 90min
- 类型: 平均功率 / 平均心率 / 平均配速 (跑步/MTB)
- 范围: 年度 / All-time
- 显示: Workout Card 右上 medal 图标 + 数字

**V0.8.2 现状**:
- `cycling_coach/core/metrics/curve.py` 已有 MMP 功率曲线算法 ✅
- `GET /api/activities/{id}/power-curve` 已有端点 ✅
- **缺**: 跨活动聚合 (compare 当前活动的 MMP vs 历史 best MMP)
- **缺**: 活动卡片显示 "你刚刚破了 5min 功率 PR!" 提醒

**实现成本**: 🟡 中
- 后端: 新建 `cycling_coach/core/metrics/personal_records.py`
  - 输入: athlete_id, sport
  - 输出: `[{duration_s, power_w, hr_bpm, pace_s_per_km, achieved_at, activity_id}]`
  - 算法: 增量更新 — 新活动上传时, 与历史 best MMP 对比, 找出新 PR
- 前端: `ActivityDetail.tsx` 加 `<PeakPerformances />` 卡片 (5min/20min/60min 三个块)
- 工作量: 后端 ~200 行, 前端 ~120 行

**为什么 P0**:
- 留住用户的"成就感"是长期留存关键 (TP 调研里 "I love to see my CTL" 是用户原话)
- 算法已有 (curve.py), 只是聚合层缺
- 体育产品用户来一次往往因为这次破了 PR

---

### 🟡 P1-1: Workout Builder Ramp Up / Ramp Down

**TP 做法**: 8 个 block 模板里有 Ramp Up / Ramp Down (渐进块), 比如:
```
Warm Up 10min → Ramp Up 5min → Active 20min → Ramp Down 5min → Cool Down 10min
```

**V0.8.2 现状**: `BuilderPage.tsx` 只有 Warmup / Loop / Cooldown / Recovery / Active 5 种, 没有渐变块。

**实现成本**: 🟢 低 (50 行)
- `StepKind` 加 "ramp" 类型
- 渲染: 渐变 SVG / 渐变 gradient
- 导出 ZWO 时映射为 ramp step

**为什么 P1**: 用户做甜区 / 阈值热身时经常需要 (TP 8 个里最常被点的是 Ramp Up)。

---

### 🟡 P1-2: AI Workout Generator (Chat 增强)

**TP 做法**: 教练视角, 在 Builder 里有 "Workout Generator" — 输入 "4x8min sweet spot 2min rest", AI 自动生成结构化 workout。

**V0.8.2 现状**: `ChatPage.tsx` 有 Chat, 但 Chat 输出是 markdown, 不直接生成可导入 Builder 的结构。

**实现成本**: 🟡 中
- 后端: 新建 `cycling_coach/ai/prompts/workout_generator.py`
  - 输入: 自然语言 (e.g. "4x8min sweet spot 2min rest")
  - 输出: 标准 ZWO JSON 结构
- 前端: `ChatPage.tsx` 检测 chat 回复含 workout 结构 → 提供 "导入到 Builder" 按钮
- 工作量: prompt ~80 行 + 前端按钮 ~40 行

**为什么 P1**: 跟 Chat 紧密耦合, 复用已有 AI 推理, 边际成本低。但要先有 Peak Performances 数据才能智能推荐 (PR 后 AI 才能 "今天的 5min 比上周好 8W")。

---

### 🟡 P1-3: Compliance 排序规则 (Duration/Dist/TSS 优先级)

**TP 做法**: 用户可设置哪种指标主导颜色:
- Duration 主导 → 长了短了都算偏
- Distance 主导 → 距离偏差
- TSS 主导 → 训练负荷偏差

**V0.8.2 现状**: 没设置项, 默认一个算法。

**实现成本**: 🟢 低 (前端 ~50 行 + 后端 profile 加 1 字段)

**为什么 P1**: 跟 P0-1 配套, 用户体验闭环。

---

### 🟡 P1-4: Calendar 今日训练一键完成

**TP 做法**: 主页 (Home View) 4 件套:
1. Readiness 顶部
2. Today's Workout (中间, 大卡)
3. Week Overview (本周圆圈, 颜色=强度)
4. Plan Info (训练周期 + 距离比赛天数)

**V0.8.2 现状**:
- ✅ Dashboard 顶部有 `DailyRecommendationCard`
- ⚠️ 没有 "今日训练" 大卡 (用户进 Calendar 才知道)
- ⚠️ 没有 week overview 圆圈视图 (Calendar 是月历)
- ⚠️ 没有 "距离比赛 X 天" 倒计时

**实现成本**: 🟡 中 (~300 行)
- 新建 `apps/web/src/pages/HomePage.tsx` 取代 Dashboard 默认页? (不要, 会破坏现有 UX)
- 改: Dashboard 上方加 "今日训练" 大卡 (从 Calendar API 拉今日 planned)
- 改: Dashboard 加 "本周总览" 7 个圆圈 (V0.8.2 已有 weekly stats, 加个圆圈视图)
- 改: `RaceList` API 已经有, 加倒计时组件

**为什么 P1**: TP 用户第一触点, 我们 Dashboard 已经是最像 Home View 的页面, 微调就好。

---

### 🟢 P2-1: Threshold 自动检测 + 自动应用

**TP 做法**: 每 60 天检测一次阈值变化, 用户可设 "自动应用"。

**V0.8.2 现状**: 手动 FTP test, 无自动检测。

**实现成本**: 🟡 中 (~250 行)
- 后端: `cycling_coach/core/metrics/threshold_detector.py`
- 算法: 20min 测试功率的 95% (经典 Coggan 法), 7 天滚动平均
- 加 cron 跑

**为什么 P2**: TP Premium 功能, 用户手动测 FTP 已经够用。

---

### 🟢 P2-2: Calendar Export (.ics)

**TP 做法**: iCal URL 同步到 Google/Apple/Outlook 日历。

**V0.8.2 现状**: 无。

**实现成本**: 🟢 低 (~150 行)
- 后端: `/api/calendar/ics.ics` 端点, 输出 iCal 格式
- 前端: Settings 加 "复制订阅链接" 按钮

**为什么 P2**: 单机用户主要在 Web 看, 但方便偶尔用 Google 日历提醒的。

---

### 🟢 P2-3: Custom Zones

**TP 做法**: 自定义区间命名 (e.g. "Coggan 7 区" vs "Joe Friel 3 区")。

**V0.8.2 现状**: 只有 Coggan 7 区固定。

**实现成本**: 🟢 低 (~150 行)
- 后端: `WorkoutZoneConfig` 表 + API
- 前端: Profile 加 "区间设置"

**为什么 P2**: 90% 用户用 Coggan 7 区, 高级用户才需要。

---

### ⚪ 不做

| 特性                  | 不做理由                                                  |
|----------------------|---------------------------------------------------------|
| StackUp              | 单机无云, 无法对比同龄用户, 留作 V1.x 云端上线后        |
| Limited Availability | 教练功能, 不在个人产品方向                              |
| Bulk Copy & Paste    | Builder 已有 copy plan 思路, 教练视角功能               |
| Daily Email          | 用户已用 Web 即时看, 邮件推送低优先级                    |
| Coach Account        | 单人产品, 不做教练侧                                    |
| Workout 评论 / Coach 评论 | 单人无教练, 简化为 Diary (已有 V0.8.2)               |

---

## 4. 用户视角差距分析 (vs V0.8.2 用户真实使用场景)

跑一个典型的 "工作日训练前" 场景:

| 步骤                          | TP 用户                                  | V0.8.2 用户                                       | 体验差距 |
|------------------------------|------------------------------------------|---------------------------------------------------|----------|
| 1. 打开                       | 看到今日训练大卡 + PMC + 倒计时          | 看到 DailyRecommendationCard + PMC              | 类似 ✅   |
| 2. 看训练项                  | 一眼看出绿/黄/红 (compliance)            | 需要点开看 duration 数字                           | **P0 缺** |
| 3. 决定要不要改               | 拖到日历其他天 (Limited Availability)    | 编辑日期改日                                       | 类似 ✅   |
| 4. 看过去一周                | Week overview 圆圈图                     | Calendar 月历                                     | **P1 缺** |
| 5. 训练完上传 FIT             | Auto-sync 或手动 → 自动 PR 检测 + medal  | 手动导入 → 显示活动详情                            | **P0 缺** |
| 6. 第二天看 PR               | 主页 / Activity 都有 medal                | 只能对比单活动 power curve                        | **P0 缺** |
| 7. 季度回顾                  | StackUp + Race Report                    | 看 Insights (CTL/ATL 趋势)                        | 类似 ✅   |
| 8. 想跟同龄人比               | StackUp                                  | 没有                                              | 暂缓   |

**结论**: 用户日常 **看 / 做 / 上传 / 回顾** 四步里, **看** 和 **上传后回顾** 是体验差距最大的两个点。这正是 P0-1 (Compliance) 和 P0-2 (Peak Performances) 对应的场景。

---

## 5. 实施建议路线图

### 阶段 1 (V0.8.3): P0 闭环 - 留住用户
预计 2-3 周工作量。

1. **Compliance 颜色系统** (P0-1)
   - 后端 `compliance.py` + API
   - 前端 CalendarPage 颜色化
   - 用户设置 (Duration/Dist/TSS 主导)

2. **Peak Performances** (P0-2)
   - 后端 `personal_records.py` + API
   - 前端 ActivityDetail 加 PR 卡片
   - 主页 (Dashboard) "最近 PR" widget

3. **Ramp Up/Down block** (P1-1)
   - Builder 新增渐变块
   - 50 行, 顺手做

### 阶段 2 (V0.8.4): P1 优化 - 提升效率
- AI Workout Generator (Chat → Builder)
- Dashboard 今日训练大卡
- Week Overview 圆圈视图
- Race 倒计时

### 阶段 3 (V0.9.x): P2 增值
- Threshold 自动检测
- Calendar .ics 导出
- Custom Zones

---

## 6. 关键引用来源

| 引用                                            | URL                                                                                          |
|------------------------------------------------|----------------------------------------------------------------------------------------------|
| Workout Card Overview + Compliance 颜色规则    | https://help.trainingpeaks.com/hc/en-us/articles/204861204-Workout-Card-Overview            |
| Peak Performances 介绍                          | https://help.trainingpeaks.com/hc/en-us/articles/115001332452-Peak-Perfomances              |
| Peak Performances FAQ                           | https://help.trainingpeaks.com/hc/en-us/articles/115000360171-Peak-Performances-FAQ          |
| Mobile Home View (4 件套)                       | https://www.trainingpeaks.com/blog/trainingpeaks-mobile-home-view/                           |
| Athlete User Guide (全功能盘点)                | https://www.trainingpeaks.com/learn/trainingpeaks-athlete-user-guide/                        |
| Structured Workout Builder (8 blocks + 模板)    | https://help.trainingpeaks.com/hc/en-us/articles/235164967-Workout-Builder                  |
| Strength Workout Builder                        | https://help.trainingpeaks.com/hc/en-us/articles/21397126893581-Using-the-Strength-Workout-Builder |
| 8 Coaching Features (Limited Availability / Bulk Copy 等) | https://www.trainingpeaks.com/coach-blog/8-trainingpeaks-coaching-features-that-save-time-boost-business |
| Annual Training Plan (TSS 主导规划)            | https://www.trainingpeaks.com/blog/a-look-at-planning-by-tss-with-the-new-atp              |
| Premium 是否值得 (用户原话引用)                 | https://www.trainingpeaks.com/blog/is-trainingpeaks-premium-worth-it/                       |
| TrainingPeaks Virtual / 室内骑行评测           | https://www.cyclistshub.com/indievelo-review                                                  |
| iOS App Store (UI 描述 + 评分 + 评论痛点)      | https://apps.apple.com/lt/app/trainingpeaks/id408047715                                     |

---

## 7. 风险与不做的明确项

**风险**:
- P0-2 Peak Performances: 算法用 MMP, 但 MMP 算的是 "单活动内最大滚动平均", 需要跨活动聚合时要重新设计增量更新逻辑 (新活动 vs 历史 best)。如果用户上传 100 个活动, 增量更新要 O(n) 比较, 单用户数据量小, 不构成性能问题。
- P1-1 Ramp: ZWO 导出 ramp step 需要查 spec, 防止某些旧设备不支持。

**明确不做的 (避免 scope creep)**:
- 教练账号 / 协作
- 多人 / 多账号
- 实时在线 (所有数据本地)
- 订阅 / 支付

---

**调研结束。建议先开 V0.8.3 阶段 1 (P0 + P1-1 Ramp), 等用户验收后再做阶段 2。**