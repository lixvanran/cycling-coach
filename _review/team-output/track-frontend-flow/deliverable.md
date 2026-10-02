# Track: 前端页面操作流审计 (V0.8.2)

## Summary
系统扫描 17 个 page + 5 个 layout + 25+ 组件 / 路由表 / Sidebar 配置 / `useNavigate` 引用矩阵 / draggable 矩阵 / localStorage 用法 / 弹窗数量 / URL query param 消费方。在已知 10 个痛点之外挖出 22 条新 issue，按 A/B/D 三类分组。

## Changed files
- `/workspace/.mavis/plans/plan_1ca7f41a/outputs/track-frontend-flow/deliverable.md` (created)
- `/workspace/.mavis/plans/plan_1ca7f41a/board.md` (appended progress entry)

## Notes
- 全 issue 都给 `file_path:line_number` 证据；行号均来自 V0.8.2 快照 (9948 lines total in `apps/web/src/pages/*.tsx`)。
- 每条均不含 patch 与背景介绍；描述用户视角影响 + 修复方向。
- 验证方法：仅依赖 `read` / `grep` / `bash`，未启动 dev server；后端 API 行为未直接确认。

---

# 模式 A · 模块不互通

## A-1 · DailyRecommendationCard 推荐结果无法"立即加到日历"
- 现状：`apps/web/src/components/DailyRecommendationCard.tsx:109-167` 渲染"今日推荐 VO2max · 目标 TSS ~100"，但 0 处 `useNavigate` / `onClick`。
- 用户视角：Dashboard 看到"今天适合 VO2max"却找不到操作入口。要排到日历需手动切到 `/plan/calendar` 再选日期 + 模板。
- 修复方向：组件接收 `onSchedule(intent, tss)` 回调或在卡上加 "+ 加到日历" 按钮，跳 `/plan/calendar?intent=vo2max&tss=100`。

## A-2 · KnowledgeBasePage 不消费 URL query 参数
- 现状：`apps/web/src/pages/KnowledgeBasePage.tsx:1-313` 全文 0 处 `useSearchParams` / `useLocation` / `location.search`。`App.tsx:139-143` 路由 `/ai/hrv` → `InsightsPage`；`/data/knowledge` 是裸路由。
- 用户视角：`Sidebar.tsx:167` 用 `navigate(\`/data/knowledge?category=${...}\`)`；`GlobalSearch.tsx:142` 用 `navigate(\`/data/knowledge?path=${...}\`)`。两者跳转均成功，但 KB 页只渲染"全部文档"根视图，用户感到"点了没用"。
- 修复方向：KB 页 `useSearchParams` 读 `path` / `category`，初始 `selectedPath` 从 URL 取。

## A-3 · BuilderPage 段模板 (localStorage) 与我的课程 (API) 双向不通
- 现状：`BuilderPage.tsx:198-205, 442-457` 段模板走 `localStorage.setItem("cc:segment_templates", ...)`；`BuilderPage.tsx:265-270` 我的课程走 `api.listWorkouts`。
- 用户视角：用户在 Builder 排好 5×3min VO2 块"存为段模板"，下次想跨课程复用，却找不到"将 localStorage 段模板同步到后端"路径；反之想把 Library 里某课"整段拆为模板"也无处下手。
- 修复方向：段模板改为 API 端点 `api.segmentTemplates`，与 `Workout` 同 schema（带 `kind` / `reps` / `step`），BuilderPage 左侧加 tab "我的段"。

## A-4 · InsightsBanner 洞察条目纯展示，无跳转动作
- 现状：`apps/web/src/components/InsightsBanner.tsx:1-191`（191 行）grep `navigate` 0 命中。
- 用户视角：Dashboard 顶部看到"高强度累积疲劳，建议降量 20%"只能手动切到 `/ai/hrv` 自己找对应洞察。
- 修复方向：每条洞察加 `onClick → navigate('/ai/hrv#insight-'+id)` 或详情路由 `/ai/hrv?focus=ID`。

