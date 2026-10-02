# TrainingPeaks 操作体验对标报告 (V0.8.2 视角)

> **作者**: Mavis Agent Team (M3)
> **时间**: 2026-09-19
> **对象**: `cycling-coach` V0.8.2 操作体验差距分析
> **方法**: TP 官方"效率功能"博客 + 快捷键文档 + 用户真实吐槽 (iOS App Store 524 评论 + 论坛) + V0.8.2 源码逐项操作密度扫描
> **范围**: 仅"**用起来是否顺手**", 不涉及功能有无

---

## 0. TL;DR

TP 操作体验的护城河是 **键盘流 + 拖拽 modifier + 右键菜单 + 即时保存**, 不是什么炫酷功能。
我们 V0.8.2 在 **Builder 内部** 已经做到 70% (拖拽 / 撤销重做 / 复制粘贴), 但 **Calendar + 全局层面** 只有 ~20%。

### V0.8.2 操作维度 5 个最明显缺口

1. ❌ **全局键盘快捷键** — 只有 Cmd+K 搜索, 没有 Cmd+1/2/3 跳页、Cmd+S 全局保存、C+拖复制
2. ❌ **右键菜单 (context menu)** — 整个项目 0 处 `onContextMenu`, 全靠点按钮 / 双击
3. ❌ **Calendar 批量操作** — 不能 Shift+点击选日期范围, 不能 mass copy/paste
4. ❌ **Recurring Workouts** — 设一次只能重复一次, 无法"每周二四 6 周自动"
5. ❌ **即时保存** — Profile / Calendar / Library 编辑完都要手动点保存

### 反过来要学的负面教训 (TP 操作痛点)

- ⚠️ **不要做 Premium paywall 阻断核心操作** (TP 用户怒: "拖未来日期要 Premium") → 我们永远不做功能墙
- ⚠️ **不要做加载慢** (TP iOS 用户报 "47 分钟加载") → Vite build 已经快, 别引入慢依赖
- ⚠️ **不要让入口藏太深** (TP 用户: "需要 user guide 才能找到功能") → 所有主功能 ≤ 2 次点击

---

## 1. TP 操作优势 (按用户日常使用频率)

### 1.1 键盘快捷键 (TP 2024 年才加, 已被用户视为杀手锏)

来源: TP Help Center — Keyboard Shortcuts 文档

```
[C]opy a workout      C + drag  复制 workout 到任意天 (按住 C 再拖)
[A]nalyze a workout   A + click 已完成 workout → 跳过 Quickview, 直接进分析
[E]dit Structured     E + click 结构化 workout → 直接进 Builder 编辑
[S]ave changes        Cmd + S  无需按钮即时保存
1-6 切页             Option + 1 Home / 2 Calendar / 3 Dashboard / 4 ATP / ...
```

**TP 用户评价**: "Every click counts. ... These little hacks keep you moving faster through your calendar."

**V0.8.2 现状**:
- ✅ `Cmd+K / Ctrl+K` 全局搜索 (V0.8.2 U-1)
- ✅ Builder 内 `Ctrl+Z / Y / S / C / V / D / Delete` (BuilderPage 写得很好)
- ❌ 全局 `Cmd+1/2/3/4` 切页 (Sidebar 必须点)
- ❌ `Cmd+S` 全局保存 (Calendar / Library 编辑完必须找按钮)
- ❌ Calendar 内 `C+拖` 复制 modifier
- ❌ ActivityDetail 内 `A+click` / `E+click` modifier

### 1.2 拖拽 + Modifier (按住 C 复制拖拽)

```
普通拖   = 移动 workout
C + 拖   = 复制 workout 到目标天 (源不变)
```

**V0.8.2 现状**:
- ✅ Builder 内部拖拽积木块 (HTML5 DnD)
- ✅ Calendar 拖动 planned workout 到其他天
- ❌ **没有 modifier 拖拽** — 用户想"周二强度课复制到周日"复刻, 必须 Library 找 → Calendar 拖两步
- ❌ Library 没法拖到 Calendar (拖拽源只有 Library 内部)

