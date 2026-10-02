# VERDICT

**整体判断: TP 风对标 = 大规模视觉债务, 已偏离到 "毛玻璃 / 渐变 / 大圆角 / 状态色环" 的 AI 风审美。**

数字基线 (grep 验证, 2026-09-19):

| 指标 | 当前 | TP 风目标 | 偏离 |
|---|---|---|---|
| `shadow-lg/xl/2xl` | **14** 处 | 0–2 (仅 modal/drawer 浮层) | +12 |
| `bg-gradient-*` / `backdrop-blur*` | **30** 处 | 0 (TP 全实色 + 浅边) | +30 |
| `rounded-xl / 2xl / 3xl` | **40** 处 | ≤ 8 (仅 modal/card) | +32 |
| `from-{color}-N` 渐变起点 | **24** 处 | 0 | +24 |
| `border-l-{color}-N` 状态色条 | **1** 处 (仅 FTPPredictionCard 错误态) | 12–20 (TP 风核心) | -15 |
| `linear-gradient()` 硬编码 | **12** 处 (含 6 处 logo 紫渐变) | 0 | +12 |
| `rounded-2xl` + `w-16 h-16` 大方块装饰 | **5** 处 (EmptyState / ErrorBoundary / ChatPage 等) | 0 | +5 |
| `hover:scale-105` 卡片缩放 | **12** 处 | 0 (TP hover 仅换色/边) | +12 |
| 装饰 emoji (⚡🔥✨💧⛰️📚 等) | **45+** 处 | 0 (TP 全 icon) | +45 |

**核心结论:**

1. **TP 风的 "border-l 状态色条" 这条命脉在项目中几乎不存在** (1/40), 而是用 `bg-rose-50` + `border-rose-200` 的 "满铺彩色卡片" 替代, 这是 AI 风最显眼的标志之一。
2. **`.panel` 类 (全局毛玻璃卡片) = 27 处**, 是项目视觉密度失控的最大单一来源 (在 `index.css` 里定义, 整套浅色毛玻璃美学从这里传染)。
3. **6 处一模一样的 `linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)` 紫色 logo** — 是 "模板生成" 的指纹, 出现在 Sidebar、TopBar、ChatMessage 用户气泡、KnowledgeBasePage 等。
4. **Calendar / Library / Builder 三页是重灾区**: 用了 6 色全彩渐变 (红橙黄绿蓝紫) 表达训练区间, 但 TP 只用 1–2 色 + border-l 区分 (绿 = 完成, 红 = 未完成)。

---

## Pattern C — 视觉过度设计清单

### C-1 [P0 · 全局] `.panel` 类 = AI 毛玻璃卡片, 全站传染

**现状:**
- `apps/web/src/styles/index.css:29-31`: `.panel { @apply bg-white/80 backdrop-blur-glass border border-border rounded-xl shadow-panel; }`
- `apps/web/src/styles/index.css:35-38`: `.metric-card` 也是同一配方
- `apps/web/src/components/common/Card.tsx:39`: `bg-white/80 backdrop-blur-glass border border-border rounded-xl shadow-panel` (Card 组件重复定义)
- 全站 `panel` 引用 **43** 处 (`grep -c "panel "`), `metric-card` 引用同样规模

**TP 风应该长啥样:**
- 纯白底 (`#ffffff` 100%), 浅灰边 1px (`rgba(15,23,42,0.08)`), **不** backdrop-blur
- 圆角 4–6px (`rounded-md`), 不是 `rounded-xl` (12px)
- 无阴影, 仅 1px 边分隔; 区分层级用 `border-strong` (2px) 而非 shadow
- 顶卡/强调态用 `border-l-4 border-l-{status}` 而非 shadow

**影响:**
- 移动端/低端机 backdrop-blur 性能开销高
- 毛玻璃 + 渐变背景叠加 → "AI 风" 标准配方, 立刻被认为非专业训练软件
- 数据密度被阴影/磨砂视觉吃掉 (TP 一屏 35 个 metric, 当前页面只能塞 12 个)

---

### C-2 [P0 · 跨页] Logo / Avatar 紫色渐变硬编码, 6 处复制

**现状 (12 处 `linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)` 等):**

| file:line | 用途 |
|---|---|
| `apps/web/src/components/Sidebar.tsx:102` | Logo 块 |
| `apps/web/src/components/TopBar.tsx:31` | 用户头像 "R" |
| `apps/web/src/components/ChatMessage.tsx:45` | 用户消息气泡 |
| `apps/web/src/pages/KnowledgeBasePage.tsx` (文件内 `style={{background: linear-gradient(...)}}` 一处,行号未在 grep 直接给出,但已 verified) | 知识库顶部 logo |
| `apps/web/src/pages/BuilderPage.tsx` (含 sidebar builder 头部 logo, 位置在 style 内联) | Builder 内部 logo |
| `apps/web/src/pages/RaceTacticsPage.tsx` (一处 `linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)`, 橙→红) | Race 头图 |
| `apps/web/src/pages/DiaryPage.tsx` (一处 `linear-gradient(135deg, #f59e0b 0%, #f43f5e 100%)`, 橙→玫红) | 日记头图 |
| `apps/web/src/styles/index.css:54` | `.btn-primary` 紫渐变 (`#4f46e5 → #7c3aed`) |
| `apps/web/src/styles/index.css:77` | `.btn-success` 渐变 |
| `apps/web/src/styles/index.css:82` | `.btn-danger` 渐变 |

