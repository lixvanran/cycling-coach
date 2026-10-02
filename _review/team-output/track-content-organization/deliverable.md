# 内容/数据组织审计 (Track E)

## Summary

扫描了 KB 文档 (359 个 md / 8 个一级分类)、KnowledgeBasePage / Sidebar / Profile / LibraryPage / PhasesPage / InsightsPage / TrendsPage / DiaryPage / ComparePage / App.tsx 路由归属, 锁定 **E-1 ~ E-14 共 14 条内容/数据散乱问题**, 附 KB 内部导航问题清单 / 同类项分散 page 清单 / 路由有但入口缺清单 / KB 最深嵌套的具体文档路径。每条带 `file_path:line_number` 证据。

量化指标: KB 文档 359 个 (8 个一级 / 训练百科 6 层目录深 / 最深文档 8 层路径深) / Insights 4 个独立 page 占用 2 个 Sidebar 槽位 / ComparePage 路由可达但 Sidebar 0 入口 / Profile 7 字段 1 页面 0 分组 / LibraryPage WorkoutDetailDrawer (lines 554-742) 无编辑入口。

## Changed files

- `/workspace/.mavis/plans/plan_1ca7f41a/outputs/track-content-organization/deliverable.md` (本文件)
- `/workspace/.mavis/plans/plan_1ca7f41a/board.md` (进度)

## Notes

- 所有 file:line 引用基于当前 `apps/web/src/` 实际代码, 行号会随增量改动漂移
- 验证命令: `find kb_source/markdown -name "*.md" | wc -l` → 359
- 验证命令: `find kb_source/markdown -mindepth 1 -maxdepth 1 -type d | wc -l` → 8
- 验证命令: `find kb_source/markdown -name "*.md" -printf "%d\n" | awk '{c[$1]++} END{for(d in c)print d,c[d]}' | sort -n` → 深度 2~8

---

## E-1 KB 训练百科目录嵌套失控 (5 层目录)

**现状** `kb_source/markdown/训练百科__061370d6/` 下: 10 个二级目录, 42 个三级目录, 141 个四级目录, 77 个五级目录, 11 个六级目录。最深文档在 8 层路径深。
**证据** `find kb_source/markdown -mindepth N -maxdepth N -type d` 计数:
```
训练百科__061370d6
  depth=2  count=10    (e.g. 2. 训练方法__0afdf618)
  depth=3  count=42    (e.g. 副本2.5 室内训练（骑行台）（o）__d5baeb8c)
  depth=4  count=141   (e.g. 2.5.5如何使用功率骑行台__bcd01920)
  depth=5  count=77    (e.g. 6.4 骑行软件（APP）__d39e08fd)
  depth=6  count=11    (e.g. 6.4.6 TrainerRoad__0a1625fd)
```
**影响** 用户从 Sidebar 一级「训练百科」点进去, 至少要下钻 4~5 层才能看到文档; KnowledgeBasePage 树视图 (`apps/web/src/pages/KnowledgeBasePage.tsx:316-419` CategorySidebar) 仅支持 2 层 (顶级 + 子), 子层以下变成黑盒面包屑。
**最深文档路径举例** (8 层, 出现在 `find kb_source/markdown -name "*.md" -printf "%d %p\n" | sort -nr | head`):
```
训练百科__061370d6/2. 训练方法__0afdf618/副本2.5 室内训练（骑行台）（o）__d5baeb8c/
  2.5.5如何使用功率骑行台__bcd01920/6.4 骑行软件（APP）__d39e08fd/
  6.4.6 TrainerRoad__0a1625fd/6.4.7 iGpsport__e5704f3c/_content.md
```
(以及 6.4.3 顽鹿竞技、6.4.4 Garmin connect 2 个兄弟下还有更多 7~8 层嵌套)
**建议聚合点** 知识库导入/迁移工具收口到 `kb_source/build/` 输出 ≤3 层 (一级 / 主题 / 文档), 旧目录归档到 `_archive/`。

## E-2 KB hover 菜单只显 8 个顶级, 子级黑洞

