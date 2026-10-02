# Cycling Coach 用户体验审计报告 V0.8.1

> **目的**:不是看代码, 是站在用户角度, 把 V0.8.1 完整用一遍, 找出"用得不舒服"的地方。
> **视角切换**:从开发者 (代码质量 / 架构) → 用户 (任务完成度 / 心情 / 反复操作)
> **方法**:读 17 个页面 + 公共组件 + AI prompt + 路由 + store, 不需要真跑起来就能定位 UX 痛点。
> **结论先行**:V0.8.1 的"功能完整度"已经是 90%+, "体验完成度"大概 60%。**优化空间大, 单点改动立竿见影**。
> **位置**:`/workspace/cycling-coach/UX_AUDIT_V0.8.1.md`, 不推 GitHub, 等你 review。

---

## 0. 用户画像与典型故事

### 0.1 目标用户 (基于 README + ROADMAP)
- **有功率计的中级公路车爱好者**:FTP 200-300W, 每周训练 6-12 小时, 已经有 100+ 训练数据
- **愿意用数据但不想配硬件**:导入 FIT 文件为主, 不需要 ANT+/BLE 实时连接
- **订阅了 LLM**:已经用 ChatGPT/Claude 帮自己解读训练, 但每次要把数字手抄进去很烦
- **想要"省事"**:希望一个 app 解决"导入 → 看指标 → AI 解读 → 排训练课"全流程

### 0.2 典型一天的用户故事

**故事 A - 周一晚上 22:00, 周复盘**:
> 周末骑了 2 次, 想看本周训练量跟上周比怎么样, 然后跟 AI 教练聊"下周该练什么"。
> 打开 app → Sidebar 点 "趋势" → 看周 TSS 柱状图 → 切 "AI 教练" → 选 "训练答疑" tab → 输 "本周累计 580 TSS 是不是太狠了?"
> 期望: 30 秒看到对比图, 1 分钟看到 AI 解读带具体数字

**故事 B - 训练后 5 分钟, 餐厅里**:
> 上午骑完 100km 回到家, 汗还没干, 想快速上传 FIT, 标记 RPE, 顺便让 AI 生成报告。
> 打开 app → 拖 FIT 到 "导入" → 等 5 秒解析 → 跳到详情 → 看到指标全出来 → 输 RPE = 7 → 点 "AI 分析" → 关 app 洗澡 → 回来后看 AI 报告
> 期望: 整个流程 < 60 秒, AI 报告在洗澡时生成好

**故事 C - 赛前 4 周**:
> 有个 100km 公路赛, 想让 AI 给我一个 4 周训练计划 + 比赛当天战术。
> 打开 app → "比赛战术" → 新建会话 (类型 = "公路赛", 比赛日 = 4 周后) → 选填优先级 A → 上传路书 PDF → "今天该怎么练?" → AI 流式回复
> 期望: 3 分钟内拿到一份可执行方案

---

## 1. 体验问题清单 (按"对用户最直接的影响"排序)

### 🔴 P0 - 直接劝退 / 看起来"产品坏了"

#### U-1. 顶部搜索框是死按钮 🔴
- **位置**: `TopBar.tsx:18-26`
- **问题**: 有 `<input placeholder="搜索训练…">` 但**没有 onChange / onSubmit**, 输入什么都不发生
- **影响**: 第一次用就发现"产品有个按钮按不动", 信任崩
- **修复**: 至少做全局 Cmd+K 搜索 (活动 / 训练日记 / KB 文章), 做不到就**直接删这个 input** 别留死按钮
- **工时**: 1h 删 / 8h 真做

#### U-2. 8 个页面还在用原生 `alert()` / `confirm()` 🔴
- **位置**: grep 出 12 处原生 alert/confirm
  - `PhasesPage.tsx`: 3 处 (alert + 2 个 confirm)
  - `RaceTacticsPage.tsx`: 2 处
  - `LibraryPage.tsx`: 2 处
  - `BuilderPage.tsx` / `CalendarPage.tsx` / `ChatPage.tsx` / `DiaryPage.tsx` / `FTPTestPage.tsx`: 各 1 处