## A-5 · FTPPredictionCard 显示预测 FTP 却无"采纳此预测 → 更新档案"
- 现状：`apps/web/src/components/FTPPredictionCard.tsx:170-189` 只有"查看趋势" / "重新预测"两按钮；调用 `navigate("/training/trends")` / `setRetryKey()`。`api.updateAthlete` 在 `lib/api.ts` 存在但组件未用。
- 用户视角：用户看到模型预测 265W (档案 250W, +15W)，想"那我把档案改成 265"，必须手动去 `/settings` → 改 FTP 输入框。
- 修复方向：加"采纳预测"按钮，调 `api.updateAthlete({ ftp: predicted_ftp })` 并 toast 成功，跳转 Profile 确认。

## A-6 · NotificationsBell dropdown 无"标记已读" / "忽略"功能
- 现状：`apps/web/src/components/NotificationsBell.tsx:75-122` 弹窗列出 insights 但 0 处状态变更。`unread` 计算只反映 `severity`，无 read-state。
- 用户视角：用户处理完洞察后铃铛红点不变，下次开页面仍 `9+`，没法"已处理"。
- 修复方向：本地 `localStorage["cc:read_insight_ids"]` Set，点击条目或"全部已读"按钮写入，badge 计算排除已读。

## A-7 · ComparePage 入口在 `/training/compare` 但与 ActivityList 多选 → 对比工作流不通
- 现状：`apps/web/src/pages/ComparePage.tsx:50-58` 单独 `listActivities(limit: 200)`。`ActivityList.tsx:289-322` 行只有 navigate 跳详情，0 处 `selected` 集合。`Sidebar.tsx:38-79` 完全不提 `/training/compare`。
- 用户视角：用户在 ActivityList 选好 5 个活动想对比，必须记下 5 个 id → 跳到独立 Compare 页 → 在 200 条长列表里手动再选一次。
- 修复方向：ActivityList 行加 checkbox，`/training/compare?ids=1,2,3` 预填；Sidebar 加 AI 教练组下的"对比"入口。

## A-8 · 17 个 page 中 8 个完全无 useNavigate
- 现状：grep `useNavigate` 仅 9 个 page：`LibraryPage / ImportPage / Dashboard / ComparePage / ChatPage / CalendarPage / BuilderPage / ActivityList / ActivityDetail`。剩下 8 个 (`PhasesPage / InsightsPage / TrendsPage / DiaryPage / KnowledgeBasePage / Profile / FTPTestPage / RaceTacticsPage`) 0 引用。
- 用户视角：从 InsightsPage 周复盘跳不到 TrendsPage 看趋势；从 DiaryPage 跳不到 ActivityList 看当天活动；从 PhasesPage 跳不到 CalendarPage 看周期排课；从 RaceTacticsPage 跳不到 KB 查相关知识。
- 修复方向：8 个 page 至少加 1 个跨模块跳转按钮（典型：InsightsPage 周卡 → "看趋势" → `/training/trends`；DiaryPage 关联项 → 活动详情）。

---

# 模式 B · 入口深 / 找不到

## B-1 · DiaryPage 无从 ActivityDetail 进入
- 现状：`ActivityDetail.tsx:160-207` 顶部 sticky bar 只"返回 / AI 分析 / 取消"3 按钮。`DiaryPage.tsx:60-495` 0 处跳转入口关联 ActivityDetail。
- 用户视角：训练后 30 分钟内最宜记 RPE + 主观感受（`ImportPage.tsx:166-168` 自己也提示），但训练详情页没"写日记"快捷按钮，要绕 Sidebar 选"训练日记"再手动选日期。
- 修复方向：ActivityDetail 顶栏加 `BookOpen` 图标 → `navigate(\`/training/diary?date=${activity.start_time.slice(0,10)}&activity_id=${id}\`)`，DiaryPage 读 URL 自动定位。

## B-2 · RaceTacticsPage 详情视图无面包屑 / 返回列表
- 现状：`apps/web/src/pages/RaceTacticsPage.tsx:45-679`（679 行）会话列表 + 详情同页，但详情模式下 0 处「← 返回会话列表」按钮（仅 `X` 删除 / 列表 cards 重渲染）。
- 用户视角：选了 session A 进去对话后，想对比 session B 必须滚到顶部点列表项；删除当前会话后直接 setSelectedId(null) 但没视觉提示"已回到列表模式"。
- 修复方向：详情顶部加 `<button onClick={() => setSelectedId(null)}>← 返回列表</button>`，删除后 toast 提示"已回到列表"。