**现状** `apps/web/src/components/Sidebar.tsx:86-93` 拉 `kbCategories` 后 `.filter((c:any) => c.path.split("/").length === 1)`, hover 只显示 8 个顶级, 训练百科 1 个一级覆盖 288 个文档 (count=288 占 80%), 用户无法跳过一级直接定位。
**证据** `find kb_source/markdown -mindepth 1 -maxdepth 1 -type d | while read d; do echo $(find "$d" -name "*.md" | wc -l) $(basename "$d")"; done | sort -nr`:
```
288 训练百科__061370d6
 29 专业术语__023cfa38
 16 青少年专题__184d828a
 11 高级训练知识__50fdea8c
  6 执教知识__bb3c1c21
  5 教练随笔__f1033205
  3 竞技百科__65aec080
  1 双语课堂__2233060f
```
**影响** 想找「iGpsport」必须: 知识库 → 训练百科 → 训练方法 → 室内训练 → 如何使用功率骑行台 → 骑行软件 APP → iGpsport (7 跳)。
**建议聚合点** Sidebar hover 加「最近浏览」「热门文档 Top10」快速通道; KB 详情页加 related docs / same parent 跳转 (在 KnowledgeBasePage.tsx:610 DocDetailView 内)。

## E-3 Sidebar `?category=...` query 是 dead param

**现状** `apps/web/src/components/Sidebar.tsx:167` 点击顶级分类调用 `navigate('/data/knowledge?category=${cat.path}')`, 但 `apps/web/src/pages/KnowledgeBasePage.tsx` **从不读 `category` query param** (grep `useSearchParams\|searchParams` 在该文件 0 命中)。同样 `apps/web/src/components/GlobalSearch.tsx:142` 的 `?path=...` 也是 dead param (KnowledgeBasePage 0 reader)。
**影响** 用户从 Sidebar 二级菜单点了训练百科, 期待直接进入分类, 实际仍回根目录全部文档列表, 必须再点侧边树。
**建议聚合点** KnowledgeBasePage 顶层 `useSearchParams()` + `useEffect` 把 `category` / `path` 写入 selectedPath state, 0 行业务改。

## E-4 KB 搜索 0 过滤维度

**现状** `apps/web/src/pages/KnowledgeBasePage.tsx:124-135` 搜索只接受 `q: string, limit=30`, API `apps/web/src/lib/api.ts:682-687` 同。`HOT_TAGS` (lines 21-28) 是写死的 6 个热门词, 不是动态热门。
**影响** 用户无法按「只看训练百科」「只看附件文档」「只看近 1 年编辑」过滤, 359 篇文档搜索 30 条命中率低 (288 篇在训练百科, FTP 命中训练百科外概率近 0)。
**建议聚合点** KnowledgeBasePage 搜索框右侧加 `category` 下拉 + 时间范围, 复用 Sidebar 的 categories 数据 (`api.kbCategories()` 已经在用)。

## E-5 Profile 7+ 字段堆一个 "基础信息" section 0 分组

**现状** `apps/web/src/pages/Profile.tsx:118-126` `fields` 数组硬编码 7 个字段: `name` (标识) / `ftp` + `ftp_estimated` (功率) / `max_hr` + `lthr` (心率) / `weight_kg` + `height_cm` (身体)。整个 panel header 就叫「基础信息」(`Profile.tsx:190`), 7 行共用同一份 grid 模板 (`Profile.tsx:207` `grid grid-cols-3`)。
**证据** Athlete interface (`apps/web/src/lib/types.ts:71-82`) 也只有这 7 个字段, 没分组标签。
**影响** 用户改 FTP 时还得滚到第 2 行; 没有"功率/心率/身体" 3 个 section 视觉分组, 跟 TrainingPeaks / Intervals.icu 风格脱节。
**建议聚合点** Profile 拆 3 个 panel: 「身份」「生理指标 (FTP/HR)」「身体参数 (体重/身高)」; 字段 group 在 `apps/web/src/lib/types.ts:71` 用嵌套 interface 表达。

## E-6 FTP 相关分散 3 个页面 + Profile 内嵌按钮

**现状** FTP 功能散落在 3 处:
1. `apps/web/src/pages/Profile.tsx:104-116` `onRefreshFtp` + `apps/web/src/pages/Profile.tsx:192-198` 「重算 FTP」按钮 → `/athlete/refresh-ftp`
2. `apps/web/src/pages/FTPTestPage.tsx` (571 行) 完整 FTP 测试页: 测试协议 / 历史 / 估算 / 智能推荐
3. `apps/web/src/pages/ActivityDetail.tsx:50,279-303` 「运行估算」单活动内嵌 → `/ftp/estimate`
**影响** 用户想"看自己 FTP 历史趋势", 必须跳 FTP 校准页; 在 Profile 页「重算」只改估算值, 跟测试值混淆 (Athlete 接口 `ftp` vs `ftp_estimated`, `apps/web/src/lib/types.ts:74-75`)。
**建议聚合点** Profile 把 FTP 折成"显示 FTP=265W · 估算=260W · 历史曲线"组件, link 到 FTPTestPage 看详情; 移除 Profile 内嵌的「重算 FTP」按钮 (FTPTestPage 已含)。