### 1.3 右键菜单 (context menu)

**TP 做法**:
```
右键 workout card  → 跳过 Quickview, 直接弹菜单 (Edit / Duplicate / Move / Delete / ...)
右键日列 header    → 弹 "这一天加新 workout / 复制 / 粘贴 / 全部清空"
右键周汇总        → 弹 "复制整周 / 粘贴到其他周 / 锁定周 / 删除周"
Mac 等价: Ctrl + Click
```

TP 用户原话: "Less digging, fewer clicks, faster edits."

**V0.8.2 现状**:
- ❌ **全项目 0 处 `onContextMenu`** — 我刚 grep 过, 完全没有
- ✅ ActivityDetail / Library 等页面双击进详情 (但不是右键菜单)

### 1.4 Mass Copy / Paste / Shift (Shift + Click 范围选)

**TP 做法**:
```
1. 点 周一日期 header
2. Shift + 点 周日日期 header → 蓝高亮整周
3. 弹菜单 → Copy
4. 点目标周 → Paste → 整周 workout 复制粘贴完
```

这是 TP 教练功能里用户"loudest gasp" 之一, 即使是运动员自训也常用 (复制过去某周模板)。

**V0.8.2 现状**:
- ❌ Calendar 不能选日期范围
- ❌ 没有 shift+click 行为
- ❌ 没有 mass copy/paste
- ⚠️ Library 有 copy plan (单 workout 复制), 不是范围

### 1.5 Week Controls (周汇总三点菜单)

**TP 做法**: Calendar 周汇总行右侧三点, 弹菜单:
- Copy / Paste / Cut / Hide / Lock / Shift / Delete **整个周**

用途: 教练快速"复制上周 + 微调" = 新一周, 比手动拖 N 个 workout 快 5 倍。

**V0.8.2 现状**:
- ❌ 没有周汇总视图 (Calendar 是月历)
- ❌ 没有"整周复制"概念

### 1.6 Recurring Workouts (循环训练)

**TP 做法**:
```
点 + → Does not repeat → 选每周一三五 + 90 天 → 保存
→ 90 天内每周一三五自动出现同一个 workout
```

**V0.8.2 现状**:
- ❌ Calendar 只能加单次, 无"每周重复"字段
- ⚠️ Builder 是单次 workout, 不是 recurring template

### 1.7 即时保存 (无 Save 按钮)

**TP 做法**: 改 workout 卡片的标题 / TSS / 备注, 输入完失焦即保存, **没有"保存"按钮**。

**V0.8.2 现状**:
- ✅ Builder 有 (Cmd+S)
- ❌ Calendar 编辑 workout 卡 (拖动改日) 没确认按钮但有时要等
- ❌ Profile 编辑完要点"保存"按钮 (V0.8.2 改过自动保存, 但其他字段呢?)
- ❌ Library workout 编辑要弹窗保存

### 1.8 Layout 自定义 (Calendar 显示什么 metric)

**TP 做法**: Calendar 右上齿轮 → 选显示哪些 metric (TSS / HR / Power / Cadence / Distance / ...), drag from Available → In Use。

**V0.8.2 现状**:
- ❌ Calendar 是固定布局, 不能让用户挑显示什么
- ⚠️ Dashboard 可加 widget (不是 Calendar)

---

## 2. TP 操作痛点 (我们要避免)

### 2.1 不要做 Premium Paywall 阻断核心操作

**TP 真实用户差评** (iOS App Store 评论):

> "Wanted to switch my workout plan around for different days within the same week so I switched to the paid plan. Ultimately, I regret it. It will allow you to work ahead in the week, but only if you execute the workout on rest day. If there is a different planned workout on the day you swap, it will show you as having missed one of the two workouts, even if you eventually accomplish both."

> "Free is alright; paid is not worth it."

