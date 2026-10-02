# Cycling Coach V0.8.2 — 操作体验问题笔记本

> **作者**: Mavis Agent Team (4 个并行 track 汇总)
> **生成时间**: 2026-09-19
> **总 issue 数**: 90 条 (模式 A 8 + 模式 A' 33 + 模式 B 8 + 模式 C 17 + 模式 D 10 + 模式 E 14)
> **深度**: deep-engineering-handbook (用于 V0.8.3 实施前的完整问题地图)

---

## 0. TL;DR — 一页纸

| 模式 | 数量 | 一句话 |
|---|---|---|
| **A 模块不互通** | 8 条 | 5 个组件 (DailyRecom/KB/Builder/InsightsBanner/FTP/Notif/Compare) 无法"做完 → 加到下一处" |
| **A' 后端孤儿 API** | 33 条 | 128 个端点中 33 个前端 0 调用 (26% 浪费) |
| **B 入口深/找不到** | 8 条 | Diary/RaceTactics/HRV/FTPTest/Builder 等多入口分散, 命名不一致 |
| **C 视觉过度设计** | 17 条 | `.panel` 毛玻璃传染 43 处, logo 紫渐变 6 处复制, border-l 状态色条只有 1 处 |
| **D 操作流不顺畅** | 10 条 | ActivityDetail 返回丢状态 / 用户偏好不持久化 / Builder 撤销只 30 步等 |
| **E 内容/数据散乱** | 14 条 | KB 8 层目录嵌套 / Insights 拆 4 page / Compare 路由无入口 / Phase 模板独立 |
| **总计** | **90 条** | |

**3 个最大的"修了立刻爽"**:
1. **A-2 KB 不消费 URL query** (`Sidebar.tsx:167` 跳 KB 但 KB 不读 path) — 一行 fix, 立即解决用户 KB 直达痛点
2. **C-1 `.panel` 毛玻璃** (`index.css:29-31`) — 改一个 CSS 类, 全站同步净化
3. **E-9 ComparePage 路由可达但 Sidebar 0 入口** (`Sidebar.tsx:38-79`) — 加一行就解决入口黑洞

---

## 1. 修复优先级总表

### 🔴 P0 (高价值 + 低成本, 用户最高频痛点)

| ID | 一句话 | 工作量 | 依赖 |
|---|---|---|---|
| **A-2** | KB 页消费 URL query | 0.5 天 | - |
| **A-7** | ComparePage 路由 + ActivityList 多选 | 1 天 | E-9 |
| **E-9** | Sidebar 加 Compare 入口 | 0.1 天 | - |
| **C-1** | `.panel` 改实色 (全站传染) | 1 天 | - |
| **C-2** | Logo 紫渐变去色 | 0.5 天 | - |
| **C-3** | 健康分卡改 border-l | 0.5 天 | C-1 |
| **C-4** | Calendar 训练项简化配色 | 0.5 天 | C-1 |
| **B-3** | `/ai/hrv` 路由 vs Sidebar 标签对齐 | 0.1 天 | - |

**P0 总工作量**: 4-5 天, 立即提升操作密度 + 视觉去 AI 味

### 🟡 P1 (价值高, 工作量中等)

| ID | 一句话 | 工作量 | 依赖 |
|---|---|---|---|
| **A-1** | DailyRecommendationCard 一键加日历 | 0.5 天 | - |
| **A-4** | InsightsBanner 加跳转 | 0.5 天 | - |
| **A-5** | FTPPredictionCard "采纳预测" 按钮 | 0.5 天 | - |
| **A-6** | NotificationsBell 标记已读 | 0.5 天 | localStorage |
| **A-8** | 8 个 page 加模块跳转 (建跳转矩阵) | 1 天 | - |
| **B-1** | DiaryPage 从 ActivityDetail 进入 | 0.5 天 | - |
| **B-4** | FTPTest 与 Profile FTP 互引 | 0.5 天 | - |
| **B-7** | FTPTestPage 结果"应用到档案" | 0.5 天 | A-5 |
| **C-5** | Builder 积木配色简化 | 1 天 | C-1 |
| **C-6** | EmptyState 素描化 | 0.5 天 | C-1 |
| **E-1** | KB 目录嵌套收口 (≤3 层) | 1.5 天 (含迁移) | - |
| **E-5** | Profile 字段分组 | 0.5 天 | - |
| **E-7** | LibraryPage WorkoutDetailDrawer 加编辑 | 0.5 天 | - |
| **E-8** | Insights 4 page 聚合 1 个 tabbed | 1.5 天 | - |

**P1 总工作量**: 9-10 天, 完成模块互通 + 视觉降 AI 味

### 🟢 P2 (锦上添花, V0.8.4 做)

| ID | 一句话 | 工作量 |
|---|---|---|
| **C-7** ~ **C-17** | hover/emoji/loading 等微改 | 2-3 天打包 |
| **D-1** ~ **D-10** | ActivityDetail 状态保留 / Builder 撤销栈扩 / 偏好持久化 | 3 天打包 |
| **E-2/E-3/E-4** | KB 二级导航 / category query / 搜索维度 | 2 天打包 |

**P2 总工作量**: 7-8 天, V0.8.4 整批次

### ⚪ 不做 (永远不做 / 放 V0.9.x)

- ❌ Mobile UX 单独优化
- ❌ Premium Paywall
- ❌ 教练侧 / 多人协作
- ❌ StackUp
- ❌ Recurring Workouts (放 V0.8.4 单独批次)
- ❌ Layout 自定义 (放 V0.8.4 单独批次)
- ❌ 后端架构变动 (只加 1 个 `POST /phases/{id}/apply` 端点)

---

## 2. 模式 A: 模块不互通 (8 条)

### A-1 · DailyRecommendationCard 推荐结果无法"立即加到日历"
- 现状: `apps/web/src/components/DailyRecommendationCard.tsx:109-167` 渲染"今日推荐 VO2max · 目标 TSS ~100", 0 处 `useNavigate` / `onClick`
- 用户视角: Dashboard 看到"今天适合 VO2max"却找不到操作入口。要排到日历需手动切到 `/plan/calendar` 再选日期 + 模板
- 修复方向: 组件接收 `onSchedule(intent, tss)` 回调或在卡上加 "+ 加到日历" 按钮, 跳 `/plan/calendar?intent=vo2max&tss=100`

### A-2 · KnowledgeBasePage 不消费 URL query 参数
- 现状: `apps/web/src/pages/KnowledgeBasePage.tsx:1-313` 全文 0 处 `useSearchParams` / `useLocation` / `location.search`
- 用户视角: `Sidebar.tsx:167` 用 `navigate(/data/knowledge?category=...)`, `GlobalSearch.tsx:142` 用 `navigate(/data/knowledge?path=...)`, 但 KB 页只渲染"全部文档"根视图, 用户感到"点了没用"
- **P0 优先级** — 一行 fix 立即解决 KB 直达痛点
- 修复方向: KB 页 `useSearchParams` 读 `path` / `category`, 初始 `selectedPath` 从 URL 取

### A-3 · BuilderPage 段模板 (localStorage) 与我的课程 (API) 双向不通
- 现状: `BuilderPage.tsx:198-205, 442-457` 段模板走 `localStorage.setItem("cc:segment_templates", ...)`, `BuilderPage.tsx:265-270` 我的课程走 `api.listWorkouts`
- 用户视角: 用户在 Builder 排好 5×3min VO2 块"存为段模板", 下次想跨课程复用却找不到"将 localStorage 段模板同步到后端"路径
- 修复方向: 段模板改为 API 端点 `api.segmentTemplates`, 与 `Workout` 同 schema, BuilderPage 左侧加 tab "我的段"

### A-4 · InsightsBanner 洞察条目纯展示, 无跳转动作
- 现状: `apps/web/src/components/InsightsBanner.tsx:1-191` (191 行) grep `navigate` 0 命中
- 用户视角: Dashboard 顶部看到"高强度累积疲劳, 建议降量 20%"只能手动切到 `/ai/hrv` 自己找对应洞察
- 修复方向: 每条洞察加 `onClick → navigate('/ai/hrv#insight-'+id)` 或详情路由 `/ai/hrv?focus=ID`

### A-5 · FTPPredictionCard 显示预测 FTP 却无"采纳此预测 → 更新档案"
- 现状: `apps/web/src/components/FTPPredictionCard.tsx:170-189` 只有"查看趋势" / "重新预测"两按钮, `api.updateAthlete` 在 `lib/api.ts` 存在但组件未用
- 用户视角: 用户看到模型预测 265W (档案 250W, +15W), 想"那我把档案改成 265", 必须手动去 `/settings` → 改 FTP 输入框
- 修复方向: 加"采纳预测"按钮, 调 `api.updateAthlete({ ftp: predicted_ftp })` 并 toast 成功

### A-6 · NotificationsBell dropdown 无"标记已读" / "忽略"功能
- 现状: `apps/web/src/components/NotificationsBell.tsx:75-122` 弹窗列出 insights 但 0 处状态变更
- 用户视角: 用户处理完洞察后铃铛红点不变, 下次开页面仍 `9+`, 没法"已处理"
- 修复方向: 本地 `localStorage["cc:read_insight_ids"]` Set, 点击条目或"全部已读"按钮写入

### A-7 · ComparePage 入口在 `/training/compare` 但与 ActivityList 多选 → 对比工作流不通
- 现状: `apps/web/src/pages/ComparePage.tsx:50-58` 单独 `listActivities(limit: 200)`, `ActivityList.tsx:289-322` 行只有 navigate 跳详情, 0 处 `selected` 集合, `Sidebar.tsx:38-79` 完全不提 `/training/compare`
- 用户视角: 想对比两次间歇训练, 必须去 `/training/compare` URL 直输或外部跳转, ActivityList 没"加入对比"选项
- 修复方向: ActivityList 加多选 checkbox + "对比 N 项" toolbar, ComparePage 从 query `?received=xxx` 接收初始列表

### A-8 · 17 个 page 中 8 个完全无 useNavigate
- 现状: 全项目 `useNavigate` 调用共 ~28 次, 集中在 9 个 page (Dashboard/Import/ActivityList/Builder/Chat 等), 8 个 page 完全无跳转
- 用户视角: 8 个独立 page 像是"信息孤岛", 用户切到后只能手动从 Sidebar 找下一个目的地
- 修复方向: 每个 page 至少加 2 处跳转 (详情 → 列表, 当前 → 相关模块)

---

## 3. 模式 A': 后端孤儿 API (33 条精选)

> 完整 128 端点表在 `_review/team-output/track-api-data-flow/deliverable.md` section 2

### A'-1 · POST /api/coach/chat/sessions/{id}/tree (chat.py:81) — 孤儿
- 后端有, 前端 0 调用
- 影响: chat 持久化靠 React state, 刷新页面就丢
- 修复: ChatPage 在 conversation 切换时 PATCH 树结构

### A'-2 · POST /api/coach/sessions/{id}/messages (chat.py:65) — 孤儿
- 同上, 历史消息没持久化

### A'-3 · GET /api/phases/{id}/apply (不存在) — 孤儿需求
- 用户期望"一键把 Phase 计划铺到日历", PhasesPage 765 行无调用
- 修复: 新增端点 `POST /api/phases/{id}/apply?start_date=...&weeks=N`

### A'-4 · GET /api/hrv/state (hrv.py:42) — 孤儿
- 后端有 HRV 计算, 前端 HRVCard 没接
- 修复: HRVCard 改用 `api.hrvState()` 而非自写 fetch

### A'-5 · GET /api/equipment (equipment.py:32) — 孤儿
- 后端有器材管理, 前端 0 入口
- 修复: Sidebar 加"装备"入口, Profile 加"装备" section

### A'-6 · GET /api/races (races.py:24) — 孤儿
- 后端有赛事管理, 前端 RaceTactics 用了单独的 race-tactics 表
- 修复: 合并两套 race 数据 (V0.8.4 再说)

### A'-7 · POST /api/notifications/{id}/read (notifications.py:18) — 孤儿
- 后端有通知状态, 前端 NotificationsBell 只展示无操作

### A'-8 · GET /api/athlete/zones (athlete.py:85) — 孤儿
- 后端有区间配置, 前端用 Coggan 7 区硬编码
- 修复: Profile 加"区间配置" tab, 调此端点

### A'-9 · GET /api/dashboard/today (dashboard.py:30) — 半孤儿
- 前端 Dashboard 调了, 但 `api/dashboard/PMC/today` 用了另一路径
- 修复: 统一 dashboard API 路径

### A'-10 · POST /api/workouts/ai-schedule (workouts.py:112) — STUB
- 返回 501, 但 ChatPage workflow tab 想调它
- 修复: V0.8.3 B1-2 配套实现

### A'-11 ~ A'-33 · (略, 见 track-api-data-flow deliverable section 3)
> 包括 12 个 PATCH/DELETE 单条端点 (workout/phase/calendar 单条), 6 个 GET 列表过滤参数未用, 4 个导出格式端点

**总结**: 128 端点中 33 个前端 0 调用 = **26% 后端产能浪费**, 主要因为:
1. Chat/HRV/Equipment 等模块前端 UI 没起来
2. 单条 PATCH/DELETE 被批量接口替代
3. 路径不一致 (`/dashboard/today` vs `/dashboard/PMC/today`)

---

## 4. 模式 B: 入口深/找不到 (8 条)

### B-1 · DiaryPage 无从 ActivityDetail 进入
- 现状: ActivityDetail 顶部只有"返回列表"按钮, 无"打开今日日记"链接
- 用户视角: 用户记完训练想写感受, 必须从 Sidebar 找"训练日记" → 再选今天
- 修复: ActivityDetail 加"📝 写日记"按钮跳 `/training/diary?date=YYYY-MM-DD`

### B-2 · RaceTacticsPage 详情视图无面包屑 / 返回列表
- 现状: `RaceTacticsPage.tsx:679` 行, 选中 session 后无"返回所有比赛"按钮
- 用户视角: 用户在一个比赛详情里, 想看其他比赛, 必须点 Sidebar "比赛战术" 回到列表
- 修复: 顶部加面包屑 "比赛战术 / [赛事名]"

### B-3 · `/ai/hrv` 路由命名与 Sidebar 标签"HRV / 训练健康"不匹配
- 现状: 路由 `/ai/hrv`, Sidebar 标签 "HRV / 训练健康"
- 用户视角: URL 跟标签不一致, 用户分享/书签时混乱
- 修复: 路由改名 `/ai/health` 或 Sidebar 改回 "HRV"

### B-4 · FTPTestPage 与 Profile 的 FTP 编辑入口互不引用
- 现状: FTPTestPage 跑完测试, Profile 有"FTP 输入框", 两个独立 UI
- 用户视角: 测完 FTP 后找不到"同步到 Profile"按钮
- 修复: FTPTestPage 加"应用到档案"按钮 (同 A-5)

### B-5 · DiaryPage 同月份导航只能 ±1 天
- 现状: `DiaryPage.tsx` 左右箭头单日切换, 无"上一周" / "上一月"按钮
- 用户视角: 想看 3 周前的日记要点 21 次 ←
- 修复: 加日历视图或周/月快速跳

### B-6 · BuilderPage 进入 `/plan` 默认空, LibraryPage 已存课程但无"在 Builder 里编辑"按钮
- 现状: `BuilderPage.tsx:265-270` 列出"我的课程"但只能加载到 builder, 无"编辑现有课程"按钮
- 用户视角: LibraryPage WorkoutDetailDrawer (lines 554-742) 只有"删除/复制/导出", 无"在 Builder 中编辑"
- 修复: LibraryPage WorkoutDetailDrawer 加"✏️ 编辑"按钮 → `/plan/builder?id={workout_id}`

### B-7 · FTPTestPage 估算结果无"应用到档案"
- 现状: `FTPTestPage.tsx` 跑完显示 "估算 FTP: 265W", 但 0 处写入档案
- 用户视角: 测完结果只是个数字, 还要手动到 Profile 改
- 修复: 同 A-5, 调 `api.updateAthlete({ ftp })`

### B-8 · BuilderPage 我的课程列表无搜索 / 过滤
- 现状: BuilderPage 左侧"我的课程"列表无搜索框
- 用户视角: 课程超过 10 个就找不到, 全靠滚轮
- 修复: 加 `<input>` 实时过滤

---

## 5. 模式 C: 视觉过度设计 (17 条精选)

### C-1 [P0] `.panel` 类 = AI 毛玻璃卡片, 全站传染 43 处
- 现状: `apps/web/src/styles/index.css:29-31` 定义 `.panel { @apply bg-white/80 backdrop-blur-glass border border-border rounded-xl shadow-panel; }`, `metric-card` 同款
- TP 风: 纯白底 (`#ffffff` 100%) + 浅灰边 1px + 圆角 4-6px + 无阴影 + 区分层级用 `border-l-4`
- 影响: 移动端 backdrop-blur 性能开销 + "非专业" 视觉感 + 数据密度被吃
- **最大单一来源**, 改了影响最大

### C-2 [P0] Logo / Avatar 紫色渐变硬编码 6 处
- 现状: `linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)` 出现在 Sidebar.tsx:102 / TopBar.tsx:31 / ChatMessage.tsx:45 / KnowledgeBasePage 等 6 处
- TP 风: 单色 (蓝灰) 或 monogram
- **改法**: 抽到 CSS variable, 全局改一处

### C-3 [P0] 健康分卡 = 满铺彩色而非 border-l
- 现状: InsightsHealthCard / PMCStatusCard / HRVCard 用 `bg-rose-50` + `border-rose-200` 整片彩色
- TP 风: 白底 + `border-l-4 border-l-{status}` 左侧 4px 色条
- 影响: 数据卡片像 "warning 提示", 实际是正常状态

### C-4 [P0] Calendar 训练意图 6 色全渐变 + hover:scale-105
- 现状: CalendarPage.tsx 训练项按 intent 分 6 色 + `hover:scale-105` (C-13 重复问题)
- TP 风: 1-2 色 + `border-l-4` (绿 = 完成, 红 = 未完成)
- 影响: 日历像 "节日", 不像 "训练计划"

### C-5 [P1] Builder 积木配色 + 拖拽块 = 满屏高饱度
- 现状: BuilderPage.tsx 12 种 StepKind 12 种颜色, 拖拽时彩色 ring
- TP 风: 蓝灰主色, 选中态用 border-l 强调
- 影响: Builder 视觉疲劳, 难以专注结构

### C-6 [P1] EmptyState 大方块装饰图 = 反 TP 数据气质
- 现状: EmptyState.tsx 用 `rounded-2xl w-16 h-16` 灰色方块
- TP 风: 小 icon (16px) + 一行提示文字
- 影响: 空状态像 "插画", 不像 "工具"

### C-7 [P1] KnowledgeBasePage 卡片 hover 三重动效堆叠
- 现状: hover 时 `shadow-xl` + `scale-[1.02]` + `border-accent` 同时触发
- TP 风: hover 仅换边框色 (1px)
- 影响: 视觉过载

### C-8 [P1] LibraryPage 6 个 goal 用 6 种 chip + ring + bg + text
- 现状: GOAL_COLOR 6 种配色, 每种 chip 4 属性 (bg/border/text/ring)
- TP 风: 1-2 种状态色 + 文字标签
- 影响: Library 像 "调色板"

### C-9 [P1] Profile 自动保存状态条 = 满铺浅色
- 现状: `bg-emerald-50 border-emerald-200` 大色块 (Profile.tsx:138-167)
- TP 风: 小指示器 + 文字 "Saved ·"
- 影响: 1.5px 提示文字变成 100px 大色条

### C-10 [P1] ChatMessage 用户消息 = 紫色渐变气泡
- 现状: ChatMessage.tsx:45 紫色渐变
- TP 风: 单色背景
- 同 C-2 系列

### C-11 ~ C-17 · (略, 微调级)
- C-11 from-amber-50 to-orange-50 浅色渐变背景 (装饰性)
- C-12 装饰 emoji 45+ 处
- C-13 hover:scale-105 / scale-[1.02] 共 12 处
- C-14 animate-pulse 用得过多 24 处
- C-15 ChatPage / DiaryPage hero icon 大方块
- C-16 opacity-30 / opacity-50 共 33 处
- C-17 Toast 4 色太花

**C 模式总工作量**: P0 4 条 ~3 天, P1 6 条 ~4 天, P2 7 条 ~3 天

---

## 6. 模式 D: 操作流不顺畅 (10 条)

### D-1 · ActivityList 跳详情后返回 → 全部状态丢失
- 现状: `ActivityList.tsx` 筛选/排序状态在 useState, 跳详情再返回需重新选
- 用户视角: 跳详情看 AI 分析 → 返回列表 → 筛选条件清空
- 修复: filter/sort 写到 URL query 或 sessionStorage

### D-2 · ComparePage 限制 limit 200 + 无日期筛选
- 现状: ComparePage.tsx:50-58 `listActivities(limit: 200)`, 无日期范围/活动类型筛选
- 用户视角: 想对比"过去 30 天 VO2 训练"无从下手
- 修复: 加日期 range picker + activity type 多选

### D-3 · 用户偏好存储碎片化 (localStorage 仅 2 处)
- 现状: 全项目仅 TrendsConfigBar (line 42) + BuilderPage segment_templates (line 200) 用 localStorage
- 用户视角: 日历视图模式/排序/折叠状态全丢, 每次重开恢复默认
- 修复: 抽 `useLocalPref(key, default)` hook, 11+ 处用上

### D-4 · ChatPage 3 tab 完全独立, 无交叉引用
- 现状: ChatPage 3 个 tab (对话 / 战术 / 思考树), 各自独立 state
- 用户视角: 在战术 tab 问的问题, 切到对话 tab 看不到
- 修复: 共享 conversation history

### D-5 · InsightsPage Weekly Review 无法刷新重算
- 现状: InsightsPage 加载一次后, "重新计算"按钮缺失
- 用户视角: 新导入活动后, Weekly Review 还显示旧数据
- 修复: 加"重新计算"按钮 + loading

### D-6 · BuilderPage 点击空白不取消, 编辑抽屉常驻 1/5 屏
- 现状: Builder 选中 block 后右侧抽屉常驻, 点空白不收起
- 用户视角: 编辑完想看全屏预览还得手动 X
- 修复: 点画布空白 → 收起抽屉

### D-7 · LibraryPage onDuplicate 后 refresh 失效
- 现状: LibraryPage.tsx:198-209 onDuplicate 复制后 list 不刷新
- 用户视角: 复制后看不到新课程
- 修复: await loadList() 后 toast

### D-8 · DiaryPage 自动保存无重试 / 失败提示
- 现状: DiaryPage 自动保存逻辑无错误处理
- 用户视角: 网络不好时丢日记无感知
- 修复: 加 retry + "保存失败" toast

### D-9 · BuilderPage 撤销栈只 30 步
- 现状: BuilderPage history 数组限制 30
- 用户视角: 改太多次后不能撤销
- 修复: 扩到 100 + 加 history size 显示

### D-10 · (略, 见 track-frontend-flow deliverable section D)

---

## 7. 模式 E: 内容/数据散乱 (14 条)

### E-1 [P1] KB 训练百科目录嵌套失控 (5-8 层)
- 现状: `kb_source/markdown/训练百科__061370d6/` 下 8 层目录, 最深 8 层路径
- 用户视角: 从 Sidebar 一级点进去, 至少下钻 4-5 层
- 修复: 知识库导入/迁移工具收口到 `kb_source/build/` 输出 ≤3 层

### E-2 [P0] KB hover 菜单只显 8 个顶级, 子级黑洞
- 现状: Sidebar.tsx:86-93 hover 只显示 8 个一级, 训练百科 1 个一级覆盖 288 个文档 (count=288 占 80%)
- **P0 修复**: Sidebar hover 加 "热门 5 篇" / "最近访问"

### E-3 [P0] Sidebar `?category=...` query 是 dead param
- 现状: 同 A-2, Sidebar 跳 KB 但 KB 不读 query
- 修复: 同 A-2

### E-4 [P1] KB 搜索 0 过滤维度
- 现状: `api.kbSearch(q)` 只接 keyword, 无 category/path/最近访问过滤
- 用户视角: 359 个文档全混在一起搜
- 修复: 加 category filter + 历史记录

### E-5 [P1] Profile 7+ 字段堆一个 "基础信息" section 0 分组
- 现状: Profile.tsx:118-126 定义 7 个字段 (name/ftp/ftp_estimated/max_hr/lthr/weight/height), 全在一个 panel
- 用户视角: 找 FTP 字段得滑一段
- 修复: 分 3 组 (基本 / 阈值 / 体型)

### E-6 [P1] FTP 相关分散 3 个页面 + Profile 内嵌按钮
- 现状: FTPTestPage + Profile 改 FTP + InsightsPage 显示 FTP + FTPPredictionCard
- 用户视角: FTP 数据 4 处不一致 (谁更新了?)
- 修复: Profile 设 single source, 其他页面只读

### E-7 [P1] LibraryPage WorkoutDetailDrawer 缺「编辑」按钮
- 现状: `LibraryPage.tsx:554-742` 只有"复制/删除/导出"
- 用户视角: 想改一个已有课程的 1 个 step, 必须重建
- 修复: 加"✏️ 编辑"按钮 → Builder

### E-8 [P1] Insights 拆 4 个独立 page + TrendsPage 跟 DiaryPage 不同路由组
- 现状: TrendsPage 在 /training/, DiaryPage 在 /training/, InsightsPage 在 /ai/, ComparePage 在 /training/, 但 Sidebar 把它们在 Dashboard 旁边列
- 用户视角: 不知道哪个看什么
- 修复: 1 个 `/training/insights` tabbed (趋势/周复盘/对比/日记)

### E-9 [P0] ComparePage 路由可达但 Sidebar 0 入口
- 现状: `/training/compare` 路由存在 (`App.tsx:104-108`), Sidebar.tsx:38-79 无 compare 入口
- **P0 修复**: Sidebar 加"📊 对比"项

### E-10 [P1] DiaryPage 495 行 + 跟 Activity 同天数据无并排
- 现状: DiaryPage 独立, 跟 ActivityDetail 不联动
- 用户视角: 看活动时不能同时看日记
- 修复: ActivityDetail 加 "日记片段" 块 / DiaryPage 加 "活动卡"

### E-11 [P2] Workout Tags/Goals 0 管理界面
- 现状: workout.tags / workout.goal 字段存在, 无管理 UI
- 用户视角: 想批量改 goal 标签无从下手
- 修复: LibraryPage 加 "标签管理" modal

### E-12 [P2] Phase 模板 0 独立入口 + 跟 Builder 无 link
- 现状: Phase 是用户自建训练周期, 无模板库
- 修复: PhasesPage 加 "模板" tab

### E-13 [P2] KB 文档展示走自写 markdown 渲染, 不解析 frontmatter
- 现状: KnowledgeBasePage.tsx 自写 markdown 渲染 (lines 250+)
- 用户视角: frontmatter (难度/标签/相关) 不显示
- 修复: 接 remark/rehype, 解析 frontmatter

### E-14 [P2] Race 类型 / Phase 类型 / Workout Goal 3 套并立术语
- 现状: race_type (road/track/crit/...) / phase_type (base/build/peak/taper/recovery) / workout goal (endurance/tempo/sweet_spot/...) 三套独立 enum
- 用户视角: 三者关系不清楚 (Phase=Base 对应 Goal=Endurance?)
- 修复: 建一个统一概念图, 加 tooltip 解释

---

## 8. 附录 A: 已知用户原话 (痛点来源)

> 引用来自用户 2026-09-19 1轮对话, 给上下文还原用

1. "我说的是操作体验: 我先举几个例子, 你接着挖相似的。1: 知识库内容杂乱, 部分访问不了, 通过侧边栏直接访问某个知识库文件访问不了。2: 日历, 训练等内容各管各的, 我新建的训练没法拖到计划里, 计划加不进日历里, AI教练给出的回复不能直接加到课程里。3: 前端一眼AI味道, 令人审美疲劳, TP的风格就很好看。"

2. "我说的是功能差距就完蛋了, 我说的不是功能" (批评我上次偏题)

3. "拉团队挖, 这种大事要上团队！！！"

4. "干完给我测, 我同意了才能 push" / "我要的是先搞实在的, 工程的"

5. "不要局限于开发者视角。你要进行详细测试... 重点优化使用体验"

---

## 9. 附录 B: 跟 V0.8.2 已改动的 18 项 UX 优化关系

| V0.8.2 改动 | 覆盖了 | 没覆盖 (→ V0.8.3 必做) |
|---|---|---|
| U-1 Cmd+K 全局搜索 | A 部分 (跨页搜内容) | A-2 KB 不消费 query, E-2 KB 子级黑洞 |
| U-2 useConfirm hook | - | D 系列大部 (列表状态、撤销栈) |
| U-3 Profile 自动保存 | E-5 一半 (save status) | E-5 字段分组, E-6 FTP 一致性 |
| U-4 AI 超时 120s | - | A-5/B-7 FTP 应用, A'-10 AI-schedule stub |
| U-5 Mock 指示移走 | - | - |
| U-6 标签清晰化 | B-3 一半 | B-3 路由命名 |
| U-7 5 分组 Sidebar | - | E-9 Compare 无入口, B-3 标签 |
| U-8 通知 badge | - | A-6 标记已读 |
| U-9 取消按钮 | D-1/D-6 一半 | - |
| U-10 EmptyState | - | C-6 EmptyState 素描化 |
| U-12 markdown 流式 | - | E-13 KB frontmatter |
| U-13 错误重试 | D-8 一半 | D-8 DiaryPage 失败提示 |
| U-14 fetch 统一 | 部分 | - |
| U-15 查重 | - | - |
| U-20 全文高亮 | KB 搜索 | E-4 KB 过滤维度 |
| U-22 引用跳转 | Chat 引 KB | A-2 KB 不读 query (BUG) |
| U-23 race_type 色 | - | C-4 Calendar 6 色全彩 |
| U-25 Toast undo | - | - |

**结论**: V0.8.2 18 项覆盖了 ~30% 的本期 issue, **70% 没覆盖**, 正是 V0.8.3 重点。

---

## 10. 附录 C: Track 来源索引

| Issue ID | Track | Deliverable |
|---|---|---|
| A-1 ~ A-8 | track-frontend-flow | `_review/team-output/track-frontend-flow/deliverable.md` |
| A'-1 ~ A'-33 | track-api-data-flow | `_review/team-output/track-api-data-flow/deliverable.md` |
| B-1 ~ B-8 | track-frontend-flow | 同上 |
| C-1 ~ C-17 | track-visual-density | `_review/team-output/track-visual-density/deliverable.md` |
| D-1 ~ D-10 | track-frontend-flow | 同 A |
| E-1 ~ E-14 | track-content-organization | `_review/team-output/track-content-organization/deliverable.md` |

---

## 11. 附录 D: V0.8.3 实施路线图 (来自 V0.8.3_PLAN.md)

### 批次 1: 模块互通 (3-4 天) — P0 + P1 高价值
- B1-1 Library workout 真·拖到 Calendar ← 解决 A-1 / A-7 / 用户原话
- B1-2 Chat 回复含 workout JSON → "加入 Builder" ← 解决 A'-10 + 用户原话
- B1-3 Phases → "应用到日历" 一键生成 ← 解决 A'-3 + 用户原话
- B1-4 Builder → "保存并加入日历" ← 用户原话
- B1-5 ActivityDetail → "作为模板" ← 解决 B-6 + 用户原话
- B1-6 Library 多选 workout 批量加入日历 ← 解决 A-7 联动

### 批次 2: KB / Chat / Insights 体验贯通 (2 天)
- B2-1 Sidebar KB 加最近访问 + 收藏 ← 解决 E-2 + 用户原话
- B2-2 KB 顶部搜索直达 ← 解决 A-2 / E-3
- B2-3 Chat 历史记录 + 搜索 ← 解决 D-4
- B2-4 Insights 聚合入口 ← 解决 E-8

### 批次 3: 视觉降 AI 味 (3-4 天) — 用户原话
- B3-1 设计系统 theme 换皮 ← 解决 C-1
- B3-2 圆角统一 6px ← 解决 C-1 配套
- B3-3 Logo 渐变去色 ← 解决 C-2
- B3-4 Empty state 素描化 ← 解决 C-6
- B3-5 卡片状态色条 (TP 风) ← 解决 C-3 / C-4

---

**笔记本完成。90 条 issue 全数过完。下一步: 等用户拍板 V0.8.3 开干顺序。**