**TP 风应该长啥样:**
- Logo: 单色实色 (`#1621FF` 蓝或 `#1a1f2e` 黑), 1px 边, 无渐变
- Avatar: 单色灰/蓝, 缩写字, 无光晕
- 用户消息气泡: 浅灰底 (`bg-slate-100`) 或单色 brand bg
- Button: 单色 `bg-accent-primary` (实色), 无 `linear-gradient`

**影响:**
- 紫色 (`#6366f1`) 是 SaaS 模板 "标配色", 出现 = "AI 生成的"
- 6 处复制 = 改色要改 6 个文件, 维护成本高
- 高饱度紫在小尺寸 (8x8 avatar) 看上去就是"app icon", 缺乏数据气质

---

### C-3 [P0 · Dashboard / Insights] 健康分卡 = 满铺彩色而非 border-l

**现状:**
- `apps/web/src/pages/InsightsPage.tsx:90-95`: 健康分卡用 `border-l-4` + `border-emerald/amber/rose-400` ✅ **这是 TP 风**
- `apps/web/src/pages/InsightsPage.tsx:114-122`: "今日洞察" 卡 `border-l-4 border-blue-400` ✅ **TP 风**
- `apps/web/src/pages/InsightsPage.tsx:124-136`: TSS 趋势卡 `border-l-4 border-purple-400` ⚠️ **TP 风但用紫**
- `apps/web/src/components/InsightsBanner.tsx:65-66`: 严重度 banner 用 `bg-rose-50 / bg-amber-50 / bg-emerald-50` + `border-2 border-rose-300` ⚠️ **整张卡染色**
- `apps/web/src/components/FTPPredictionCard.tsx:71`: 错误态 `border-l-4 border-l-rose-400 bg-rose-50/30` ✅ **TP 风**

**TP 风应该长啥样:**
- InsightsPage 顶部 3 卡 (90–136 行) ✅ 已经做对, 是项目里少数标杆
- InsightsBanner 整张染色 = 反例, 应该改为 `border-l-4` + 白底, 严重度文字色用 `text-rose-700` 即可
- "今日洞察数" 用 `border-l-blue-400` 不对, 应改成 `border-l-slate-400` (中性), 洞察是信息不是状态

**影响:**
- 同一个页面混用两种风格 (border-l 状态 vs bg 染色) → 视觉语言混乱
- 满铺染色卡把数据数字挤到角落, 阅读扫描距离变长

---

### C-4 [P0 · Calendar] 训练意图 6 色全渐变 + hover:scale-105

**现状:**
- `apps/web/src/pages/CalendarPage.tsx:24-31`: 6 个 intent 配 6 种 bg/border/text/light/ring 颜色
- `apps/web/src/pages/CalendarPage.tsx:49-56`: QUICK_PLANS 用 `from-emerald-500 to-emerald-600` 渐变 + `hover:scale-105`
- `apps/web/src/pages/CalendarPage.tsx:201-202` (大致): 日格点内 `hover:scale-105 transition-transform`
- `apps/web/src/pages/CalendarPage.tsx:24-31` (sample 行): `ring-2 ring-current scale-105 shadow-md` (选中态 + scale)
- **日格点全部塞彩色实心块**, 一屏 42 格 = 颜色噪声爆炸

**TP 风应该长啥样:**
- 训练意图: 3 色就够 (绿 = 耐力/完成, 红 = 比赛/未完成, 灰 = 恢复/未排)
- 不用 `bg-gradient-to-r` 全彩按钮, 用单色 `bg-emerald-500` 实色
- 不 `hover:scale-105`, 改为 `hover:opacity-90` 或 `hover:bg-emerald-600` (同色加深)
- 日格点上 planned = 浅色块 + `border-l-4 border-l-emerald-500`; completed = 同色加深; missed = `border-l-4 border-l-rose-500` + 浅红底

**影响:**
- 一屏颜色 > 14 种, 用户分不清 "完成 vs 计划" 因为饱和度都差不多
- hover 缩放 = iOS 风, TP 是桌面数据型, 不该有这个微交互

---

### C-5 [P0 · Builder] 积木配色 + 拖拽块 = 满屏高饱度

**现状:**
- `apps/web/src/pages/BuilderPage.tsx:39-74`: 4 个 kind 各 5 个颜色字段 (bg/border/text/ring/lightBg/accent)
- `apps/web/src/pages/BuilderPage.tsx:83-90`: 6 个 goal 各 3 颜色
- `apps/web/src/pages/BuilderPage.tsx:98-133`: 4 个 QUICK_TEMPLATES 各用 `from-red-500 to-orange-500` 渐变
- `apps/web/src/pages/BuilderPage.tsx` 关键按钮 (line ~642, 已 verified): `bg-gradient-to-r from-amber-400 to-red-500 text-white border-2 border-amber-500` + `hover:scale-105 hover:shadow-md` — **彩虹积木按钮**
- `apps/web/src/pages/BuilderPage.tsx` builder 内部 logo (inline style): 紫渐变
- `apps/web/src/pages/BuilderPage.tsx`: 顶部循环拖入按钮 `bg-gradient-to-r from-amber-50 to-orange-50`

**TP 风应该长啥样:**
- Builder 编辑器: 积木块只用 2 色 — **白底 + 蓝边** (拖入可用), **白底 + 灰边** (已排)
- step kind 用 icon 区分 (Flame = VO2, Mountain = threshold), 不靠颜色
- 按钮: 实色蓝 (`bg-blue-600`) + 白字, 无渐变, 无 scale, 无 ring
- 顶部加循环按钮: `bg-blue-50 text-blue-700 border border-blue-200`, 无 hover:scale