## E-7 LibraryPage WorkoutDetailDrawer 缺「编辑」按钮

**现状** `apps/web/src/pages/LibraryPage.tsx:554-742` WorkoutDetailDrawer 底部只有 4 个动作:
- 排到日历 (lines 678-691)
- 导出 .zwo/.mrc/.erg (lines 692-718)
- 复制到我的 / 删除 (lines 719-738)
- **无「编辑课程」入口**
**证据** grep `updateWorkout\|editWorkout\|editingId\|/plan/\${id}` 在 LibraryPage 0 命中; `BuilderPage.tsx:272-283 loadFromWorkout` 有 `editing` state, 但只有 Builder 内部 `myWorkouts` 列表 (`BuilderPage.tsx:781`) 调用, LibraryPage 没跳。
**影响** 用户想微调自己创建的课程, 必须: 课程库 → 记住 ID → 跳 /plan → 在 Builder 内 myWorkouts 列表里找 → 点编辑。多 3~4 跳。
**建议聚合点** WorkoutDetailDrawer 底部加 `<button onClick={() => navigate(\`/plan?id=${w.id}\`)}>编辑</button>`, BuilderPage 用 `useSearchParams` 读 id 调 `loadFromWorkout` (BuilderPage.tsx:272 已具备该能力)。

## E-8 Insights 拆 4 个独立 page + TrendsPage 跟 DiaryPage 不同路由组

**现状** "洞察/数据" 拆 4 个独立 page:
- `apps/web/src/pages/InsightsPage.tsx` (286 行) → `/ai/hrv` (Sidebar 占「HRV / 训练健康」, `Sidebar.tsx:53`)
- `apps/web/src/pages/TrendsPage.tsx` (370 行) → `/training/trends` (Sidebar 占「趋势」, `Sidebar.tsx:44`)
- `apps/web/src/pages/DiaryPage.tsx` (495 行) → `/training/diary` (Sidebar 占「训练日记」, `Sidebar.tsx:45`)
- `apps/web/src/pages/ComparePage.tsx` (336 行) → `/training/compare` (Sidebar 0 入口)

**影响** 周复盘 (Insights) 跟每日趋势 (Trends) 跟日记 (Diary) 都在不同 nav group (AI 教练 / 训练), 用户做一次完整复盘要切 3 个 group。Compare 完全隐身。
**建议聚合点** 新 `pages/InsightsPage.tsx` 单页整合: Tab1 周复盘 / Tab2 长期趋势 / Tab3 训练日记 / Tab4 活动对比; 旧 4 个 page 降级为内部组件。

## E-9 ComparePage 路由可达但 Sidebar 0 入口

**现状** `apps/web/src/App.tsx:104-111` 路由 `/training/compare` 注册了 ComparePage, 但 `Sidebar.tsx:38-79` 5 个 NAV_GROUPS 没有 `compare` 项。`hooks/useLegacyRedirect.ts:33` 把旧 `#compare` 重定向到 `/training/activities` (占位), 用户从老链接进来落到训练列表。
**证据** grep `to=.*compare\|compare.*Sidebar` 在 apps/web/src/components/Sidebar.tsx 0 命中。
**影响** 336 行 ComparePage 代码完全死代码; 路由加载了 lazy chunk 但永远无人访问。
**建议聚合点** Sidebar 「训练」组加 `{ to: "/training/compare", label: "活动对比", icon: GitCompare }`, 或合并到 Insights 统一 Tab (见 E-8)。

## E-10 DiaryPage 495 行 + 跟 Activity 同天数据无并排