**结论**: 我们的策略 ✅ (开源 + 本地, 永远不做功能墙)

### 2.2 不要做 Mobile UX Clunky

**TP 真实用户差评**:

> "TrainingPeaks is not that. The mobile app is clunky and crowded and honestly a bit stressful to use. It's not the worst ever, but it kind of gives off early 2010's vibes."

> "Good for just seeing the workouts and commenting and rating each one, but the organization and presentation of the interface could use some serious work."

> "If I could compare it to anything, it would be Microsoft's Sharepoint: a bloated steampunk ship lumbering through the seas of 'saying yes,' each person with an idea in a weekly meeting rewarded with an add-on feature that results in a Frankensteinian structure of clunk."

**启示**: 移动端简洁度 > 功能密度。我们 V0.8.2 移动端没专门优化 (Vite + Tailwind 自适应), V0.9.x 应该单独评估。

### 2.3 不要做加载慢

**TP 真实用户差评**:

> "Crazy long loading times ... Today it took 47 minutes to load, only then to tell me that it needed an update."

> "Unusably slow and laggy on iPhone. Trying to view and update workouts on iPhone is unbearably slow. Can't even update things like TSS because the keyboard won't show up."

> "Consistently fails to pull Apple Watch workouts ... Often fails to pull TSS even though Apple Watch clearly records it. ... 20% or the time."

**启示**: Vite build 已经快 (38s build, 1.5MB assets), 但要注意:
- 单页不能引过大依赖 (vendor-charts 已经 434KB, 不要再加 d3 / 其它)
- API 慢要给 skeleton / loading (V0.8.2 部分做了, 不够全)
- iOS Safari 兼容 (滚动 / 键盘弹起)

### 2.4 不要让入口藏太深

**TP 真实用户差评**:

> "Nevertheless, it still requires a bunch of poking around to figure out where certain metrics are and how to view them, none of which is particularly intuitive."

> "It's completely stagnated in new features for 5 years, they only started to work again in anything nice in the last year."

> "First impression is that this app (web, iOS, iPadOS) needs serious modernisation and improvements in intuitiveness."

**启示**: 所有主功能 ≤ 2 次点击可达。我们的 Sidebar 5 分组做得 OK, 但有些二级功能在 Profile 内嵌 3-4 层 (e.g. 设置 → 区间 → 修改 → 保存)。可以考虑:
- 把"今日训练" / "FTP 测试" / "导入" 这种高频功能放成 quick action card (Dashboard 顶部)
- 设置拆 flat, 不嵌套

### 2.5 不要做 Steep Learning Curve

**TP 真实用户差评**:

> "It's a bit like learning a new language. Not just the metrics and analysis of the workout, but the opening of hidden doors and drawers to find everything you need."

> "You shouldn't need a user guide to use an app or technology, it should just be intuitive. TrainingPeaks is not that."

**启示**: V0.8.2 KB 已经有 359 docs, 这是我们的优势。但**功能发现**要靠 in-app hint / 空状态提示 / 首次访问 tooltip, 不要让用户去翻 KB 文档。

---

## 3. V0.8.2 操作维度差距清单 (按改造性价比排)

### 🔴 P0 (用户每天用、改动小、价值高)

#### P0-1: 全局键盘快捷键 (Cmd+1/2/3/4 切页)

**改动量**: 🟢 小 (50 行)
- `apps/web/src/hooks/useGlobalShortcuts.ts` (新)
- 在 `App.tsx` 注册
- 监听 Cmd/Ctrl + 1/2/3/4/5 (按 Sidebar 顺序)

**价值**: ⭐⭐⭐⭐⭐ 高频用户每天切 20+ 次

#### P0-2: Calendar 右键菜单 (workout / 日 header)

**改动量**: 🟡 中 (200 行)
- `apps/web/src/components/ContextMenu.tsx` (新通用组件)
- CalendarPage 给 planned / actual 卡片加 `onContextMenu`
- 弹: Edit / Duplicate / Move to Today / Delete / Open Detail