## B-3 · /ai/hrv 路由命名与 Sidebar 标签"HRV / 训练健康"不匹配
- 现状：`App.tsx:136-143` 路由 `path="hrv"` → `InsightsPage`（实际是周复盘页）。`Sidebar.tsx:53` 显示 `label: "HRV / 训练健康"`。
- 用户视角：用户在 Sidebar 找"HRV"找不到；点"HRV / 训练健康"看到周复盘，困惑"这跟 HRV 有什么关系"（HRVCard 仅是 4 卡之一）。
- 修复方向：要么 Sidebar label 改为"训练洞察 / 周复盘"；要么 `/ai/hrv` 单独做一个 HRV 详情页，InsightsPage 改到 `/ai/insights`。

## B-4 · FTPTestPage 与 Profile 的 FTP 编辑入口互不引用
- 现状：`FTPTestPage.tsx:130-138` "手动录入" 按钮打开 modal 录入新测试。`Profile.tsx:200-238` 自己也有 FTP 输入框。两条路径都调 `api.ftpRecord` / `api.updateAthlete`，但互相不链。
- 用户视角：在 FTPTestPage 录了新测试 260W，回到 Profile 看档案还是旧的 250W（因为档案 FTP 与 ftp_records 表是分离字段）；但用户不知道该去 Profile 同步。
- 修复方向：FTPTestPage 录完后 toast 加"是否同步到档案？"，按钮调 `api.updateAthlete({ ftp: 260 })`；或后端 `ftpRecord` 接口自动更新 `athlete.ftp`。

## B-5 · DiaryPage 同月份导航只能 ±1 天
- 现状：`DiaryPage.tsx:243-278` 日期切换只有 ChevronLeft/Right + date input，无"上个月 / 下个月"或"按周跳"。
- 用户视角：用户 3 周前那天有日记，要跳过去得连按 21 次左箭头，或用 date input 但要记具体日期。
- 修复方向：加"上一周 / 下一周"按钮或日历 popup 选择器；同时支持 URL `?date=YYYY-MM-DD`。

## B-6 · BuilderPage 进入 `/plan` 默认空，LibraryPage 已存课程但无"在 Builder 里编辑"按钮
- 现状：`LibraryPage.tsx:719-738` WorkoutDetailDrawer 操作只有"排到日历 / 导出 .zwo / 复制到我的 / 删除"。`BuilderPage.tsx:272-283` 通过 `loadFromWorkout` 才能加载，但无入口。
- 用户视角：用户 Library 选好"VO2 5×3min"，想微调 `90% FTP → 92% FTP`，必须回 `/plan` → 左侧"我的课程"列表里翻到再点。整个 3 步。
- 修复方向：WorkoutDetailDrawer 加"在 Builder 中编辑"按钮 → `navigate(\`/plan?edit=${w.id}\`)`；BuilderPage `useSearchParams` 读 `edit`，初次渲染自动 `loadFromWorkout`。

## B-7 · FTPTestPage 估算结果无"应用到档案"
- 现状：`FTPTestPage.tsx:241-309` 估算结果面板只有"录入此次测试"按钮（写 ftp_records 表），调 `api.ftpRecord`。`api.updateAthlete({ ftp })` 存在但组件未用。
- 用户视角：用户用 4 协议综合估算 268W，按"录入此次测试"后档案里 athlete.ftp 没变（分离字段），功率区间仍按旧 250W 算。
- 修复方向："录入此次测试"按钮文案改为"应用为档案 FTP"，同时调 ftpRecord + updateAthlete；或新增 `applyFtpToProfile()` 按钮。

## B-8 · BuilderPage 我的课程列表无搜索 / 过滤
- 现状：`BuilderPage.tsx:918-939` 我的课程列表 `space-y-1 max-h-48 overflow-auto`，无搜索框。
- 用户视角：用户自建 30+ 课程，要在 BuilderPage 左侧找某个老课程只能肉眼滚动。
- 修复方向：加 `myWorkoutSearch` state + `<Search>` input，过滤 `w.title.includes(q)`。

---

# 模式 D · 操作流不顺畅

