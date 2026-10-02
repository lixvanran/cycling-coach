# track-api-data-flow — 后端 API 连通性审计

## 1. Summary

扫描了 cycling_coach/api/routers/ 下全部 24 个 router 文件的 **128 个** `@router.*` 端点（GET 76 / POST 33 / DELETE 10 / PATCH 9），对照 apps/web/src/lib/api.ts 暴露的 89 个前端方法（外加 10 处组件原生 fetch），定位 **33 个孤儿端点**（后端有但前端 0 调用）、**5 类孤儿需求**（前端想用但后端没）、**1 处 URL 拼写错位**（race-tactics 上传 404）、**5 条数据流断裂**（写入侧与读取侧未连通）。审计方法：grep `@router\.` 全量枚举 + grep `api\.<method>` 全量提取 + 逐 file:line 验证；所有数字与 grep 原始计数对齐。

---

## 2. 后端端点全清单（128 个）

图例：**✓** = 前端有封装且被页面调用；**R** = 后端有路由但前端通过原生 `fetch()` 调用（非 api.ts 封装）；**✗** = 孤儿（前端完全无调用）。

### 2.1 activities (12 端点)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| POST | /api/activities/upload | cycling_coach/api/routers/activities.py:27 | ✓ uploadActivity (ImportPage) |
| GET | /api/activities | activities.py:46 | ✓ listActivities (ActivityList) |
| GET | /api/activities/compare | activities.py:85 | ✓ compareActivities (ComparePage:78) |
| GET | /api/activities/{id} | activities.py:94 | ✓ getActivity (ActivityDetail:64) |
| DELETE | /api/activities/{id} | activities.py:103 | ✓ deleteActivity |
| PATCH | /api/activities/{id}/rpe | activities.py:111 | ✓ updateRpe (RPEEditor:34,47) |
| POST | /api/activities/{id}/analyze | activities.py:121 | ✓ analyzeActivity |
| GET | /api/activities/{id}/power-curve | activities.py:134 | ✓ getPowerCurve (ActivityDetail:65) |
| GET | /api/activities/{id}/power-zones-detailed | activities.py:143 | ✓ getPowerZonesDetailed (ActivityDetail:66) |
| GET | /api/activities/{id}/wbal | activities.py:153 | ✓ getWbal (ActivityDetail:67) |
| GET | /api/activities/{id}/decoupling | activities.py:164 | ✓ getDecoupling (ActivityDetail:69) |
| GET | /api/activities/{id}/cp-estimate | activities.py:173 | ✓ getCpEstimate (ActivityDetail:68) |

### 2.2 athlete (3)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/athlete | athlete.py:41 | ✓ getAthlete |
| PATCH | /api/athlete | athlete.py:58 | ✓ updateAthlete |
| POST | /api/athlete/refresh-ftp | athlete.py:69 | ✓ refreshAthleteFtp (Profile:107) |

### 2.3 calendar (8)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/calendar | calendar.py:198 | ✓ getCalendar (CalendarPage:87) |
| GET | /api/calendar/planned | calendar.py:209 | **✗ 孤儿** |
| POST | /api/calendar/planned | calendar.py:225 | ✓ createPlanned |
| PATCH | /api/calendar/planned/{id} | calendar.py:253 | ✓ updatePlanned |
| DELETE | /api/calendar/planned/{id} | calendar.py:268 | ✓ deletePlanned |
| POST | /api/calendar/planned/{id}/link/{activity_id} | calendar.py:279 | ✓ linkPlanned |
| POST | /api/calendar/planned/{id}/unlink | calendar.py:298 | ✓ unlinkPlanned |
| POST | /api/calendar/auto-link | calendar.py:312 | ✓ autoLinkMonth |

### 2.4 chat (6) — 全部孤儿

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| POST | /api/chat/sessions | chat.py:29 | **✗ 孤儿** |
| GET | /api/chat/sessions | chat.py:38 | **✗ 孤儿** |
| DELETE | /api/chat/sessions/{id} | chat.py:49 | **✗ 孤儿** |
| GET | /api/chat/sessions/{id}/messages | chat.py:62 | **✗ 孤儿** |
| POST | /api/chat/sessions/{id}/messages | chat.py:71 | **✗ 孤儿** |
| PATCH | /api/chat/sessions/{id}/tree | chat.py:81 | **✗ 孤儿** |