- **问题**: 项目**已经写了** `ConfirmDialog` 公共组件 (`components/common/ConfirmDialog.tsx`), 但**没人用**。原生 confirm 在 Electron 桌面模式会阻塞 event-loop, 在某些浏览器可能被屏蔽
- **影响**: 整个产品看起来"业余", 用户操作时突然弹原生框, 风格不一致
- **修复**: 12 处全部换成 `ConfirmDialog` / `toast.error()`, 半天干完
- **工时**: 0.5d

#### U-3. Profile 改了不点保存全丢 🔴
- **位置**: `Profile.tsx:32-45`
- **问题**: 用 `onChange` 累积到 `editing` 状态, **用户改了 7 个字段 + 关浏览器 = 全丢**。没 dirty 警告、没自动保存、没 "未保存" 提示
- **影响**: 用户的 FTP / 体重改了一通, 误关页面, 全部没了, 再来一次
- **修复 (3 选 1)**:
  1. **加 dirty 警告**: 离开页面前 `beforeunload` 提示
  2. **加自动保存**: 跟 DiaryPage 学 (`setTimeout(1500ms)` debounce)
  3. **加 "保存" 按钮高亮**: 改了之后按钮变红 + 标 "有 3 项未保存"
- **工时**: 0.5d

#### U-4. AI 报告生成超时只有 60s 兜底 🔴
- **位置**: `ActivityDetail.tsx:103-122`
- **问题**: `setInterval(2000)` 轮询 + `setTimeout(60000)` 兜底。LLM 慢的时候 30-60s 是常态, **真超时就 `setAnalyzing(false)` 但 `report_status` 可能还在 "analyzing"**, UI 状态错乱
- **影响**: 用户看 60s "分析中...", 然后突然没了, 不知道是好了还是挂了。点了 "AI 分析" 没反应
- **修复**:
  1. 兜底时间改 120s
  2. 超时前明确告诉用户"LLM 慢, 再等 30s"
  3. 超时后给 "取消" / "重试" 二选一按钮
- **工时**: 0.5d

#### U-5. Mock 模式在 TopBar 显眼展示 🔴
- **位置**: `TopBar.tsx:33-42`
- **问题**: 顶部右侧展示 "Mock 模式" / "AI 在线" 状态, **每次进 app 第一眼看到**
- **影响**: 没配 key 的用户 (90% 新用户) 看到 "Mock 模式" 立刻觉得"哦我用的是假 AI, 没用"。实际 Mock 引擎质量还行 (`mock_engine.py` 414 行), 但用户不知道
- **修复**:
  - 把这个 indicator 移到 `/settings` 或者一个 "诊断" 弹窗里
  - TopBar 不要再显示
- **工时**: 0.5d

#### U-6. 训练日记 / 知识库 / 比赛战术: 路由别名混乱 🔴
- **位置**: `Sidebar.tsx:42-48`
- **问题**: Sidebar 写"训练洞察" 但 URL 是 `/ai/hrv`, "FTP 测试" 但 URL 是 `/data/ftp-test`。用户分享链接或者收藏夹, 看不懂
- **影响**: 用户不知道 "训练洞察" 跟 "HRV" 是一个东西
- **修复**: Sidebar 改成更清晰的中文名, 或者 URL 跟 Sidebar 标签对齐
  - "训练洞察" → "HRV / 训练健康"
  - "FTP 测试" → "FTP 校准"
- **工时**: 0.5h

---

### 🟡 P1 - 用得别扭, 不修用户会"凑合用"

#### U-7. Sidebar 15 项平铺, 没分组 🟡
- **位置**: `Sidebar.tsx:42-58`
- **问题**: 15 项一字排开, 跨"训练 / AI / 计划 / 数据 / 设置"5 大类, 但**视觉上完全平铺**, 没分隔线、没标题、没折叠
- **影响**: 找一项要扫 15 行; 6 个月后新增几个功能就 20+ 行, 灾难
- **修复**: 加分组标题 ("训练" / "AI 教练" / "训练计划" / "数据" / "设置") + 折叠能力
- **工时**: 1d

#### U-8. TopBar 通知铃铛是死按钮 🟡
- **位置**: `TopBar.tsx:45-47`
- **问题**: `<button>` 包 `<Bell>` 但**没 onClick**。点啥都不发生
- **影响**: 跟 U-1 一样, 用户发现"产品有按钮按不动"
- **修复**: 至少做成"未读洞察数 badge", 真的做通知 (HRV 异常 / FTP 复测提醒 / 比赛临近) — 后者值得做
- **工时**: 1h 删 / 1-2d 真做