## D-1 · ActivityList 跳详情后返回 → 全部状态丢失
- 现状：`ActivityList.tsx:99-102` `sort / order / page / filters` 全是 useState。点击 row `navigate(\`/training/activities/${a.id}\`)` 后再 back，React Router 默认重渲染组件，state 重新初始化。
- 用户视角：用户在第 3 页 + 排序按 avg_power desc + TSS 80-150 过滤，点进一条 → 返回 → 又跳回第 1 页全量列表。需要重新设置。
- 修复方向：`filters / sort / page` 提升到 URL `?sort=avg_power&order=desc&page=2&min_tss=80&max_tss=150`，刷新/分享都保活。

## D-2 · ComparePage 限制 limit 200 + 无日期筛选
- 现状：`ComparePage.tsx:50-58` `listActivities({ limit: 200 })`，全量不分日期。
- 用户视角：用户 1000+ 活动，对比"最近 30 天的 3 个 Z4 训练"，200 条里可能捞不到目标；筛选只能去 ActivityList。
- 修复方向：加日期范围筛选 + 增加分页或日期分组下拉。

## D-3 · 用户偏好存储碎片化 (localStorage 仅 2 处)
- 现状：grep `localStorage` 仅 2 处：`TrendsConfigBar.tsx:42-52` (cc:trends_config_v1) + `BuilderPage.tsx:200,452` (cc:segment_templates)。其他类似偏好（如 ActivityList 排序、Library 默认 source filter、DiaryPage 提示开关）都丢内存。
- 用户视角：用户精心配置 TrendsPage 想看的图表区块 → 刷新页面还在；但配 ActivityList 排序刷新就没了。预期一致行为。
- 修复方向：建 `useUserPrefs` hook + 统一 `cc:user_prefs` JSON 仓库；或后端 `api.userPrefs`。

## D-4 · ChatPage 3 tab 完全独立，无交叉引用
- 现状：`ChatPage.tsx:79-96` `chatMessagesRag / chatMessagesWorkflow / chatMessagesChat` 三个独立数组；切换 tab 完全隔离。
- 用户视角：用户在"训练答疑"问"FTP 怎么测"，得到一段答案；想从"随便聊聊"问同样的问题看 LLM 直答 vs RAG 增强差异，必须复制粘贴；两 tab 历史也无法对照。
- 修复方向：提供"在另一模式重发此问"按钮，或在 workflow 模式 final response 加"对比 rag 模式回答" 链接。

## D-5 · InsightsPage Weekly Review 无法刷新重算
- 现状：`InsightsPage.tsx:41-48` `useEffect(..., [])` 仅挂载时调一次 `api.insightsWeekly()`。
- 用户视角：用户上传新活动后想看"本周 vs 上周"最新对比，必须切走再回来刷新整页。
- 修复方向：标题旁加 `RefreshCw` 按钮调重 fetch + loading 状态；或订阅 store 变化自动 invalidate。

## D-6 · BuilderPage 点击空白不取消，编辑抽屉常驻 1/5 屏
- 现状：`BuilderPage.tsx:583-771` 顶层 `onDragEnd` 但无 `onClick` 取消选中；`EditPanel` (`EditTarget` 非 null 时) 始终渲染。
- 用户视角：用户选中"热身"块 → 编辑抽屉出现 → 满意 → 想看时间轴全貌（去掉抽屉多 1/5 屏）→ 找不到关闭按钮（X 只在选中 block 详情内）。
- 修复方向：时间轴空白处加 `onClick={() => setEditTarget(null)}`；EditPanel 顶部加 "× 折叠" 按钮收缩为图标条。

## D-7 · LibraryPage onDuplicate 后 refresh 失效
- 现状：`LibraryPage.tsx:198-207` `onDuplicate` 后调 `setSource(source)` 同值不触发 useEffect `[source, q, goal, tag]` 重 fetch（L142,145）。
- 用户视角：复制完某课程 toast"已复制：xxx"，列表不刷新，"我的课程"快捷区（L383-405）也不出现新条目。
- 修复方向：抽 `refresh()` 显式函数，onDuplicate / onDelete 后调 `refresh()`；或 setSource 切换为 `prev => prev === 'all' ? 'system' : 'all'`。