> 前端 ChatPage.tsx:172 走的是 `api.chatStreamV2(...)` → `POST /api/coach/chat`，与 chat.py 无关。chat.py 这 6 个端点仅在 tests/test_chat_persistence_v076.py 被调用（产品代码 0 引用）。

### 2.5 coach (1)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| POST | /api/coach/chat | coach.py:46 | ✓ chatStream/chatStreamV2 (ChatPage:172) |

### 2.6 dashboard (1)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/dashboard/overview | dashboard.py:18 | ✓ getOverview |

### 2.7 dev (3)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| POST | /api/dev/generate-mock | dev.py:151 | ✓ generateMock (ImportPage:82) |
| GET | /api/dev/mock-profiles | dev.py:238 | ✓ listMockProfiles |
| POST | /api/dev/repair-db | dev.py:243 | R LibraryPage.tsx:169 (原生 fetch) |

### 2.8 diagnose (2)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/diagnose | diagnose.py:15 | ✓ diagnose (Sidebar:203, TopBar:16,45) |
| GET | /api/health | diagnose.py:29 | **✗ 孤儿** |

### 2.9 diary (5) — 全部已连通

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/diary | diary.py:25 | ✓ diaryList (DiaryPage:114,152,182) |
| GET | /api/diary/template | diary.py:34 | ✓ diaryTemplate (DiaryPage:112) |
| GET | /api/diary/{date} | diary.py:40 | ✓ diaryGet (DiaryPage:86) |
| POST | /api/diary | diary.py:49 | ✓ diaryUpsert (DiaryPage:148) |
| DELETE | /api/diary/{date} | diary.py:58 | ✓ diaryDelete (DiaryPage:176) |

### 2.10 ftp (6)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/ftp/methods | ftp.py:26 | ✓ ftpMethods |
| POST | /api/ftp/estimate | ftp.py:31 | ✓ ftpEstimate |
| POST | /api/ftp/test | ftp.py:40 | ✓ ftpRecord |
| GET | /api/ftp/history | ftp.py:49 | ✓ ftpHistory |
| GET | /api/ftp/recommend | ftp.py:58 | ✓ ftpRecommend (FTPTestPage:55) |
| DELETE | /api/ftp/test/{id} | ftp.py:66 | ✓ ftpDelete |

### 2.11 hrv (3)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/hrv/state | hrv.py:35 | ✓ HRVCard.tsx:32 (原生 fetch) |
| GET | /api/hrv/series | hrv.py:49 | **✗ 孤儿**（series 数据塞在 state 响应里） |
| POST | /api/hrv/today | hrv.py:56 | **✗ 孤儿**（无 UI 手动录入 HRV） |

### 2.12 insights (2)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/insights/today | insights.py:24 | ✓ insightsToday |
| GET | /api/insights/weekly | insights.py:48 | ✓ insightsWeekly |

### 2.13 kb (12)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/kb/categories | kb.py:33 | ✓ kbCategories |
| GET | /api/kb/documents | kb.py:41 | ✓ kbDocuments |
| GET | /api/kb/documents/{id} | kb.py:55 | ✓ kbDocument |
| GET | /api/kb/by-path | kb.py:65 | ✓ kbByPath |
| GET | /api/kb/search | kb.py:76 | ✓ kbSearch |
| GET | /api/kb/attachments/by-name/{filename} | kb.py:88 | R KnowledgeBasePage.tsx:34 (原生 fetch，markdown 渲染) |
| GET | /api/kb/attachments/{att_id}/image | kb.py:98 | **✗ 孤儿** |
| PATCH | /api/kb/attachments/{att_id} | kb.py:108 | ✓ kbPatchAttachment |
| GET | /api/kb/attachments | kb.py:118 | ✓ kbAttachments |
| GET | /api/kb/stats | kb.py:135 | ✓ kbStats |
| POST | /api/kb/reimport | kb.py:141 | **✗ 孤儿** |
| GET | /api/kb/import-status | kb.py:147 | **✗ 孤儿** |