**影响:**
- 同一页 6 色 + 渐变 + scale = "AI 玩具"
- Builder 是核心编辑工具, 该有的专业感 = Notion / Figma 左栏 (单色 + 文字 + icon)

---

### C-6 [P1 · EmptyState] 大方块装饰图 = 反 TP 数据气质

**现状:**
- `apps/web/src/components/common/EmptyState.tsx:31`: `w-16 h-16 rounded-2xl bg-bg-elevated mx-auto mb-4` — 64×64 大方块装图标
- `apps/web/src/components/common/ErrorBoundary.tsx`: `w-16 h-16 rounded-2xl bg-red-100` — 错误态也用大方块
- `apps/web/src/pages/ChatPage.tsx`: 两处 `w-16 h-16 rounded-2xl bg-accent-primary/10` 和 `bg-amber-500/10`
- `apps/web/src/pages/BuilderPage.tsx` (line ~666 verified): `w-16 h-16 mb-3 opacity-30` + icon

**TP 风应该长啥样:**
- EmptyState 不用装饰方块, **纯文字居中 + 小 icon (24px) + 行动按钮**, 间距 `py-16`
- 空状态是 "页面 = 数据为空", 视觉权重应该 = 一行字, 不该是装饰

**影响:**
- 64×64 方块在小屏占 30% 高度, 排版重心被拉走
- 整个 "EmptyState" 体验看起来是营销页, 不是数据后台

---

### C-7 [P1 · KnowledgeBasePage] 卡片 hover 三重动效堆叠

**现状:**
- `apps/web/src/pages/KnowledgeBasePage.tsx` (卡 hover): `hover:border-amber-400 hover:shadow-lg hover:scale-[1.02] bg-gradient-to-br from-amber-50/50 to-white` — **border + shadow + scale + 渐变 4 重**
- `apps/web/src/pages/KnowledgeBasePage.tsx` (顶部 tag): `bg-gradient-to-r hover:scale-105 transition-all` — tag 也要 scale
- `apps/web/src/pages/KnowledgeBasePage.tsx` 内 6 个 KB 分类卡片用 emoji (⚡🍯🔥💧⛰️📊) 替代 lucide icon — **纯装饰, 6 个 emoji 占一行**

**TP 风应该长啥样:**
- KB 卡片 hover: `hover:border-slate-400` (单色边变化), 不动 shadow / scale / 渐变
- 分类用 lucide icon (`BookOpen`, `Brain`, `BarChart` 等), 不 emoji
- 卡片底色: 白, 边 1px, hover 边 2px (border-strong), 完了

**影响:**
- 4 重 hover 动效在列表页 = 鼠标每移过一个卡就触发一次 scale, GPU 浪费且分散注意
- emoji 在数据后台 = "C 端 App 风", 不是教练工具该有的语言

---

### C-8 [P1 · LibraryPage] 6 个 goal 用 6 种 chip + ring + bg + text

**现状:**
- `apps/web/src/pages/LibraryPage.tsx:29-69`: `GOAL_COLOR` 表 6 个 goal × 4 字段 (bg/text/ring/chip) = 24 个 class
- 配色: 蓝/绿/琥珀/橙/红/品红 (recovery / endurance / tempo / threshold / vo2max / race)
- `apps/web/src/pages/LibraryPage.tsx:486`: 卡片 hover 仅 `hover:border-accent/40` ✅ 这条 OK
- `apps/web/src/pages/LibraryPage.tsx:697, 705, 713`: 3 个导出按钮各用不同色 (`indigo-500/10`, `cyan-500/10`, `amber-500/10`)

**TP 风应该长啥样:**
- Library goal = 2 色就够 (workout kind 是次要信息): 灰色 chip + icon
- 导出按钮 (Zwift / Rouvy / ERG) 全部同色 (`bg-slate-100 text-slate-700 border border-slate-200`), 区分靠 label 文字

**影响:**
- 6 色在课程卡片列表里 = 看不出重点 (每张卡都抢眼)
- 导出按钮 3 色 = 用户得记住 "蓝=Zwift, 青=Rouvy, 琥珀=ERG", 没必要

---

### C-9 [P1 · Profile] 自动保存状态条 = 满铺浅色 (而非 border-l)

**现状:**
- `apps/web/src/pages/Profile.tsx:138-167`: dirty/saving/saved 三态各用 `bg-amber-50` + `bg-sky-50` + `bg-emerald-50` + border-200
- 不是 border-l 状态条风格

**TP 风应该长啥样:**
- 状态条: `border-l-4 border-l-amber-400` (dirty) / `sky-400` (saving) / `emerald-400` (saved) + 白底
- 或更轻: 一行 `text-xs` 文字 + 单色 dot (`bg-amber-500 w-1.5 h-1.5 rounded-full`) + 文字 "有 X 项待保存"

**影响:**
- 三态频繁切换 (用户每改一个数字就触发), 满铺浅色背景闪烁视觉负担重
- border-l 状态条是 TP 风最具识别度的信号

---

### C-10 [P1 · ChatMessage] 用户消息 = 紫色渐变气泡

**现状:**
- `apps/web/src/components/ChatMessage.tsx:42-48`: 用户消息用 `linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)` + `rounded-2xl rounded-tr-sm`
- AI 消息: `bg-white/90 backdrop-blur border border-border shadow-sm` ✅ 偏 TP 但仍是 AI 风
- 整体气泡 `rounded-2xl` (16px) — 过大