## D-8 · DiaryPage 自动保存无重试 / 失败提示
- 现状：`DiaryPage.tsx:125-133` 防抖 1500ms 自动保存，`try/catch` 静默吞错。`DiaryPage.tsx:159-160` `console.error` + `toast.error` 但仅在手动点击"保存"时。
- 用户视角：用户长篇写完训练感受 + 评分，网络瞬断，自动保存失败但界面仍"已保存"（实际未存），用户关闭页面 → 内容全丢。
- 修复方向：自动保存失败时显式 toast "保存失败，已保留本地草稿，可重试"+ 加 `localStorage["cc:diary_draft"]` 暂存。

## D-9 · BuilderPage 撤销栈只 30 步
- 现状：`BuilderPage.tsx:210-214` `setHistory((h) => [...h.slice(-30), blocks])`，超 30 步最早的撤销点丢。
- 用户视角：复杂课程（20 块）用户调 5×5min = 25 步操作，前 5 步无法 Ctrl+Z 还原。
- 修复方向：history 上限提到 100 或无上限（仅受 sessionStorage 配额限制，约 5MB）。

## D-10 · RaceTacticsPage 创建会话后侧栏不会自动滚动到选中项
- 现状：`RaceTacticsPage.tsx:82-92` `setSelectedId(r.session.id)` 后列表 sessions state 已更新但无 scrollIntoView。
- 用户视角：用户已有 10+ 会话列表，新建会话在末尾 → 详情视图打开但左侧列表看不到选中态高亮，"我在哪？"困惑。
- 修复方向：sessions 渲染处加 `ref={selectedId === s.id ? selectedRef : null}` + useEffect 滚动。

---

# 附：硬性量化数据

## `useNavigate` 覆盖率
- 17 个 page 中 9 个有 `useNavigate`：`ActivityDetail / ActivityList / BuilderPage / CalendarPage / ChatPage / ComparePage / Dashboard / ImportPage / LibraryPage`
- 8 个完全无跨页跳转能力：`PhasesPage / InsightsPage / TrendsPage / DiaryPage / KnowledgeBasePage / Profile / FTPTestPage / RaceTacticsPage`（47% 页面是"孤岛"）

## draggable 支持矩阵
- 仅 3 个页面接受 drop：`BuilderPage.tsx:851-1109` (intra-builder 拖块)、`CalendarPage.tsx:140,358` (跨日改期)、`ImportPage.tsx:73-105` (FIT 文件拖入)
- 课程库 LibraryPage 仅支持 `ScheduleModal` (L751-794) 而非 drop，目标日历日格是 drop target 但 LibraryPage 内部卡片不是 drag source —— 真正的"拖到日历" 不存在

## localStorage 用法
- 仅 2 处：`TrendsConfigBar.tsx:42,52` (`cc:trends_config_v1`) + `BuilderPage.tsx:200,452,480` (`cc:segment_templates`)
- 已知应持久化但缺失的偏好：ActivityList 排序/分页/过滤条件、LibraryPage source/goal/tag 过滤、DiaryPage 提示开关与最近日期、BuilderPage 编辑面板状态、ChatPage activeMode + 历史保留策略

## 弹窗 (fixed inset-0) 清单
- 全站 7 处全屏 modal：LibraryPage.tsx:762、PhasesPage.tsx:371 + 591、RaceTacticsPage.tsx:599、FTPTestPage.tsx:494、TrendsConfigBar.tsx:81、ConfirmDialog.tsx:117
- 加 GlobalSearch.tsx:177 (命令面板) + KnowledgeBasePage 无 modal 但 DocDetailView 全屏替换
- 不含 popover / drawer（如 WorkoutDetailDrawer、CalendarPage Popover）。用户从 LibraryPage 切到 ScheduleModal 需 2 次 Esc 才能完全退出

## URL query param 消费方
- grep `useSearchParams` / `location.search`：整个 `apps/web/src` 0 命中
- 即：`GlobalSearch.tsx:142` 跳 `/data/knowledge?path=...`、`Sidebar.tsx:167` 跳 `/data/knowledge?category=...` 均被静默忽略

## Sidebar NAV_GROUPS 与实际路由对照
- Sidebar 列了 13 项；App.tsx 实际路由 17 项（17 page）
- Sidebar 完全没列的 page：`/training/compare`、`/plan` index (BuilderPage)、`/data/ftp-test` 不在 data 组（实际在）但 `SettingsLayout` 组仅 `/settings` (Profile)，FTP 测试硬塞进 data 组语义不通