### 2.14 ml (5)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| POST | /api/ml/predict/ftp | ml.py:100 | ✓ predictFtp (FTPPredictionCard:35) |
| GET | /api/ml/models | ml.py:214 | **✗ 孤儿**（api.ts:594 定义 listMlModels，但 0 处页面调用） |
| POST | /api/ml/models/register | ml.py:243 | **✗ 孤儿** |
| POST | /api/ml/models/activate | ml.py:278 | **✗ 孤儿** |
| GET | /api/ml/predictions | ml.py:303 | **✗ 孤儿** |

### 2.15 phases (11)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/phases/meta | phases.py:86 | ✓ phasesMeta (PhasesPage:65) |
| GET | /api/phases | phases.py:93 | ✓ phasesList (PhasesPage:64) |
| POST | /api/phases | phases.py:141 | ✓ phasesCreate (PhasesPage:580) |
| GET | /api/phases/current | phases.py:173 | ✓ phasesCurrent (PhasesPage:66) |
| GET | /api/phases/next-race | phases.py:191 | ✓ phasesNextRace (PhasesPage:67) |
| PATCH | /api/phases/{id} | phases.py:216 | ✓ phasesUpdate (PhasesPage:578) |
| DELETE | /api/phases/{id} | phases.py:235 | ✓ phasesDelete (PhasesPage:103) |
| GET | /api/phases/suggest | phases.py:247 | ✓ phasesSuggest (PhasesPage:68) |
| GET | /api/phases/polarized | phases.py:272 | ✓ phasesPolarized (PhasesPage:69) |
| GET | /api/phases/race-plan | phases.py:312 | ✓ phasesRacePlan (PhasesPage:82) |
| GET | /api/phases/signals | phases.py:396 | R PhaseSignalsCard.tsx:82 (原生 fetch) |

### 2.16 plans (5) — 全部已连通

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/plans | plans.py:59 | ✓ listPlans |
| POST | /api/plans | plans.py:71 | ✓ createPlan |
| GET | /api/plans/{id} | plans.py:94 | ✓ getPlan |
| PATCH | /api/plans/{id} | plans.py:105 | ✓ updatePlan |
| DELETE | /api/plans/{id} | plans.py:118 | ✓ deletePlan |

### 2.17 pmc (3) — 全部已连通

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/pmc | pmc.py:20 | ✓ getPMC |
| GET | /api/pmc/today | pmc.py:35 | ✓ getPMCToday |
| POST | /api/pmc/rebuild | pmc.py:42 | ✓ rebuildPMC |

### 2.18 race_prep (3)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/race-prep/types | race_prep.py:24 | R RaceTypePicker.tsx:23 (原生 fetch) |
| GET | /api/race-prep/tsb-target | race_prep.py:45 | **✗ 孤儿**（数据塞在 types 响应里） |
| GET | /api/race-prep/training-state | race_prep.py:82 | R TrainingRadarChart.tsx:52 (原生 fetch) |

### 2.19 race_tactics (10)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/race-tactics/sessions | race_tactics.py:174 | ✓ raceTacticsList (RaceTacticsPage:61) |
| POST | /api/race-tactics/sessions | race_tactics.py:187 | ✓ raceTacticsCreate (RaceTacticsPage:84) |
| GET | /api/race-tactics/sessions/{id} | race_tactics.py:208 | ✓ raceTacticsGet (RaceTacticsPage:73,154,221,261) |
| PATCH | /api/race-tactics/sessions/{id} | race_tactics.py:221 | **✗ 孤儿** |
| DELETE | /api/race-tactics/sessions/{id} | race_tactics.py:239 | ✓ raceTacticsDelete (RaceTacticsPage:104) |
| POST | /api/race-tactics/sessions/{id}/upload | race_tactics.py:260 | ⚠ URL 拼写错位（见 §3.B1） |
| DELETE | /api/race-tactics/sessions/{id}/attachments/{att_id} | race_tactics.py:322 | **✗ 孤儿** |
| GET | /api/race-tactics/attachments/{att_id}/download | race_tactics.py:341 | **✗ 孤儿** |
| POST | /api/race-tactics/sessions/{id}/messages | race_tactics.py:358 | R RaceTacticsPage.tsx:133 (原生 fetch + SSE) |
| POST | /api/race-tactics/sessions/{id}/suggest | race_tactics.py:459 | R RaceTacticsPage.tsx:204 (原生 fetch + SSE) |