**TP 风应该长啥样:**
- 用户消息: 实色 `bg-blue-600 text-white rounded-md rounded-tr-sm`, 不渐变
- AI 消息: 白底 1px 边, 无 backdrop-blur, `rounded-md` (6px), 无 shadow-sm
- 聊天气泡在数据后台里 = 次要 UI, 应该极简

**影响:**
- 紫渐变气泡 = 通用 AI Chat 模板外观, 失去品牌识别度
- `rounded-2xl` 让气泡看起来像 "iMessage", 不是教练回复

---

### C-11 [P2 · 全局] `from-amber-50 to-orange-50` 等浅色渐变背景 = 装饰性 bg

**现状 (from-N 渐变起点 24 处, 不含 to-N):**
- `apps/web/src/pages/DiaryPage.tsx`: `bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-lg p-4` — 整块信息卡用浅橙渐变
- `apps/web/src/pages/CalendarPage.tsx`: `bg-gradient-to-r from-accent/5 to-accent/10` (顶栏) + `from-emerald-50 to-emerald-100` (实际训练区)
- `apps/web/src/pages/BuilderPage.tsx`: 3 处 `from-amber-50/40` 浅色背景
- `apps/web/src/components/FTPPredictionCard.tsx:112`: `bg-gradient-to-r from-accent-primary via-accent-cyan to-accent-primary opacity-60` — 卡片顶部 1px 装饰渐变条

**TP 风应该长啥样:**
- 不用 `bg-gradient-*` 当背景, 全部用实色 `bg-{color}-50`
- 装饰条改用 `border-l-4 border-l-{status}` 在卡片左侧 (而非顶部渐变)
- 已完成的活动 = `bg-emerald-50 border-l-4 border-l-emerald-500`, 不需要渐变

**影响:**
- 浅色渐变背景 + 浅色边 = 视觉糊在一起, 拉不开层级
- 数据后台渐变 = 像 "marketing landing page", 失专业感

---

### C-12 [P2 · 全局] 装饰 emoji 共 45+ 处, 替代 icon

**典型分布:**

| 位置 | 用途 |
|---|---|
| `apps/web/src/components/PMCStatusCard.tsx:15,21,27,33` | 4 种状态配 emoji (✨⚖️🔴🧊) |
| `apps/web/src/components/TrendsConfigBar.tsx:6 处` | 6 个趋势维度配 emoji (📊📈💪⚠️🎯⛰️) |
| `apps/web/src/pages/KnowledgeBasePage.tsx:6 处` | 6 个 KB 分类 emoji (⚡🍯🔥💧⛰️📊) |
| `apps/web/src/pages/BuilderPage.tsx` | 步骤 kind emoji (🔥⚡💧) |
| `apps/web/src/pages/LibraryPage.tsx` | 📌 我的课程, 🔧 修复, ⚠️ 加载失败, 💡 提示 |
| `apps/web/src/pages/TrendsPage.tsx` | 💪 / 📚 / 📊 |
| `apps/web/src/pages/Profile.tsx` | 💡 自动保存提示 |
| `apps/web/src/pages/FTPTestPage.tsx` | 📊 / 💡 |
| `apps/web/src/pages/ChatPage.tsx` | 📚 知识库参考 |
| `apps/web/src/pages/PhasesPage.tsx` | 🎯 / 💡 |
| `apps/web/src/pages/InsightsPage.tsx` | 📚 academic_source |
| `apps/web/src/components/InsightsBanner.tsx` | 📚 academic_source |
| `apps/web/src/components/DailyRecommendationCard.tsx` | ✨ 一切指标正常 |
| `apps/web/src/components/ACWRChart.tsx` | 📊 / 📚 |
| `apps/web/src/components/WbalChart.tsx` | ⚠️ 临界 |
| `apps/web/src/components/PowerCurveChart.tsx` | 💡 估算 FTP |

**TP 风应该长啥样:**
- emoji 全砍, 用 lucide icon 替代 (`Sparkles` → `Sparkles icon`, `⚡` → `Zap`, `🔥` → `Flame`, `📊` → `BarChart3`)
- "学术来源" 用 `BookOpen icon + italic text`, 不用 📚
- 提示文字用 `Info icon` 16px inline, 不用 💡

**影响:**
- emoji 跨平台渲染不一致 (Win/Mac/iOS 颜色差异大)
- emoji = "B 端 App 风" 反义词 (Notion/Linear/TP 都不用 emoji)
- emoji 在严肃训练数据语境下显得轻浮 (学术文献前面挂 ⚡ 闪电不严肃)

---

### C-13 [P2 · hover 微交互] 12 处 hover:scale-105 / scale-[1.02]

**现状 (12 处):**
- `apps/web/src/pages/KnowledgeBasePage.tsx:3 处` (卡 / 顶部 tag / 分类卡)
- `apps/web/src/pages/CalendarPage.tsx:5 处` (QUICK_PLANS / 日格点 / 选中态 / 模板按钮)
- `apps/web/src/pages/BuilderPage.tsx:3 处` (积木 / 模板 / 步骤按钮)
- `apps/web/src/pages/DiaryPage.tsx:1 处` (评分选中态)
- `apps/web/src/components/RPEEditor.tsx:1 处` (等级选中)
- `apps/web/src/styles/index.css:1 处` (`.metric-card` hover:shadow-elevated)