**价值**: ⭐⭐⭐⭐⭐ 操作密度高

#### P0-3: 即时保存 (Profile / Library / Calendar 编辑)

**改动量**: 🟢 小 (60 行, debounce auto-save)
- 用 react-hook-form watch + debounce 触发 save
- 显示 "Saving..." / "Saved ✓" 微指示

**价值**: ⭐⭐⭐⭐ 用户感知强

#### P0-4: Calendar C+拖复制 modifier

**改动量**: 🟢 小 (30 行)
- CalendarPage onDragStart 检测 event 状态 + C key
- 弹 hint tooltip "按住 C 复制"

**价值**: ⭐⭐⭐⭐

### 🟡 P1 (价值高但改动中等)

#### P1-1: Shift+click 范围选 (Calendar 日期范围)

**改动量**: 🟡 中 (150 行)
- 选中范围后弹 "Copy / Paste / Shift / Delete" 操作栏
- 跟 Week Controls 配套

**价值**: ⭐⭐⭐⭐

#### P1-2: Week Controls (Calendar 周汇总三点菜单)

**改动量**: 🟡 中 (200 行)
- 周汇总行加三点菜单
- 操作: Copy Week / Paste Week / Clear Week / Lock Week

**价值**: ⭐⭐⭐

#### P1-3: Recurring Workouts

**改动量**: 🟡 中 (300 行)
- 后端: `recurring_pattern` 字段 (RRULE 简化版, 支持"每周一三五 / 共 8 周")
- 前端: Calendar 创建 workout 时选 Recurring
- 引擎: 每天 0 点自动展开未来 14 天

**价值**: ⭐⭐⭐⭐ 长期留存

### 🟢 P2 (锦上添花)

#### P2-1: Layout 自定义 (Calendar 显示哪些 metric)

**改动量**: 🟡 中 (200 行)
- 齿轮按钮 + 弹窗
- drag from Available → In Use
- 持久化到 profile.preferences

**价值**: ⭐⭐⭐

#### P2-2: GlobalSearch 加 Action 命令 (Cmd+K 现在只搜, 不执行命令)

**改动量**: 🟢 小 (80 行)
- Cmd+K 不仅搜内容, 还搜动作: "新建训练"、"跳到 Builder"、"导入 FIT"...
- 输入 "> 执行命令" 模式

**价值**: ⭐⭐⭐

#### P2-3: ActivityDetail / Workout 详情 Cmd+Enter 快速评论

**改动量**: 🟢 小 (20 行)
- 详情页 RPE / 备注输入框, Cmd+Enter 提交

**价值**: ⭐⭐

### ⚪ 不做

| 特性                  | 不做理由                                                  |
|----------------------|---------------------------------------------------------|
| Dual Calendar         | 单人项目, 不需要双日历对照 |
| Premium Paywall       | 我们开源 + 本地, 永远不做 |
| Coach-side 操作       | 不做教练功能 |

---

## 4. 操作维度: TP vs V0.8.2 横向对比 (速览)

| 操作维度                 | TP    | V0.8.2 | 差距        |
|------------------------|-------|--------|-----------|
| 全局键盘快捷键          | ⭐⭐⭐⭐⭐ | ⭐     | 4 星      |
| Modifier 拖拽 (C+拖)   | ⭐⭐⭐⭐  | ❌     | 4 星      |
| 右键菜单                | ⭐⭐⭐⭐⭐ | ❌     | 5 星 (全无) |
| 即时保存                | ⭐⭐⭐⭐  | ⭐     | 3 星      |
| Mass Copy/Paste        | ⭐⭐⭐⭐  | ❌     | 4 星      |
| Recurring Workouts     | ⭐⭐⭐⭐  | ❌     | 4 星      |
| Week Controls          | ⭐⭐⭐   | ❌     | 3 星      |
| 拖拽 (workout 移动)    | ⭐⭐⭐⭐  | ⭐⭐⭐   | 1 星 (有但 modifier 缺) |
| Builder 撤销重做        | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 已追平 ✅  |
| Layout 自定义           | ⭐⭐⭐   | ❌     | 3 星      |
| 操作"自然感"            | ⭐⭐⭐   | ⭐⭐⭐⭐  | 我们反而好 ✅ (TP 慢/卡) |