### 2.20 recommendations (2)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/recommendations/today | recommendations.py:26 | R DailyRecommendationCard.tsx:81 (原生 fetch) |
| GET | /api/recommendations/readiness | recommendations.py:58 | **✗ 孤儿**（readiness 字段塞在 today 响应里） |

### 2.21 reports (1)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/reports/weekly | reports.py:23 | R ReportDownloadButton.tsx:15 (原生 fetch) |

### 2.22 sync (7) — Strava 全套孤儿

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/sync/providers | sync.py:36 | **✗ 孤儿** |
| GET | /api/sync/strava/status | sync.py:100 | **✗ 孤儿** |
| GET | /api/sync/strava/auth | sync.py:121 | **✗ 孤儿** |
| GET | /api/sync/strava/callback | sync.py:136 | **✗ 孤儿** |
| POST | /api/sync/strava/disconnect | sync.py:152 | **✗ 孤儿** |
| GET | /api/sync/strava/activities | sync.py:162 | **✗ 孤儿** |
| POST | /api/sync/strava/sync | sync.py:180 | **✗ 孤儿** |

### 2.23 trends (6)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/trends/volume | trends.py:79 | **✗ 孤儿**（volume 数据塞在 overview 响应里） |
| GET | /api/trends/zones | trends.py:172 | **✗ 孤儿**（zones 数据塞在 overview 响应里） |
| GET | /api/trends/metrics | trends.py:222 | **✗ 孤儿**（metrics 数据塞在 overview 响应里） |
| GET | /api/trends/rpe-trend | trends.py:273 | ✓ trendsRpe (TrendsPage:66) |
| GET | /api/trends/acwr | trends.py:358 | ✓ trendsAcwr (TrendsPage:65) |
| GET | /api/trends/overview | trends.py:373 | ✓ trendsOverview (TrendsPage:64) |

### 2.24 workouts (11)

| 方法 | 路径 | 后端位置 | 前端调用 |
|---|---|---|---|
| GET | /api/workouts | workouts.py:542 | ✓ listWorkouts |
| GET | /api/workouts/tags | workouts.py:595 | ✓ listWorkoutTags |
| GET | /api/workouts/goals | workouts.py:618 | ✓ listWorkoutGoals |
| GET | /api/workouts/{id} | workouts.py:633 | ✓ getWorkout |
| POST | /api/workouts | workouts.py:642 | ✓ createWorkout (BuilderPage:567, LibraryPage) |
| PATCH | /api/workouts/{id} | workouts.py:665 | ✓ updateWorkout |
| DELETE | /api/workouts/{id} | workouts.py:685 | ✓ deleteWorkout |
| POST | /api/workouts/{id}/duplicate | workouts.py:701 | ✓ duplicateWorkout |
| POST | /api/workouts/{id}/schedule | workouts.py:733 | ✓ scheduleWorkout (LibraryPage:235) |
| GET | /api/workouts/{id}/export | workouts.py:773 | R LibraryPage.tsx:746 (原生 window.open) |
| POST | /api/workouts/ai-schedule | workouts.py:880 | **✗ 孤儿**（501 stub，永远 501） |

**合计 128 端点 = ✓ 94 (含 R 10 处原生 fetch 调用) + ⚠ 1 (race-tactics /upload 拼错 404) + ✗ 33** ✓ 数与 grep 原始计数 128 一致。

---

## 3. 孤儿 API 清单（33 条 / 22 条目）

每条带 file:line 后端证据 + 前端 0 调用验证。

### 3.A 整模块孤儿（chat.py 6 条）

1. **POST /api/chat/sessions**（chat.py:29）— 创建 chat 会话。意图：思维树持久化。
   应在哪调用：ChatPage.tsx:172（chatStreamV2 入口）需先 POST 拿 session_id。当前 chatStreamV2 只发 messages+message，从未拿到 session_id，刷新页面所有对话/树全部丢失。