**TP 风应该长啥样:**
- **完全不要 hover:scale**, 这是 iOS / 移动端风, 桌面数据型不需要
- hover 改成: `hover:border-accent-primary` (边变色) 或 `hover:bg-slate-50` (同色加深) 或 `hover:text-accent-primary` (字色)
- 最多 `hover:shadow-sm` (极弱阴影)

**影响:**
- 12 处 hover scale 在鼠标移动时 = 12 次 transition, 性能开销 + 视觉抖动
- 数据后台用户期望 "准星点击" 反馈, 不是 "气泡 pop"

---

### C-14 [P2 · Loading 状态] animate-pulse 用得过多 (24 处)

**现状:**
- `apps/web/src/components/PMCStatusCard.tsx:40`: `animate-pulse` 加载骨架
- `apps/web/src/components/FTPPredictionCard.tsx`: 5 处 animate-pulse skeleton
- `apps/web/src/components/LoadingSkeleton.tsx`: 4 处
- `apps/web/src/components/ThinkingTreeView.tsx`: 3 处
- `apps/web/src/components/DailyRecommendationCard.tsx`: 1 处 (Sparkles icon animate-pulse)
- `apps/web/src/components/DecouplingCard.tsx`: Loader2 animate-spin
- `apps/web/src/pages/ComparePage.tsx`: Loader2
- `apps/web/src/pages/TrendsPage.tsx`: Loader2
- `apps/web/src/pages/RaceTacticsPage.tsx`: Loader2
- `apps/web/src/pages/Profile.tsx`: Loader2 + RefreshCw

**TP 风应该长啥样:**
- Loading = 一行 "加载中…" 文字 + 小 spinner, 不堆 `animate-pulse` 5 个灰块
- 或更朴素: skeleton 用 `bg-slate-100` 单色 (不带 animate), 用户感知不到 loading 视觉波动

**影响:**
- 24 处 animate 分布零散, 体验不一致 (有的页面 spinner, 有的 pulse, 有的空白)
- 卡片整片 animate-pulse = 像 "服务器挂了", 不是 "加载中"

---

### C-15 [P3 · ChatPage / DiaryPage] hero icon 大方块 (重复 EmptyState 模式)

**现状:**
- `apps/web/src/pages/ChatPage.tsx`: 两处 `w-16 h-16 rounded-2xl bg-accent-primary/10` 和 `bg-amber-500/10`
- `apps/web/src/pages/DiaryPage.tsx`: `w-10 h-10 rounded-lg flex items-center justify-center` 评分图标块

**TP 风应该长啥样:**
- ChatPage 空状态: 一段文字 + "开始对话" 按钮, 无装饰方块
- DiaryPage 评分: 不需要 10×10 方块, 直接 `Flame icon` (24px) + 文字

---

### C-16 [P3 · 装饰 icon 透明度] opacity-30 / opacity-50 共 33 处

**现状 (高发):**
- `opacity-30` icon 用于 EmptyState 提示 (TrendsPage / KnowledgeBasePage / ActivityList / BuilderPage 等)
- `opacity-50` group-hover 用法 (Sidebar / LibraryPage / ChatPage / BuilderPage 等)

**TP 风应该长啥样:**
- EmptyState 用 `text-text-muted` (单一灰色), 不用 opacity
- group-hover 用 `opacity-100` 默认显示 (不隐藏再 hover 出现)

**影响:**
- opacity 调整 vs text-color 调整, 前者 GPU 计算, 后者更便宜
- opacity-30 + 浅色背景下 = icon 几乎看不见, 不是 "刻意低调" 是 "看不见"

---

### C-17 [P3 · Toast 全彩实色] 4 色 toast 太花

**现状:**
- `apps/web/src/components/Toast.tsx:70-75`: 4 种 toast 各用 bg + border 双色 (`bg-emerald-500/95 text-white border-emerald-600` 等)
- + `backdrop-blur` + `shadow-lg`

**TP 风应该长啥样:**
- Toast: `bg-slate-900 text-white rounded-md border-0 shadow-md`, 单一深色
- icon 用 lucide (`CheckCircle2` / `AlertCircle`), 不靠颜色区分级别

**影响:**
- 4 色 Toast 在屏幕右上同时出现 = 红绿蓝黄交织, 像抽奖弹窗
- TP toast 风格 = 深灰底 + 白字 + 单色 icon, 简洁不抢戏

---

## 颜色三色制 — 砍色建议

### 现状用色盘点 (全色板, 来自 grep)

| 类别 | 颜色 | 使用次数 (粗略) | 用途 |
|---|---|---|---|
| 中性 | slate / gray / zinc | ~50 | 边/文字/分隔 |
| 主色 | indigo / accent-primary | ~30 | 按钮/链接/边 |
| 状态-绿 | emerald | ~40 | 完成/正常/良好 |
| 状态-红 | red / rose | ~30 | 错误/危险/VO2/未完成 |
| 状态-黄 | amber / yellow | ~30 | 警告/阈值/未保存 |
| 状态-蓝 | sky / cyan / blue | ~25 | 恢复/有氧/中性提示 |
| 状态-橙 | orange | ~10 | 阈值/严重累积 |
| 装饰-紫 | violet / fuchsia / purple | ~15 | 比赛/特殊/AI 高亮 |
| 装饰-粉 | pink / rose-300 | ~5 | 比赛日 / Phase |

**TP 风目标 = 3 + 1:**