**现状** `apps/web/src/pages/DiaryPage.tsx:60-495` 13 个 state (training_feel/mood/sleep_h/sleep_quality/content/weather/equipment_notes/pain_notes/activity_id 等), 单列布局, Activity 是通过 `activity_id` 关联 (line 82, line 145-147) 但页内不展示该 activity 摘要。
**证据** DiaryPage grep `ActivitySummary\|power\|duration\|tss\|avg_hr` 0 命中; 只在 line 401 `<option>` 里给个 `start_time · title · min`。
**影响** 用户写日记看不到今天骑了 80km / TSS 120 / 60min Z2 是什么, 得切 Activity tab 查再切回来。
**建议聚合点** DiaryPage 加 sticky right rail 渲染当天 activity 关键指标 (avg_power/NP/TSS/HR/zones), 复用 `apps/web/src/components/MetricCard.tsx`。

## E-11 Workout Tags/Goals 0 管理界面

**现状** `apps/web/src/lib/api.ts:631-634` 暴露 `listWorkoutTags()` `listWorkoutGoals()` 只读接口; `apps/web/src/pages/LibraryPage.tsx:124-129` 拉取用作筛选下拉 (line 312-325)。没有 create/update/delete UI。
**证据** grep `createWorkoutTag\|updateWorkoutTag\|workoutGoal.*create` 在整个 apps/web/src 0 命中。
**影响** 课程标签库是写死 seed 的 (`cycling_coach/seed_workouts.py` 之类的 seed), 用户无法自定义 (e.g. 加上「高原训练」「冬训」标签)。
**建议聚合点** Profile / Settings 加 "训练标签库" section, 复用 Toast 跟 Confirm; API 配套加 POST/PATCH/DELETE `/workouts/tags`。

## E-12 Phase 模板 0 独立入口 + 跟 Builder 无 link

**现状** `apps/web/src/pages/PhasesPage.tsx:544-588` PhaseForm 接受 `phase_type: 7 种` (base/build/peak/taper/recovery/race/rest), meta 来自 `api.phasesMeta()` (硬编码 7 种标签+icon), 但 BuilderPage 跟 PhasesPage 无 link:
- `BuilderPage.tsx` grep `phase\|Phase` 0 命中
- `PhasesPage.tsx` grep `navigate.*plan\|/plan/workouts` 0 命中
**影响** 用户新建 Phase 阶段 (e.g. "9 月强化期 base"), 想批量排课, 没有 "从 Phase 推荐课程" 入口; 反之 BuilderPage 编排完的课程也无法"加入 Phase"。
**建议聚合点** PhasesPage 列表里每行加「推荐课程」按钮 → 跳 `/plan/workouts?goal=X&phase=Y`; BuilderPage 保存后加「加入当前 Phase」按钮, 复用 CalendarPage 已有排课链。

## E-13 KB 文档展示走自写 markdown 渲染, 不解析 frontmatter

**现状** `apps/web/src/pages/KnowledgeBasePage.tsx:31-50 renderMarkdown` 自写 5 个 regex (h1/h2/h3/code/link/list), 不解析 YAML frontmatter / 不显示 doc 元数据 (tags / last_updated / author / source)。`apps/web/src/lib/types.ts` grep `KbDocument` 字段看一下:
**证据** `find kb_source/markdown -name "_content.md" | head` 都是 `<hash>/_content.md`, 元数据靠目录名解析 (`name__hash` 格式)。
**影响** 359 篇文档无标签 / 修订时间展示, 用户无法"按时间看最新文档"或"按 tag 浏览"。
**建议聚合点** 导入脚本把 `_meta.yaml` (title/tags/updated/source) 抽出塞到 KbDocument 表, KnowledgeBasePage DocDetailView (line 209-228) 渲染 metadata block。

## E-14 Race 类型 / Phase 类型 / Workout Goal 3 套并立术语

**现状** 3 套分类体系并存, 互不映射:
- Workout Goal: `recovery/endurance/tempo/threshold/vo2max/race` 6 种 (`LibraryPage.tsx:33-68 GOAL_COLOR`)
- Phase 类型: `base/build/peak/taper/recovery/race/rest` 7 种 (`PhasesPage.tsx:38-46 PHASE_COLORS`)
- Race 类型: `road_race/time_trial/criterium/...` 7 种 (`RaceTypePicker.tsx:1`)
**影响** Phase 类型 `race` 跟 Workout Goal `race` 含义不同, Race Type 又是第三种, 用户混着听。
**建议聚合点** 在 KnowledgeBasePage 加一篇 "术语速查" 文档或在 GlossaryPage (`apps/web/src/pages/` 目前 0) 集中展示映射表。

---