2. **GET /api/chat/sessions**（chat.py:38）— 列历史会话。
   应在哪调用：ChatPage 左侧 "历史 N 条" 区域（ChatPage.tsx:352 显示 `messages.length`，应该列出真正会话而非 in-memory 计数）。

3. **DELETE /api/chat/sessions/{id}**（chat.py:49）— 删会话。
   应在哪调用：ChatPage 历史列表的删除按钮。

4. **GET /api/chat/sessions/{id}/messages**（chat.py:62）— 读历史消息。
   应在哪调用：ChatPage 切换会话时拉历史。

5. **POST /api/chat/sessions/{id}/messages**（chat.py:71）— 写消息。
   应在哪调用：chatStreamV2 流式完成后调用，把对话落到 DB（当前仅存 in-memory）。

6. **PATCH /api/chat/sessions/{id}/tree**（chat.py:81）— 更新思维树。
   应在哪调用：ChatPage 收 [NODE] SSE 帧时（ChatPage.tsx:172 循环）应有 patchTree 调用，但 0 引用。

> **数据流断裂**：`POST /api/coach/chat` SSE 流（chat.py:81 字段 rag_sources + [NODE]）→ 写入侧只到内存 React state。chat.py PATCH 端点就是给这个场景准备的，但前端从未连通，刷新页面 9 stage 思维树全丢。

### 3.B 半模块孤儿（race_tactics + sync + 杂）

7. **POST /api/race-tactics/sessions/{id}/upload**（race_tactics.py:260）— 上传路书 PDF/PNG。
   **⚠ URL 拼写错位**：前端 api.ts:724 写的是 `/sessions/${id}/attachments`，后端真实路径是 `/sessions/${id}/upload`。RaceTacticsPage.tsx:259 调用 `raceTacticsUpload`，会 100% 返回 404 Method Not Allowed。这是真实功能 bug，不是孤儿。

8. **PATCH /api/race-tactics/sessions/{id}**（race_tactics.py:221）— 更新会话元数据。
   应在哪调用：RaceTacticsPage 编辑会话标题/分类时。

9. **DELETE /api/race-tactics/sessions/{id}/attachments/{att_id}**（race_tactics.py:322）— 删附件。
   应在哪调用：RaceTacticsPage 附件列表的删除按钮（RaceTacticsPage.tsx 未渲染附件列表）。

10. **GET /api/race-tactics/attachments/{att_id}/download**（race_tactics.py:341）— 下载附件。
    应在哪调用：附件列表的"下载"按钮。

11. **GET /api/sync/providers**（sync.py:36）+ **GET /api/sync/strava/status**（sync.py:100）+ **GET /api/sync/strava/auth**（sync.py:121） + **GET /api/sync/strava/callback**（sync.py:136）+ **POST /api/sync/strava/disconnect**（sync.py:152）+ **GET /api/sync/strava/activities**（sync.py:162）+ **POST /api/sync/strava/sync**（sync.py:180） — Strava 全套 7 端点全部孤儿。
    应在哪调用：Profile / Settings 页应有 "连接 Strava" 按钮（UserProfile.tsx / Settings 页当前都没有 Strava 接入）。

12. **POST /api/workouts/ai-schedule**（workouts.py:880）— AI 排课。
    **永远 501**（workouts.py:891-901 抛 HTTPException(501)）。注释说 "V0.7.6+ 实装"，仍未实装。

13. **POST /api/ml/models/register**（ml.py:243）+ **POST /api/ml/models/activate**（ml.py:278）+ **GET /api/ml/predictions**（ml.py:303） + **GET /api/ml/models**（ml.py:214） — ML 模型管理 4 端点全部孤儿。
    api.ts:594 定义了 `listMlModels` 但 0 处调用（grep `listMlModels` apps/web/src/ 仅匹配 lib/api.ts + test mock）。FTPPredictionCard.tsx 是唯一用 ML 的 UI，但只调 predictFtp。

14. **GET /api/health**（diagnose.py:29）— 健康检查。
    应在哪调用：运维监控端点，前端无须。