#### U-9. AI 报告生成期间没有"取消"按钮 🟡
- **位置**: `ActivityDetail.tsx:104-122`
- **问题**: "分析中..." 状态 30-60s, **用户没法取消**, 只能等或者关页面
- **影响**: 用户上传错了活动 + 点了 AI 分析, 只能干等 60s
- **修复**: 加 "停止分析" 按钮 → 调 `api.cancelAnalyze(id)` (后端需要补一个 cancel 端点)
- **工时**: 1d (前端 0.5d + 后端 cancel 端点 0.5d)

#### U-10. InsightsPage 加载状态简陋 🟡
- **位置**: `InsightsPage.tsx:42-50`
- **问题**: 加载中是"加载中..."纯文本, 空数据是"暂无数据"纯文本, **没用项目已有的 `EmptyState` 组件**
- **影响**: 风格不统一, 跟 Dashboard 的 EmptyState 不一致
- **修复**: 全部换成 `<EmptyState>` + `<LoadingSkeleton variant="card">`
- **工时**: 0.5d

#### U-11. KB 自己写 markdown 渲染器 🟡
- **位置**: `KnowledgeBasePage.tsx:30-55`
- **问题**: 用 `dangerouslySetInnerHTML` + 自己写的正则替换渲染 markdown。**项目已经在 ChatPage 用 `react-markdown` + `rehype-sanitize`**, 这里却自己造一个
- **影响**:
  - 安全性: 任何 KB 内容渲染都走 dangerouslySetInnerHTML, **rehype-sanitize 在这没用**, XSS 风险面
  - 维护性: 修了 KB 样式, 还得修 chat markdown 样式
- **修复**: 统一用 `react-markdown` + `rehype-sanitize`, 加自定义组件 (image / code / list)
- **工时**: 1d

#### U-12. AI 教练流式解析 `[THINK]xxx[/THINK]` 是 hack 🟡
- **位置**: `ChatPage.tsx:160-180`
- **问题**: 客户端用 `chunk.indexOf("[THINK]")` 解析 LLM 流式输出里的 thinking 块。**LLM 不会按你规规矩矩输出 `[THINK]xxx[/THINK]`**, 半路切开会乱
- **影响**: 流式过程中"思考内容"和"最终回答"会串台, 用户看到乱七八糟
- **修复**:
  - 短期: LLM prompt 里硬性要求 "## Thinking\nxxx\n## Answer\nyyy" 这种 markdown 标题, 客户端按标题切
  - 长期: 后端解析 thinking + 拆 2 个 SSE channel (`event: thinking` / `event: answer`)
- **工时**: 0.5d 短期 / 2d 长期

#### U-13. ComparePage 错误展示简陋 🟡
- **位置**: `ComparePage.tsx:30, 75`
- **问题**: `setError(String(e?.message || e))` 直接显示原始错误; 加载失败和空数据都是 "加载活动列表…"
- **影响**: 出错时用户看到 `Error: HTTP 500: Internal Server Error` 这种 raw 信息, 不知道咋办
- **修复**: 用 `toast.error()` 通知, 主区显示 `<EmptyState icon={AlertCircle} title="对比失败" description={...} cta={重试} />`
- **工时**: 0.5d

#### U-14. 4 处直接 `fetch()` 不走 `api` 客户端 🟡
- **位置**:
  - `Profile.tsx:24` `fetch("/api/athlete/refresh-ftp", { method: "POST" })`
  - `RaceTacticsPage.tsx:101, 137` 用了 SSE 不能用 `api.jsonFetch`
  - `LibraryPage.tsx:39` `fetch("/api/dev/repair-db", { method: "POST" })`
- **问题**: RaceTacticsPage 是 SSE 特殊场景必须直接 fetch, 但 Profile / LibraryPage 不该用
- **影响**: 错误处理不一致; `LibraryPage` 的 repair-db 失败 toast 不出来
- **修复**: Profile / LibraryPage 走 `api` 客户端; RaceTacticsPage 抽一个 `api.sseStream()` helper
- **工时**: 0.5d