---

## 5. 改造路线图 (建议)

### V0.8.3 阶段 1: 操作流速提升 (1-2 周)

只改操作不改功能:

1. **P0-1 全局快捷键** — Cmd+1/2/3/4 切页 (50 行, 1 小时)
2. **P0-3 即时保存** — Profile / Library 编辑 auto-save (60 行, 半天)
3. **P0-4 C+拖复制** — Calendar modifier (30 行, 1 小时)
4. **P0-2 右键菜单** — CalendarPage 卡片 + 日 header (200 行, 1 天)

### V0.8.4 阶段 2: 批量操作 (2 周)

5. **P1-1 Shift+click 范围选**
6. **P1-2 Week Controls**

### V0.9.x 阶段 3: 高级操作 (弹性)

7. **P1-3 Recurring Workouts** (后端 RRULE, 前端 UI)
8. **P2-1 Layout 自定义**
9. **P2-2 Cmd+K Action 命令**

---

## 6. 关键引用来源

| 引用                                          | URL                                                                                  |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| TP 官方: 5+ Calendar Efficiency Features     | https://www.trainingpeaks.com/coach-blog/speed-up-your-coaching-with-5-trainingpeaks-calendar-efficiency-features/ |
| TP 官方: Keyboard Shortcuts                  | https://help.trainingpeaks.com/hc/en-us/articles/38847458144013-Keyboard-Shortcuts |
| TP 官方: Move Workouts (拖拽 + Mass Shift)    | https://help.trainingpeaks.com/hc/en-us/articles/204072164                           |
| iOS App Store 524 评论吐槽 (TP 真实用户差评) | https://appshunter.io/ios/app/408047715/reviews                                       |
| 真实用户吐槽 (Mobile clunky / Sharepoint)     | https://believeintherun.com/trainingpeaks-training                                    |
| intervals.icu 论坛用户讨论 "为什么离开 TP"     | https://forum.intervals.icu/t/trainingpeaks-stick-with-it-or-not/86465/6              |
| 用户吐槽 (Premium paywall + 加载慢)         | https://apps.apple.com/gb/app/trainingpeaks-plan-lift-train/id408047715              |

---

## 7. 我们的优势 (相对 TP 的反向)

TP 操作很全, 但有几个**反向优势** 我们其实已经做对了, 不要倒退:

1. ✅ **本地响应** — 我们没有"47 分钟加载", Vite build + FastAPI 本地 < 1s
2. ✅ **无 Paywall** — 所有功能可用, 不收费
3. ✅ **Builder 撤销重做** — TP 的 Builder 编辑后没听用户说有 undo, 我们做了 (BuilderPage Ctrl+Z/Y)
4. ✅ **AI Chat** — TP 没有 AI 教练对话, 这是我们的差异化
5. ✅ **KB 内嵌** — 359 docs 离线可用, TP 用户要去 KB 网站

**底线**: V0.8.3 改造时, 不要为了对标 TP 反而变慢 / 变复杂 / 引入 paywall 思维。

---

## 8. 总结

TP 的 **操作优势** 是 **键盘 + 拖拽 modifier + 右键 + 即时保存**, 不是功能数量。
V0.8.2 的 **操作劣势** 在 Calendar + 全局层面 (Builder 已经 70%), **完全不需要新功能**, 只需要把现有交互做细。

**预计 V0.8.3 1-2 周, 全部改 P0 + P1-1 + P1-2, 就能让操作密度追平 TP 的核心操作**。
然后 V0.8.4 / V0.9.x 再做 Recurring + Layout 自定义等锦上添花项。

---

**报告结束。这次只谈操作, 不谈功能。**