## KB 内部导航问题清单

| # | 问题 | 位置 | 现状 |
|---|------|------|------|
| KB-N1 | tree 仅 2 层 (顶级 + 子级), 4 层以下黑洞 | `KnowledgeBasePage.tsx:316-419` CategorySidebar | 子级以下折叠, 用户靠面包屑走 |
| KB-N2 | hover Sidebar 显示 8 个顶级, 训练百科 1 个独占 288 文档 | `Sidebar.tsx:144-184` | 无"热门子分类"二级菜单 |
| KB-N3 | `?category=...` query 不消费 | `KnowledgeBasePage.tsx` 全文 0 reader | Sidebar 跳完跳根目录 |
| KB-N4 | `?path=...` query 不消费 | `KnowledgeBasePage.tsx` 全文 0 reader | GlobalSearch 跳完跳根目录 |
| KB-N5 | 搜索 0 过滤维度 (类别/时间/作者) | `KnowledgeBasePage.tsx:124-135` + `api.ts:682-687` | 只 q + limit |
| KB-N6 | HOT_TAGS 6 个写死, 非动态 | `KnowledgeBasePage.tsx:21-28` | 改 KB 不会自动同步 |
| KB-N7 | DocDetailView 无 related docs / 同 parent 跳转 | `KnowledgeBasePage.tsx:610-648` | 用户读完一篇无 next |
| KB-N8 | 推荐 3 篇每次随机, 0 编辑配置 | `KnowledgeBasePage.tsx:118-119` | 编辑推啥用户没法干预 |
| KB-N9 | 自写 markdown 渲染, 不解析 frontmatter | `KnowledgeBasePage.tsx:31-50` | metadata 全丢 |
| KB-N10 | 树排序按 path.localeCompare(zh-Hans), "副本" 目录混在训练百科 | `KnowledgeBasePage.tsx:159` | "副本2.5 室内训练（骑行台）（o）__d5baeb8c" 是复制出来的副本, 跟原目录并列展示 |

---

## "同类项分散多个 page" 清单

| # | 同类项 | 散落位置 |
|---|--------|----------|
| S-1 | 训练洞察 | InsightsPage (286 行, /ai/hrv) + TrendsPage (370 行, /training/trends) + DiaryPage (495 行, /training/diary) + ComparePage (336 行, /training/compare) — 4 page 4 路由 4 Sidebar 槽 |
| S-2 | FTP 管理 | Profile.tsx:192-198 「重算 FTP」 + FTPTestPage.tsx (571 行, /data/ftp-test) + ActivityDetail.tsx:279-303 「运行估算」 |
| S-3 | 强度分布 (Z1-Z7) | InsightsPage.tsx:185-213 + PhasesPage.tsx:174-209 (Seiler 80/20) + TrendsPage.tsx 全章 (ZONE_COLORS) + BuilderPage (workout step 编辑时按 Z 显示) — 4 处 |
| S-4 | Race 相关 | PhasesPage.tsx:556 raceType + RaceTacticsPage.tsx + RaceTypePicker.tsx — 3 处; "race" 概念在 Phase/Workout/Race-Tactics 3 个独立类型 |
| S-5 | 训练阶段 | PhasesPage.tsx (管理) + PhaseSignalsCard.tsx (Dashboard 用) + TrainingRadarChart.tsx (PhasesPage 用) + 当前 phase 算 IF/NP 在 CalendarPage / Dashboard 多处 |
| S-6 | 周期化颜色表 | PhasesPage.tsx:38-46 PHASE_COLORS (7 色) + LibraryPage.tsx:33-68 GOAL_COLOR (6 色) — 2 套独立 palette, 同色含义不同 (例如 Phases 的 recovery=slate, Library 的 recovery=sky) |
| S-7 | 训练健康分 | InsightsPage.tsx:90-112 `health_score` + InsightsBanner.tsx (Dashboard 顶部) + HRVCard.tsx (Insights 内嵌) — 3 处取同一 `insightsToday().summary.health_score` 但分别布局 |
| S-8 | Settings 字段 | Profile.tsx 7 字段 0 分组; FTPTestPage 也算 athlete 数据但分散到 /data/ftp-test |
| S-9 | AI 入口 | Sidebar "AI 教练" 组 (3 项) + TopBar GlobalSearch (Cmd+K) + NotificationsBell (跳 /ai/hrv) — 3 入口 |
| S-10 | 课程详情 | LibraryPage WorkoutDetailDrawer (lines 554-742) + LibraryPage WorkoutCard (lines 473-552) — 同一卡片 2 套不同信息密度展示 |