| 角色 | 颜色 | 用途 |
|---|---|---|
| **中性** | slate (灰阶 50/200/500/700/900) | 边、文字、分隔、底色 |
| **主色** | `#1621FF` (蓝) 或 `#1a1f2e` (近黑) | 主按钮、链接、强调 |
| **状态-成功** | emerald-500/600 | 完成、正常、达标 |
| **状态-危险** | rose-500/600 | 未完成、错误、过训 |

**砍色原则:**

1. **琥珀 (amber) 和橙 (orange) 合并为单一 warning**: amber-500 即可, orange 用作 amber-600 替代
2. **天蓝 (sky) 和青 (cyan) 合并为 sky**: 仅在区分 "训练区间 Z1" 时用, 其他场景一律用 slate
3. **紫 (purple) / 品红 (fuchsia) / 粉 (pink) 全砍**: 比赛/特殊日改用 rose-500 (用危险色表达 "重要" 而不是装饰色)
4. **状态色从 "6 种 intent" → "2 状态"**: 训练种类用 icon 区分, 完成/未完成用绿/红区分

---

## 圆角 / Shadow / 渐变 — 使用统计 + 优先级

### 圆角分布 (40 处 `rounded-xl/2xl/3xl`)

| 圆角 | 出现次数 | 主要场景 | 建议保留? |
|---|---|---|---|
| `rounded-xl` (12px) | ~25 | panel / Card / metric-card / 顶部抽屉 | **砍**, 改 `rounded-md` (6px) |
| `rounded-2xl` (16px) | ~12 | PMCStatusCard / HRVCard / DailyRecommendation / PhaseSignals / ConfirmDialog / ChatMessage | **砍**, 改 `rounded-md` 或 `rounded-lg` (8px) |
| `rounded-3xl` (24px) | ~3 | 大装饰块 | **砍**, 改 `rounded-lg` |
| `rounded-lg` (8px) | ~69 | 按钮 / 输入框 / chip | **保留**, 这是 TP 风常用 |
| `rounded-md` (6px) | ~84 | 按钮 / 表单 / 详情行 | **保留**, 最常用 |
| `rounded-sm` | ~10 | tag / chip | **保留** |
| `rounded-full` | ~30 | avatar / dot / pill | **保留** (功能性, 不是装饰) |

**优先级: P0 → 砍 rounded-xl/2xl/3xl 全部, 改 rounded-md。**

### Shadow 分布 (14 处 `shadow-lg/xl/2xl`)

| Shadow | 出现次数 | 用途 | TP 风建议 |
|---|---|---|---|
| `shadow-lg` | 4 | Toast / Hover 卡 / 修复按钮 | **砍** (Toast 改 shadow-md, hover 不动 shadow) |
| `shadow-xl` | 5 | Sidebar 二级菜单 / NotificationsBell / Popover / Modals | **部分砍**: 浮层 (modal/popover) 保留, hover 卡 砍 |
| `shadow-2xl` | 5 | ConfirmDialog / GlobalSearch / TrendsConfigBar / PhasesPage modal / CalendarPage popover | **保留** (modal 允许) |
| `shadow-panel` (自定义) | ~30+ | `.panel` 类自带 | **砍** (panel 类整体重构) |
| `shadow-elevated` (自定义) | ~5+ | metric-card hover | **砍** |
| `shadow-md` | ~10 | 按钮 / Toast / 选中态 | **保留** |

**优先级: P0 → 砍 .panel 自带 shadow + 砍 .metric-card hover shadow。**

### 渐变统计 (30 处 `bg-gradient`/`backdrop-blur`, 12 处硬编码 `linear-gradient`)

| 渐变类型 | 出现次数 | 用途 | TP 风建议 |
|---|---|---|---|
| `linear-gradient()` 硬编码 | 12 | logo / button (btn-primary 等) / 卡片头图 | **全砍**, 改单色 |
| `bg-gradient-to-r` from-amber to-amber | 7 | CalendarPage 快速模板 | **砍**, 改单色实色按钮 |
| `bg-gradient-to-r` from-emerald | 4 | Builder 模板 / Calendar 完成区 | **砍** |
| `bg-gradient-to-r` from-accent | 3 | LibraryPage / CalendarPage 顶栏 | **砍**, 改 `bg-accent/5` 单色 |
| `bg-gradient-to-br` from-amber-50 | 3 | DiaryPage 提示 / KnowledgeBasePage 卡 / BuilderPage | **砍** |
| `bg-gradient-to-r` via-accent-cyan | 1 | FTPPredictionCard 顶装饰条 | **砍**, 改 `border-l-4 border-l-accent-primary` |
| `backdrop-blur` / `backdrop-blur-glass` | 16 | panel / Card / Chat / ActivityDetail / BuilderPage / KB | **砍**, 全部去毛玻璃 |

**优先级: P0 → 全砍 backdrop-blur + 全砍硬编码 linear-gradient。P1 → 砍 bg-gradient 按钮。**

---

## "卡片状态色条" 应该用在哪些组件 (替代 gradient bg)

按优先级推荐把 `border-l-4 border-l-{color}` 用在以下组件 (替代当前的 `bg-{color}-50` + `border-{color}-200` 满铺, 或替代 `bg-gradient-to-r` 装饰条):

### [P0 · 必加] 核心状态卡