#### U-15. 上传 FIT 文件没有"重复检测" 🟡
- **位置**: `ImportPage.tsx:25-50`
- **问题**: 上传同一个 FIT 文件, **会再创建一条 activity** (虽然 service 层有 `file_path` 唯一约束, 但前端没 prompt 也没"已存在"提示)
- **影响**: 用户不小心拖 2 次, 数据库多一条, 报告重复
- **修复**: 上传前 `api.checkDuplicate(file)` (按 start_time + duration 查), 有重复弹 "已存在, 是否覆盖?"
- **工时**: 1d (前端 0.5d + 后端 0.5d)

#### U-16. AI 报告"分析中..."没有进度感 🟡
- **位置**: `ActivityDetail.tsx:104-122` + `analyze.py` prompt
- **问题**: LLM 通常 20-40s 出结果, 用户干等 30s 不知道还要多久
- **影响**: 焦虑 + 容易误关页面
- **修复**:
  - 加一个 LoadingSkeleton 显示 "分析中..." 加 "AI 正在读你的功率曲线..." 这种动态文案
  - 改前端 SSE 接收: 后端推 `event: progress` (data: {stage: "reading_power_curve"}), 前端显示对应文案
- **工时**: 1d

---

### 🟢 P2 - 锦上添花, 用户主动说"好用"那种

#### U-17. Sidebar 没"最近活动"快捷入口 🟢
- **位置**: `Sidebar.tsx`
- **问题**: 想看昨天那次活动, 要点 "训练" → 翻列表 → 找日期。每次 3 步
- **修复**: Sidebar 底部加 "最近 3 个活动" 链接
- **工时**: 0.5d

#### U-18. Dashboard "重建 PMC" 按钮是 dev 工具 🟢
- **位置**: `Dashboard.tsx:106-116`
- **问题**: 任何用户都能点 "重建 PMC" (调 `api.rebuildPMC()`), 普通用户不应该碰
- **影响**: 用户瞎点, 性能差的时候体感更慢
- **修复**: 移到 `/settings` 加 dev_mode 门控
- **工时**: 0.5d

#### U-19. 训练日记 9 个字段全暴露, 没模板引导 🟢
- **位置**: `DiaryPage.tsx`
- **问题**: 字段 9 个 (感受/心情/睡眠/睡眠质量/正文/天气/装备/痛点/活动关联), 第一次用 user 不知道填啥
- **修复**: 加 onboarding tooltip, 或 "今日提示" 引导
- **工时**: 0.5d

#### U-20. 知识库搜索结果没有"为什么这篇" 🟢
- **位置**: `KnowledgeBasePage.tsx`
- **问题**: 搜索 "FTP" 出 30 条, 每条都长得像, 不知道该看哪条
- **修复**: 搜索结果高亮命中片段 (已有 `highlight` 函数, 没用上), 加 "相关度" badge
- **工时**: 0.5d

#### U-21. BuilderPage 1701 行, 拖拽体验能再优化 🟢
- **位置**: `BuilderPage.tsx`
- **问题**: 拖块到时间轴时插入线太细, 块放下后无 undo toast (键盘 Cmd+Z 不一定灵)
- **修复**: 插入线加粗 + 颜色; 每次操作右下角 toast "已保存草稿 / 已撤销"
- **工时**: 1d

#### U-22. AI 教练"参考知识库"来源点进去是死的 🟢
- **位置**: `ChatPage.tsx` (RAG mode 流)
- **问题**: AI 回答后面标 "[1] 训练百科/FTP 怎么测", 但**点击不跳转到 KB 那篇**
- **影响**: 引用形式在, 用户没法 follow up
- **修复**: 引用加 `onClick → navigate('/data/knowledge?path=...')`
- **工时**: 0.5d

#### U-23. 比赛战术会话列表没"状态"标识 🟢
- **位置**: `RaceTacticsPage.tsx`
- **问题**: 7 种比赛类型 × 3 优先级 (A/B/C), 但列表卡只显示标题, **没类型色标 / 优先级徽章**
- **影响**: 一堆会话堆在那, 不知道哪个紧急
- **修复**: 卡片左上 A/B/C 徽章 + 比赛类型色条
- **工时**: 0.5d