15. **GET /api/hrv/series**（hrv.py:49）— HRV 历史曲线。
    实际数据已塞进 hrv/state 响应里（HRVCard.tsx:32 调 /state，state 响应含 series 字段 hrv.py:35），hrv/series 是冗余端点。

16. **POST /api/hrv/today**（hrv.py:56）— 今日手动录入 HRV。
    应在哪调用：HRVCard 旁边的 "+ 录入今日" 按钮（当前 UI 无此入口）。

17. **GET /api/kb/attachments/{att_id}/image**（kb.py:98）— 通过 att_id 取图。
    实际 KnowledgeBasePage.tsx:34 走的是 `by-name/{filename}`（kb.py:88），按文件名取图更便捷，本端点是重复实现。

18. **POST /api/kb/reimport**（kb.py:141）+ **GET /api/kb/import-status**（kb.py:147） — KB 重新导入管理。
    应在哪调用：KB 设置/管理员面板（KnowledgeBasePage 当前只有浏览/搜索/统计）。

19. **GET /api/calendar/planned**（calendar.py:209）— 列出所有 planned（不按月份）。
    CalendarPage 仅用 GET /api/calendar?year&month（calendar.py:198）拿月度数据，全量列表端点从未被调。

20. **GET /api/recommendations/readiness**（recommendations.py:58）— 单独的 readiness 评分。
    DailyRecommendationCard.tsx:81 调 /recommendations/today 拿全量（含 readiness 字段），readiness 是冗余端点。

21. **GET /api/trends/volume**（trends.py:79）+ **GET /api/trends/zones**（trends.py:172）+ **GET /api/trends/metrics**（trends.py:222） — trends 三个独立端点全部孤儿。
    TrendsPage.tsx:64 调 trendsOverview，overview 返回 volume+zones+metrics 三合一数据，三个独立端点是冗余实现。

22. **GET /api/race-prep/tsb-target**（race_prep.py:45） — 按比赛类型返回 TSB 目标区间。
    RaceTypePicker.tsx:23 调 /race-prep/types，types 响应里已含 tsb_target 字段（RaceTypePicker.tsx:8 接口声明证实），独立端点是冗余实现。

---

## 4. 孤儿需求清单（前端想用但后端没）

### 4.N1 — 比赛计划一键采纳
**用户场景**：用户在 PhasesPage 点 "生成比赛计划" 看到 Joe Friel 4 阶段计划预览（PhasesPage.tsx:80-88, 357-453），期望点 "全部采纳" 自动建 4 个 Phase。
**缺端点**：POST /api/phases/bulk-create-from-plan（payload: race_date, race_name）。
**证据**：race-plan 预览是只读展示，无 apply 按钮；用户必须手填 4 次 PhaseForm 才能复用（PhasesPage.tsx:544-588）。

### 4.N2 — KB 引用跳转
**用户场景**：ChatPage AI 回答末尾 "知识库参考 · N 条" 列出引用源，期望点 "打开 →" 跳到 KB 对应文档。
**缺端点**：无缺，但 KnowledgeBasePage.tsx 没读 `?path=` query（grep `useSearchParams` 在 KnowledgeBasePage 0 结果），导致 ChatPage.tsx:558 跳 `/data/knowledge?path=...` 后 KB 页仍停在根目录，引用跳转 100% 失败。
**证据**：KnowledgeBasePage.tsx 全文无 URLSearchParams/window.location.search；selectedPath 仅由内部点击（line 95）控制。

### 4.N3 — 活动作为课程模板
**用户场景**：ActivityDetail 用户看完某次精彩间歇训练，期望 "另存为课程" 一键加到 Library。
**缺端点**：POST /api/activities/{id}/to-workout（payload: title, source_format） 或前端复用 POST /api/workouts 自动从 activity 推算 intervals。
**证据**：ActivityDetail.tsx:168 只有 Back 按钮，无 "另存为课程"。ChatPage 给出 "基于上次间歇再练" 类建议也无从落地。