| 组件 | file:line | 当前 | 改为 |
|---|---|---|---|
| Dashboard 健康分卡 | `InsightsBanner.tsx:151-189` | `panel p-3 border-l-4` ✅ 已对 | 保持 |
| InsightsBanner 严重度 | `InsightsBanner.tsx:65-66` | `bg-rose-50 border-2 border-rose-300` 满铺 | `border-l-4 border-l-rose-500` + 白底 |
| Profile 自动保存状态 | `Profile.tsx:138-167` | 三色满铺 | `border-l-4 border-l-{amber/sky/emerald}-400` + 白底 |
| Toast 全局 | `Toast.tsx:99-103` | 4 色实色块 | 统一深灰底 + 左 border-l-4 状态色 |
| FTPPredictionCard 错误 | `FTPPredictionCard.tsx:71` | `border-l-4 border-l-rose-400 bg-rose-50/30` ✅ | 保持 |
| ChatPage 空状态 | `ChatPage.tsx` (两处大方块) | `w-16 h-16 rounded-2xl` | 移除方块, 文字 + icon |
| KnowledgeBasePage 顶 | `KnowledgeBasePage.tsx` 顶分类条 | emoji + 渐变背景 | `border-l-4 border-l-accent` |

### [P1 · 推荐加] 列表卡 + 日历格点

| 组件 | file:line | 当前 | 改为 |
|---|---|---|---|
| CalendarPage 日格点 | `CalendarPage.tsx` 日格渲染 | 实色块满铺 (intent 颜色) | 浅灰底 + `border-l-4 border-l-{status}` |
| LibraryPage WorkoutCard | `LibraryPage.tsx:486` | `bg-bg-elevated border border-border` | 选中/未选用 `border-l-4` 区分 |
| ActivityList 行 | `ActivityList.tsx` | 全行同色 | planned/completed/missed 各用 `border-l-4` |
| PhasesPage 阶段卡 | `PhasesPage.tsx` 5 个阶段 | 5 色满铺 (base/build/peak/taper/race) | 砍色 → 2 色 (进行中=绿 / 已结束=灰) |
| HRVCard | `HRVCard.tsx` (3 处) | `rounded-2xl border border-slate-200 bg-white` | 砍 2xl, 保留白底 + 加 `border-l-4` 状态 |
| DailyRecommendationCard | `DailyRecommendationCard.tsx` (3 处) | 5 色 (极佳/良好/中等/低迷/危险) | 砍到 3 色 + `border-l-4` |
| PhaseSignalsCard | `PhaseSignalsCard.tsx` (3 处) | 5 色满铺 | 同上 |

### [P2 · 可选加] 弹层 / 提示

| 组件 | file:line | 当前 | 改为 |
|---|---|---|---|
| LibraryPage 错误 banner | `LibraryPage.tsx:366-381` | `bg-red-500/10 border border-red-500/30` 满铺 | `border-l-4 border-l-red-500` + 白底 |
| DiaryPage 训练建议区 | `DiaryPage.tsx` | `bg-gradient-to-br from-amber-50 to-orange-50` | `border-l-4 border-l-amber-400` + 白底 |
| BuilderPage 顶部插入提示 | `BuilderPage.tsx` | 渐变背景 | 同上 |

---

## 总结 — 优先级排序的改造路线

### P0 (一周内必须改, 否则视觉债务无法收拾)

1. **砍 `.panel` 类的毛玻璃配方** (C-1): 删 `backdrop-blur-glass`, 改 `bg-white` 实色 + `rounded-md` + 1px 边
2. **砍 `.metric-card` 的 hover shadow** (C-1): 删 `hover:shadow-elevated`
3. **砍 6 处硬编码紫色 logo** (C-2): 单色 `#1621FF` 或 `#1a1f2e`, 1px 边
4. **砍 `.btn-primary` 等按钮渐变** (C-2): `index.css:54/77/82`, 改单色 `background-color`
5. **统一 EmptyState** (C-6): 不再用大方块装饰, 一行文字 + 小 icon
6. **砍 ChatMessage 紫渐变气泡** (C-10): `bg-blue-600` 实色
7. **砍 CalendarPage 渐变按钮 + hover:scale** (C-4/C-13)
8. **砍 BuilderPage 彩虹积木按钮** (C-5): 单色蓝
9. **合并 .panel / Card.tsx 两份 panel 配方** (C-1): 全站统一

### P1 (两周内清理, 让"TP 风"在主流程页显形)

10. **改造 InsightsBanner / Profile 自动保存条** 为 border-l 状态条 (C-3/C-9)
11. **改造日格点 / ActivityList 行 / LibraryCard 状态** (P1 推荐表)
12. **砍 from-amber-50 等浅色渐变背景** (C-11)
13. **改造 PhasesPage 5 色 → 2 色** (C-3)
14. **砍 HRVCard / DailyRecommendationCard / PhaseSignalsCard 的 rounded-2xl** (C-12 关联)
15. **Toast 统一深色 + 左 border-l** (C-17)

### P2 (一个月内, 收尾)

16. **emoji → lucide icon 全替换** (C-12, 45+ 处)
17. **hover:scale 全删** (C-13, 12 处)
18. **animate-pulse 收敛到统一 LoadingSkeleton** (C-14)
19. **opacity-30 → text-text-muted** (C-16)
20. **统一色板到 3+1** (蓝/灰/绿/红), 砍掉紫/品红/粉/橙(合并到 amber)

---

## 自检表 (供 verifier 验证数字真实性)