#### U-24. InsightsPage 8 区域一屏装不下, 没锚点导航 🟢
- **位置**: `InsightsPage.tsx`
- **问题**: 健康分 / 今日洞察 / 强度分布 / RPE / ACWR / HRV / 周报... 一屏装不下, 滚下去找不到刚看的
- **修复**: 顶部 sticky tab 锚点 (类似 ChatPage 的 3 mode tab)
- **工时**: 0.5d

#### U-25. Toast 不能"撤销"操作 🟢
- **位置**: `Toast.tsx`
- **问题**: 删了一条活动, toast 说"已删除", 但**用户没法 undo**。Toast 只有 info, 没有 action
- **修复**: Toast 加可选 `action: { label: "撤销", onClick: ... }` 字段
- **工时**: 0.5d

---

## 2. 用户旅程体验问题映射

### 2.1 旅程 A: 周一晚上 22:00 周复盘
| 步骤 | 用户操作 | 体验问题 |
|---|---|---|
| 1 | 开 app | U-7 找 "趋势" 要扫 15 行 Sidebar |
| 2 | 点 "趋势" | 加载中 3s, 不知道是慢还是挂了 |
| 3 | 看 TSS 柱状图 | OK, 但**没法对比上周同一天**, 要切到 InsightsPage |
| 4 | 切 "AI 教练" | U-6 路由混淆, "AI 教练" 跟 "比赛战术" 是同级, 用户犹豫 |
| 5 | 输问题 | OK, 4 个 quick suggestions 帮了 |
| 6 | 等 AI 回答 | U-12 `[THINK]` hack, 流式文本可能乱 |
| 7 | AI 引用 KB | U-22 引用点不进去 |

**总评**: 3 步顺畅, 4 步卡顿。可以接受, 但**离"爽"还差**。

### 2.2 旅程 B: 训练后快速上传 + AI 报告
| 步骤 | 用户操作 | 体验问题 |
|---|---|---|
| 1 | 开 app | U-1/U-8 看到两个死按钮 (搜索 + 通知) |
| 2 | 拖 FIT | OK, drag-drop 工作 |
| 3 | 看进度 | 0-100% 进度条 OK, **但 XHR 进度**实际不一定准 (FastAPI 后端) |
| 4 | 跳详情 | OK, 自动跳 |
| 5 | 输 RPE = 7 | OK, RPEEditor 组件好 |
| 6 | 点 "AI 分析" | U-4 60s timeout 兜底, U-16 没进度感, U-9 没法取消 |
| 7 | 洗澡回来 | U-13 报告生成失败 toast 简陋 |

**总评**: 上传 3 步丝滑, AI 报告这一步是**最大痛点**。

### 2.3 旅程 C: 赛前 4 周规划
| 步骤 | 用户操作 | 体验问题 |
|---|---|---|
| 1 | 点 "比赛战术" | OK |
| 2 | 新建会话 | U-2 用了 confirm 原生框 (创建后删除会话) |
| 3 | 填比赛信息 | OK, RaceTypePicker 好用 |
| 4 | 传路书 PDF | 不知道支持哪些格式? U-2 confirm 又来 |
| 5 | "今天怎么练" | OK, 流式 |
| 6 | AI 给方案 | U-22 KB 引用点不进去 |

**总评**: 整套流程能用, 但 confirm 弹窗 + 引用死链 扣分。

---

## 3. 优化优先级矩阵

| 影响 / 成本 | 低 (0.5d) | 中 (1d) | 高 (2d+) |
|---|---|---|---|
| **高 (改完用户立刻感知)** | U-1 删死按钮<br>U-2 全替 confirm<br>U-3 Profile 改保存<br>U-5 藏 Mock<br>U-6 Sidebar 标签 | U-4 AI 报告超时修<br>U-9 加取消按钮<br>U-15 重复检测 | U-11 KB 渲染统一<br>U-12 AI 流式拆通道 |
| **中 (改完用户体验更顺)** | U-10 EmptyState 统一<br>U-14 fetch 统一<br>U-22 KB 引用跳转 | U-7 Sidebar 分组<br>U-13 错误展示<br>U-16 报告进度 | — |
| **低 (锦上添花)** | U-17 最近活动<br>U-18 隐藏 dev 按钮<br>U-23 比赛状态色<br>U-25 Toast undo | U-19 训练日记引导<br>U-20 搜索高亮<br>U-21 Builder 拖拽优化 | U-8 真做通知<br>U-24 Insights 锚点 |