---

## "路由有但入口缺" 清单

| # | 路由 | 路由注册位置 | Sidebar 入口 | 影响 |
|---|------|------------|------------|------|
| R-1 | `/training/compare` | `App.tsx:104-111` | **缺** | 336 行 ComparePage 死代码; 老 `#compare` 重定向到 `/training/activities` (`useLegacyRedirect.ts:33`) |
| R-2 | `/training/activities/:id` | `App.tsx:80-87` | 通过 /training/activities 进入 | OK, 无问题 |
| R-3 | `/plan/calendar` | `App.tsx:156-163` | Sidebar 「日历」`Sidebar.tsx:60` | OK |
| R-4 | `/data/import` | `App.tsx:188-194` | Sidebar 「导入」`Sidebar.tsx:68` | OK, 但 ImportPage 是数据 group 唯一入口, KB/FTP 跟它挤同一组语义不通 |
| R-5 | `/settings` | `App.tsx:215-224` | Sidebar 「个人画像」`Sidebar.tsx:76` | OK, 但 Settings 组只有 1 项, 跟 5 个 4-5 项的 group 不对称, 预示"未来要加更多 settings" |
| R-6 | `/data/knowledge?category=...` | `Sidebar.tsx:167` 触发 | 0 消费方 | 跳完回根目录 |
| R-7 | `/data/knowledge?path=...` | `GlobalSearch.tsx:142` 触发 | 0 消费方 | 跳完回根目录 |
| R-8 | `/ai/chat` 默认入口 | `App.tsx:118` `<Navigate to="/ai/chat" />` | Sidebar 「AI 教练」`Sidebar.tsx:51` | OK, `/ai` index 重定向到 chat |
| R-9 | `/plan` BuilderPage 编辑入口 | `App.tsx:147-155` | Sidebar 「计划」`Sidebar.tsx:59` (但 Label 「计划」, 实际页面是 Builder 编辑课程) | 命名混淆: "计划" 在用户认知 = 训练计划 (Phases/计划生成), 实际是 Builder 编辑课程 |

---

## KB 文档嵌套过深的具体清单

按 `find kb_source/markdown -name "*.md" -printf "%d\n" | awk '{c[$1]++} END{for(d in c)print d,c[d]}' | sort -n`:

| 路径深度 | 文档数 | 占 359 比例 |
|---------|--------|------------|
| 2 (1 级目录 + _content.md) | 8 | 2.2% |
| 3 (1+1) | 59 | 16.4% |
| 4 (1+2) | 56 | 15.6% |
| 5 (1+3) | 142 | 39.6% |
| 6 (1+4) | 77 | 21.4% |
| 7 (1+5) | 11 | 3.1% |
| **8 (1+6)** | **6** | **1.7%** |

**8 层深的最深 6 篇文档 (训练百科/室内训练/Garmin 或 TrainerRoad 下):**
```
1. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.6 TrainerRoad/6.4.7 iGpsport/_content.md
2. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.4Garmin connect/如何将Garmin connect与Trainingpeaks绑定/_content.md
3. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.4Garmin connect/Garmin如何批量导出数据/_content.md
4. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.4Garmin connect/Garmin国内账号转移全球服务器的说明（官方回复，20220419）/_content.md
5. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.3顽鹿竞技/如何在顽鹿运动中绑定TP账户/_content.md
6. 训练百科/2. 训练方法/副本2.5 室内训练（骑行台）（o）/2.5.5如何使用功率骑行台/
   6.4 骑行软件（APP）/6.4.1 通用问题/什么是ERG模式，什么时候开启_关闭ERG模式？/_content.md
```

**7 层深的 11 篇** 主要在 `训练百科/6. 训练工具与装备/专业软件/Trainingpeaks/如何在TP里面写日记/` 下 (TrainingPeaks Me 长文件名副本) 跟 `训练百科/4. 车下训练/力量训练/动作库/拉伸/髂胫束|背部|帼绳肌 拉伸` (3 篇)。

**模式观察** "副本2.5" 前缀 (出现在 E-1 列表第 2 行) 是 V0.x 升级时手工复制目录没合并留下的痕迹, 跟原 `2.5` 并存, 用户看到两个同名目录。