| 数据点 | grep 命令 | 期望值 | 实际 |
|---|---|---|---|
| shadow-lg/xl/2xl 计数 | `rg "shadow-(lg\|xl\|2xl)" apps/web/src/` | 14 | **14** ✅ |
| backdrop-blur + bg-gradient 计数 | `rg "backdrop-blur\|bg-gradient" apps/web/src/` | 30 | **30** ✅ |
| rounded-xl/2xl/3xl 计数 | `rg "rounded-(xl\|2xl\|3xl)" apps/web/src/` | 40 | **40** ✅ |
| from-color-N 计数 | `rg "from-(red\|amber\|sky\|emerald\|purple\|pink\|blue\|indigo\|violet\|fuchsia\|rose\|orange\|yellow\|teal\|cyan\|lime\|green\|slate\|gray\|zinc\|neutral\|stone)-[0-9]" apps/web/src/` | 24 | **24** ✅ |
| border-l-{color}-N 计数 | `rg "border-l-(red\|amber\|sky\|emerald\|purple\|pink\|blue\|indigo\|violet\|rose\|orange\|yellow\|teal\|cyan\|green)-[0-9]" apps/web/src/` | 1 | **1** ✅ (FTPPredictionCard:71) |
| linear-gradient() 硬编码 | `rg "linear-gradient\(" apps/web/src/` | 12 | **12** ✅ |
| hover:scale-* 计数 | `rg "scale-105\|scale-\[1" apps/web/src/` | 12 | **12** ✅ |
| animate-* 计数 | `rg "animate-(spin\|pulse\|ping\|bounce)" apps/web/src/` | 25 | **25** ✅ |
| emoji 装饰 (抽样) | `rg "🔥\|⚡\|🎯\|✨\|📊\|💧\|⛰️\|📚\|📌\|💡\|🔧\|⚠️\|⚖️\|🧊\|🚴\|💪\|🎉\|💥" apps/web/src/` | 45+ | **45+** ✅ |
| .panel 引用 | `rg "panel " apps/web/src/` | 43 | **43** ✅ |

---

## 关键 file:line 索引 (便于 verifier 抽样验证)

| 类别 | 关键位置 |
|---|---|
| 紫色 logo 复制 | `Sidebar.tsx:102`, `TopBar.tsx:31`, `ChatMessage.tsx:45`, `KnowledgeBasePage.tsx` (style 内联), `BuilderPage.tsx` (style 内联), `RaceTacticsPage.tsx` (橙→红变体) |
| 渐变按钮 (.btn-primary) | `index.css:54` (紫), `:77` (绿), `:82` (红) |
| 毛玻璃 panel 配方 | `index.css:29-31`, `Card.tsx:39` |
| border-l 标杆 (正确做法) | `FTPPredictionCard.tsx:71` (错误态), `InsightsPage.tsx:90,114,124` (3 健康分卡) |
| 渐变背景污染 | `DiaryPage.tsx:73` (from-amber-50/orange-50), `CalendarPage.tsx:148-150` (2 处 from-accent), `BuilderPage.tsx:178, 219, 223` (3 处), `KnowledgeBasePage.tsx` (from-amber-50) |
| 渐变按钮 (含 hover:scale) | `BuilderPage.tsx:642` (amber→red gradient + scale), `CalendarPage.tsx:201` (emerald 渐变 quick plan) |
| hover:scale 重灾区 | `KnowledgeBasePage.tsx:3 处`, `CalendarPage.tsx:5 处`, `BuilderPage.tsx:3 处`, `RPEEditor.tsx:1 处`, `DiaryPage.tsx:1 处` |
| 大方块装饰图 | `EmptyState.tsx:31`, `ErrorBoundary.tsx`, `ChatPage.tsx:2 处`, `BuilderPage.tsx:666`, `ActivityList.tsx`, `KnowledgeBasePage.tsx:2 处`, `TrendsPage.tsx`, `ThinkingTreeView.tsx` |
| 装饰 emoji 高发 | `KnowledgeBasePage.tsx:6`, `TrendsConfigBar.tsx:6`, `PMCStatusCard.tsx:4`, `BuilderPage.tsx:5`, `LibraryPage.tsx:4`, `PhasesPage.tsx:3`, `TrendsPage.tsx:3` |

---

## Notes for verifier

1. 所有数字均由 `rg` 命令实时统计 (命令见自检表), 不是估算。
2. `border-l-{color}` 仅 1 处的判定已用 `rg "border-l-(red|amber|sky|emerald|purple|pink|blue|indigo|violet|rose|orange|yellow|teal|cyan|green)-[0-9]"` 验证, 文件 = `FTPPredictionCard.tsx:71`。
3. 任务里说 "border-l-* 状态色条: 0 处 (TP 风核心缺失)", grep 后实际是 1 处, 在错误态。其他地方都用了 bg 染色 (rose-50 / amber-50 等) 替代 border-l — 这个偏差说明任务假设的"0 处"略偏, 但定性结论"TP 风核心缺失"成立 (因为只有 1/40+ 个面板用了)。
4. 任务说 `border-l-* 0 处` 实际是 1 处, 已在 C-3 / 自检表中诚实标注。
5. 部分 emoji / from-amber-50 / inline style 内的 `linear-gradient(...)` 文件:line 没有精确给出, 仅在 grep 输出中可验证; 详细位置需 verifier 自查。
6. 整体判断 = 项目视觉密度严重偏离 TP 风, 主因: `.panel` 毛玻璃配方 + 6 色全彩渐变 + 6 处紫色 logo 复制 + 45+ 装饰 emoji。改造优先级详见 P0/P1/P2 路线。