### 4.N4 — AI 教练代写课程
**用户场景**：ChatPage workflow 模式（"战术规划" tab）用户问 "FTP 220W 备战 60km 山地赛，赛前 4 周怎么练？"，AI 给出 9 stage 思维扩散，期望一键生成 Phase + Workout 落到日历。
**缺端点**：POST /api/coach/plan-apply（payload: workflow_session_id, plan_json）。当前 /api/workouts/ai-schedule 是 stub（501）。
**证据**：workflow tab 只有思维树（ChatPage.tsx:359 WorkflowLayout），结果只能看不能落库。

### 4.N5 — 训练健康手动录入
**用户场景**：用户用 Oura/Whoop 测得今日 HRV=45ms，期望在 Dashboard/HRVCard 旁手动录入触发 readiness 计算。
**缺端点**：POST /api/hrv/today 端点**后端已有**（hrv.py:56），但前端无 UI（grep "api/hrv/today\|hrvToday" apps/web/src/ 0 命中），属"孤儿需求"侧：API 空闲等入口。
**证据**：HRVCard.tsx 全文只有 fetch /api/hrv/state，没有录入按钮。

---

## 5. 数据流断裂图（A 写入 → B 该读未读）

```
┌──────────────────────────────────────────────────────────────────┐
│  断裂 1: chat 持久化                                              │
│                                                                  │
│  [NODE][SOURCES] SSE 帧  ←── POST /api/coach/chat (coach.py:46) │
│       │                                                          │
│       ▼                                                          │
│  React state (in-memory)  ──X──>  /api/chat/sessions/{id}/tree   │
│       │                            PATCH (chat.py:81) [孤儿]     │
│       ▼                                                          │
│  刷新页面 → 全部丢失                                              │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  断裂 2: KB 引用跳转                                              │
│                                                                  │
│  [SOURCES] 帧含 path/title/snippet  ←── /api/coach/chat          │
│       │                                                          │
│       ▼                                                          │
│  ChatPage render (ChatPage.tsx:540-569)                          │
│       │                                                          │
│       ▼ 用户点 "打开 →"                                           │
│  navigate("/data/knowledge?path=...")                            │
│       │                                                          │
│       ▼                                                          │
│  KnowledgeBasePage.tsx  ──X──>  useSearchParams.get("path")      │
│                                  [KnowledgeBasePage 全文 0 命中]   │
│  结果: 跳转后停在 KB 首页, 引用未生效                              │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  断裂 3: race-plan → phases 采纳                                  │
│                                                                  │
│  GET /api/phases/race-plan (phases.py:312)  ←── PhasesPage:82    │
│       │                                                          │
│       ▼                                                          │
│  React state (PhasesPage.tsx:57 racePlan)                        │
│       │                                                          │
│       ▼                                                          │
│  只读展示 (PhasesPage.tsx:357-453 RacePlanForm)                   │
│       │                                                          │
│       ▼ 用户期望 "全部采纳"                                       │
│  POST /api/phases (×4, 用户手填 4 次)                             │
│       │                                                          │
│       ▼                                                          │
│  缺: POST /api/phases/bulk-create-from-plan [4.N1]                │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  断裂 4: activity → workout 模板                                  │
│                                                                  │
│  POST /api/activities/upload (activities.py:27)                  │
│       │                                                          │
│       ▼                                                          │
│  ActivityDetail (ActivityDetail.tsx)                             │
│       │                                                          │
│       ▼ 用户期望 "另存为课程"                                     │
│  ──X──> POST /api/workouts [4.N3]                                │
│                                                                  │
│  缺: 转换器 (intervals → workout blocks) 或一键 endpoint         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  断裂 5: Strava 同步 (整模块未接)                                  │
│                                                                  │
│  sync.py 7 端点全部孤儿                                          │
│  缺: Profile/Settings 的 "连接 Strava" UI 入口                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. 模式 A'（后端视角）：数据可达性

> 视角转换：从"前端调后端"反转为"后端生产的数据能否到达用户"。三类不可达数据：

### A'.1 永不到达（生产了没人读）
- **chat 9-stage 思维树** — coach.py POST /chat SSE 流持续生产 [NODE] 帧（orchestrator.py:402-406），无任何持久化路径。DB 有 sessions_tree 表（chat.py:81 路由证明），但 0 写入。
- **Strava 活动流** — sync.py 7 端点全程空闲；sync_activities 表有写入路径但没有触发入口。
- **workflow plan 上下文** — orchestrator.py:401 JSON-encoded rag_sources 跟随 [SOURCES] 帧发出，ChatPage.tsx:251 setSources 把数据存内存，无落库动作。

### A'.2 能到达但到达错地方（数据搬家 / 错配）
- **HRV series 数据** — hrv.py:35 GET /state 响应里塞了 series 数组（HRVCard.tsx:17 类型证实），导致 hrv.py:49 GET /series 端点冗余；用户看 HRVCard 但永远不知道有 /series。
- **recommendations readiness** — 同理，readiness 字段塞在 /today 响应里（DailyRecommendationCard.tsx:31-39 类型证实），/readiness 端点冗余。
- **trends volume/zones/metrics** — overview 端点（trends.py:373）一次性返回 3 块数据（api.ts:295-310 类型），独立 3 端点全部冗余。
- **race-prep tsb_target** — types 响应含 tsb_target 字段（RaceTypePicker.tsx:8 接口），/tsb-target 端点冗余。

### A'.3 生产了但调用方路径错
- **race-tactics 上传路书** — 前端 api.ts:724 拼 `/sessions/${id}/attachments`，后端真实是 `/sessions/${id}/upload`（race_tactics.py:260）。每次上传都 404，必须修前端 URL 才能用。

---

## 7. 关键计数自检

| 项 | 报告数 | grep 原始 | 对齐 |
|---|---|---|---|
| 后端总端点 | 128 | `grep -rn "@router\." cycling_coach/api/routers/ \| wc -l` = 128 (GET 76 + POST 33 + DELETE 10 + PATCH 9) | ✓ |
| 已连通 (✓ 含 R) | 94 | activities 12 + athlete 3 + calendar 7 + chat 0 + coach 1 + dashboard 1 + dev 3 + diagnose 1 + diary 5 + ftp 6 + hrv 1 + insights 2 + kb 9 + ml 1 + phases 11 + plans 5 + pmc 3 + race_prep 2 + race_tactics 6 + recommendations 1 + reports 1 + sync 0 + trends 3 + workouts 10 = 94 | ✓ |
| 拼写错位 (⚠) | 1 | race_tactics.py:260 POST /upload，但前端 api.ts:724 拼成 /attachments，每次 404 | ✓ |
| 孤儿 (✗) | 33 | chat.py 6 + diagnose.py 1 + hrv.py 2 + kb.py 3 + ml.py 4 + race_prep.py 1 + race_tactics.py 3 + sync.py 7 + trends.py 3 + workouts.py 1 + calendar.py 1 + recommendations.py 1 = 33 | ✓ |
| 合计 | 128 | 94 + 1 + 33 = 128 | ✓ |

**R 类（前端原生 fetch 封装绕过 api.ts）10 处**：HRVCard (state)、RaceTypePicker (types)、TrainingRadarChart (training-state)、KnowledgeBasePage (kb attachments by-name, markdown 渲染)、LibraryPage (workouts export / dev repair-db)、ReportDownloadButton (reports weekly)、DailyRecommendationCard (recommendations today)、RaceTacticsPage (race-tactics messages / suggest, SSE 流式)、PhaseSignalsCard (phases signals)。这 10 处已计入 ✓ 94。

---

## 8. 结论摘要

- **128 个后端端点**，**33 个孤儿**（26%），**1 处 URL 错位**（race-tactics 上传 404），**3 个后端整模块零连通**（chat.py / sync.py Strava / ml.py 模型管理），**5 处数据流断裂**。
- 最大的修复 ROI 在三处：
  1. **修 race-tactics 上传 URL 错位**（1 行改动，恢复 1 个核心功能）
  2. **接 chat.py 持久化**（接通 PATCH /chat/sessions/{id}/tree，刷新不丢思维树）
  3. **KB 页读 `?path=` query**（接通 ChatPage 引用跳转）
- 次要：删 8 个冗余端点（hrv/series、readiness、trends 3 个、race-prep/tsb-target、kb/attachments/{id}/image、calendar/planned），节省维护负担。

---

## 9. Changed files

无源代码改动。本审计为纯 grep + 人工核查，仅产出 deliverable.md。