---

## 4. 推荐执行顺序 (1 周可交付明显改善)

### Day 1: 清死按钮 + 改 confirm
- U-1 删 TopBar 搜索框 (改成 Cmd+K 触发 popover search, 0.5d)
- U-2 全 12 处 confirm/alert 改 ConfirmDialog / toast (0.5d)
- U-5 Mock indicator 移到 Settings (0.5d)
- U-8 通知按钮加未读 badge (0.5d)

### Day 2: 用户能感知的"修了"的小修
- U-3 Profile 自动保存 + dirty 警告 (0.5d)
- U-4 AI 报告超时改 120s + 友好提示 (0.5d)
- U-6 Sidebar 标签清晰化 (0.5h)
- U-10 InsightsPage 改 EmptyState (0.5d)
- U-13 ComparePage 错误用 toast + EmptyState (0.5d)
- U-14 fetch 统一 (0.5d)

### Day 3: AI 体验核心修复
- U-9 AI 报告加 "取消" 按钮 (1d, 含后端 cancel 端点)

### Day 4: 内容 & 引用
- U-22 AI 教练 KB 引用可点击 (0.5d)
- U-20 KB 搜索高亮 (0.5d)
- U-23 比赛战术状态色 (0.5d)
- U-12 AI 流式改 markdown 标题切 (0.5d)

### Day 5: 收口
- U-15 重复文件检测 (1d, 含后端)
- 留出半天做回归测试

**1 周交付 14 项 UX 修复, 单人工作量, 不动业务逻辑**

---

## 5. 不建议做的事 (这次)

- ❌ **重写 Dashboard**: 现有功能齐, 改完体感提升有限
- ❌ **统一 17 个页面的视觉**: 锦上添花, 但工程量大
- ❌ **做深色模式**: 用户没要, 优先级低
- ❌ **做 PWA / 移动端响应式**: 大工程, 单点体验提升不如 P0/P1 那些
- ❌ **重新设计 AI prompt**: 现有 prompt 已经够专业, 改完质量提升不一定有
- ❌ **动 Service 层业务逻辑**: 跟体验优化无关, 改完反而有回归风险
- ❌ **加测试**: 工程债, 不是体验债

---

## 6. 用户调研问题 (后续可做)

1. **5 个真实用户跑一遍**: 找 5 个有功率计的朋友, 给 FIT 文件, 让他们用 1 周, 记下哪里卡
2. **录屏**: 用 OBS 录自己用 30 分钟, 看自己卡在哪里
3. **NPS 调研**: 3 个核心问题 (会推荐吗 / 最有用 / 最没用)
4. **A/B 测试 AI 报告长度**: 现在限制 400 字, 试试 200/400/600 哪个用户更满意

---

## 7. 下一步: 你拍板

按你的工作流 ("先规划、再执行、先给 zip 预览、用户同意后才推 GitHub"):

1. **现在**:
   - 这份报告在 `/workspace/cycling-coach/UX_AUDIT_V0.8.1.md` ✅
   - 没动任何业务代码
   - 没推 GitHub
   - 跟上一份 `ENGINEERING_AUDIT_V0.8.1.md` 配对 (一份工程, 一份 UX)

2. **等你决定**:
   - **A**: 同意 Day 1-5 排期, 1 周全清 (14 项修复) — 我按天给你 diff 摘要, 同意一个 commit 一个
   - **B**: 只清 Day 1 (5 个最容易的修复) — 半天拿小胜利
   - **C**: 改优先级, 某条挑出来先做 / 后做 — 你说
   - **D**: 整个方案要重做 — 你说方向

3. **不会发生**:
   - 不会推任何东西到 GitHub
   - 不会动后端 service 层 / 业务逻辑 / 数据库 schema
   - 不会改 AI prompt (除非 U-12 短期方案需要)
   - 不会动工程审计那份报告的任务 (CI / 测试覆盖 / 性能基线) — 那些是工程债, 等这次 UX 清完再做

你拍。
