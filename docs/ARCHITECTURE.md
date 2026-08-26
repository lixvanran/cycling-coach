# Cycling Coach 架构演进 — 对标 TrainingPeaks

> 目标:把单用户单机的 MVP,演进为对标 TrainingPeaks(下文简称 TP)的训练管理平台
> 路径:V0.2.0(现状)→ V0.3 PMC → V0.4 计划/课程 → V0.5 多轮 AI → V0.6 多用户协作

---

## 1. 现状盘点(V0.2.0)

### 1.1 已有能力

| 模块 | 实现 | 文件 |
|---|---|---|
| 启动器 | 跨平台 .bat/.sh + Python 包装 | `tools/start.py` |
| FIT 解析 | ✓ 基础流 | `data/parsers/fit_parser.py` |
| 核心指标 | NP/IF/TSS/EF/VI/HR漂移/功率/HR/踏频区间 | `core/metrics/*` |
| 运动员画像 | 单用户,基础字段 | `core/profile/*` |
| 训练负荷 | 单次 TSS + 周累计 | `api/routers/dashboard.py` |
| AI 教练 | M3 SDK 单轮 chat, SSE 流 | `ai/orchestrator.py` + `ai/m3_client.py` |
| 数据模型 | Athlete / Activity / Workout / Preference | `data/sqlite/models.py` |
| 前端 | React 18 + Vite + Tailwind + Recharts + Zustand | `apps/web/src/` |

### 1.2 现有架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (apps/web)                        │
│  React 18 + Vite + Tailwind + Recharts + Zustand             │
│  Pages: Dashboard / ActivityList / ActivityDetail / Import   │
│         / Chat / Profile                                      │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP (127.0.0.1:1420 → 8765)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              Backend (cycling_coach FastAPI)                  │
│  Single uvicorn process · port 8765                           │
│  Routers: activities / athlete / dashboard / coach / dev     │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  data/       │  │  core/       │  │  ai/               │  │
│  │  FIT parse   │→ │  metrics     │→ │  M3 client         │  │
│  │  SQLite ORM  │  │  profile     │  │  orchestrator      │  │
│  │  models      │  │  (单 user)   │  │  prompts/tools     │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
│                                                               │
│  Storage: SQLite (workspace/cycling_coach.db)                 │
│  AI: M3 SDK (mock mode toggle)                                │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
   workspace/input/*.fit    (用户拖入)
   workspace/output/*.md    (AI 报告)
   workspace/.logs/         (启动器/服务日志)
```

### 1.3 离 TP 还差多少

| TP 核心能力 | 现状 | 缺口 |
|---|---|---|
| **PMC (CTL/ATL/TSB)** | ❌ 完全无 | 缺 EWMA 算法 + 每日 metric 表 + 图表 |
| **训练计划 / 日历** | ❌ 模型占位,无业务 | 缺 Period / PlannedWorkout / 日历视图 |
| **Workout Builder** | ❌ | 缺结构化课程(Workout/Block/Step) |
| **Workout Library** | ❌ | 缺搜索/标签/分类 |
| **Power Curve (MMP)** | ⚠️ 后端有 `mean_maximal_power`,前端未接 | 加曲线图 + 区间覆盖 |
| **VO2max 估计** | ❌ | 缺 5min 功率 + HR 模型 |
| **W'bal 实时** | ⚠️ 公式有,无 UI | 加 race-plan 视图 |
| **多轮 AI 工具调用** | ⚠️ 单轮 | 缺 function calling 循环 |
| **结构化课程导入导出** | ❌ | 缺 .zwo / .erg / .mrc 适配器 |
| **多用户 / 教练-运动员** | ❌ 单 user 硬编码 | 需先做 auth + athlete_id 隔离 |
| **iCal 订阅** | ❌ | 后端 ical feed |
| **路线/GPS** | ❌ | FIT 已有 GPS,缺地图组件 |

---

## 2. 目标架构(V0.6 终态)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          Frontend (apps/web)                                │
│  React 18 + Vite + Tailwind + Recharts + Zustand                            │
│                                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ Dashboard    │ │ Calendar     │ │ Workout      │ │ Library          │  │
│  │ PMC + 概览   │ │ 周/月计划    │ │ Builder      │ │ 课程搜索/标签    │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ Activity     │ │ Chat         │ │ Profile      │ │ Route/GPS        │  │
│  │ 详情+分析    │ │ AI 多轮+工具 │ │ 画像+设置    │ │ 地图+海拔        │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘  │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ REST + SSE
                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                                    │
│  /api/activities  /api/athlete   /api/dashboard   /api/pmc                  │
│  /api/workouts    /api/plans     /api/library     /api/coach                │
│  /api/insights    /api/import    /api/export(iCal) /api/ical/{token}       │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬───────────────┬───────────────┐
       ▼               ▼               ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐
│ ingestion    │ │ metrics      │ │ planning     │ │ ai/          │ │ search  │
│ FIT/TCX/CSV  │ │ NP/IF/TSS/   │ │ Period/      │ │ orchestrator │ │ Meilisearch│
│ auto-import  │ │ W'/PMC/      │ │ Workout/     │ │ tools/       │ │ (V0.6)  │
│ watch-dir    │ │ VO2max       │ │ Library      │ │ function call│ │         │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └─────────┘
       │               │               │               │
       └───────────────┴───────────────┴───────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                            │
│  MVP  : SQLite                                                              │
│  V0.6 : Postgres + TimescaleDB(PMC 时序)+ S3(workout 媒体)                  │
│  Files: workspace/{input, output, reports, workouts, plans}                 │
└────────────────────────────────────────────────────────────────────────────┘
```

### 核心模块职责拆分

| 模块 | 职责 | 复用性 |
|---|---|---|
| `ingestion` | 监听 workspace/input,自动解析 FIT/TCX/CSV,落库 | 单实例,常驻 |
| `metrics` | 计算 NP/IF/TSS/W'/PMC/VO2max,生成 daily_metrics | 纯函数,可缓存 |
| `planning` | Workout/PlanPeriod/PlannedWorkout 的 CRUD + 周期排课 | 业务核心 |
| `ai/orchestrator` | tools + memory + function-calling 循环 | 模型无关 |
| `search` | Library / 课程 / 活动全文搜索 | 后期加 |

---

## 3. 演进路线(分四阶段)

### 阶段一:数据基线 + PMC · V0.3(1-2 周)

**目标**:让"训练负荷/状态"这个 TP 最核心的场景立起来。

#### 后端

新增表:
```python
class DailyMetric(Base):
    """每日训练状态(PMC)"""
    __tablename__ = "daily_metrics"
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    date: Mapped[date]  # 当日 00:00 UTC
    tss: Mapped[float] = 0
    ctl: Mapped[float] = 0      # Chronic Training Load (42d EWMA)
    atl: Mapped[float] = 0      # Acute Training Load (7d EWMA)
    tsb: Mapped[float] = 0      # TSB = CTL - ATL
    ramp_rate: Mapped[float] = 0  # 7d CTL 斜率
    sleep_h: Mapped[float | None] = None
    hrv_ms: Mapped[float | None] = None
    rpe: Mapped[int | None] = None  # 1-10
    weight_kg: Mapped[float | None] = None
```

新增服务 `core/pmc.py`:
```python
def compute_pmc(daily_tss: list[float], today: date) -> tuple[float, float, float]:
    """EWMA 算法:CTL(42d)/ATL(7d)/TSB"""
    ctl = sum(t * exp(-(len(daily_tss) - 1 - i) / 42) for i, t in enumerate(daily_tss))
    atl = sum(t * exp(-(len(daily_tss) - 1 - i) / 7)  for i, t in enumerate(daily_tss))
    return ctl, atl, ctl - atl
```

- 触发:每次新 activity 落库 → 后台 thread 增量更新当天 + 未来 7 天 daily_metrics
- 路由:`GET /api/pmc?days=90` 返回时间序列
- 路由:`GET /api/pmc/today` 返回今日 TSB 状态卡

#### 前端

- Dashboard 加 **PMC 双 Y 轴图**(CTL/ATL 折线 + TSB 面积)
- AthleteProfile 加"今日 TSB = +5(状态良好)"状态卡
- AI 聊天上下文自动注入"今日 TSB = +5, 昨日 TSS = 120"

#### 验收

- 导入 5 次活动后,Dashboard 看到 CTL 曲线随 TSS 累计上升
- TSB 准确反映"今天累不累"
- AI 回复能引用 TSB 数字

---

### 阶段二:训练计划 + Workout Builder · V0.4(2-3 周)

**目标**:TP 第二个核心场景 — 课程库 + 排课日历。

#### 后端

```python
class WorkoutBlock(Base):
    """结构化课程(单个)"""
    __tablename__ = "workouts"
    id, athlete_id, name, sport, target_tss, target_duration_s
    blocks: Mapped[list["WorkoutStep"]] = relationship(...)

class WorkoutStep(Base):
    """课程步骤(Interval)"""
    __tablename__ = "workout_steps"
    workout_id, order, kind  # warmup/main/recovery/cooldown
    duration_s, power_pct_ftp, hr_pct_lthr, cadence_rpm
    repeat: int  # 块内循环次数

class PlanPeriod(Base):
    """训练周期(Base/Build/Peak/Taper)"""
    __tablename__ = "plan_periods"
    id, athlete_id, name, start_date, end_date, goal, target_event

class PlannedWorkout(Base):
    """日历上的一次课"""
    __tablename__ = "planned_workouts"
    id, period_id, scheduled_date, workout_id, status  # planned/completed/skipped
    actual_activity_id: int | None  # 关联到真实 activity
```

- 路由:
  - `GET/POST/PUT/DELETE /api/workouts`
  - `GET/POST /api/plans` 周期管理
  - `GET /api/calendar?month=2026-08` 月视图
  - `POST /api/plans/{id}/auto-fill` 用 AI 生成周期草稿
  - `GET /api/ical/{user_token}.ics` iCal 订阅

- 内置 Workout Library:`seed_data/workouts.json`(30-50 经典课程)

#### 前端

- `pages/Calendar.tsx` — 月/周视图,拖拽 PlannedWorkout
- `pages/WorkoutBuilder.tsx` — 区间编辑(react-dnd 或简单的 step list)
- `pages/Library.tsx` — 搜索 + 标签筛选
- `.zwo` / `.erg` 导入(粘文本到对话框)

#### AI 升级

- `ai/tools/build_week_plan` tool — 输入 goal + 现有 TSB,输出 7 天草稿
- 用户说"这周给我排个 Base 期" → AI 调用 tool → 把结果写入 PlanPeriod

#### 验收

- 拖拽课程到日历日期 → 后端写入 PlannedWorkout
- 订阅 iCal → 能在系统日历看到课程
- 真实活动落库后 → 自动关联到对应 PlannedWorkout(按日期+时长匹配)

---

### 阶段三:多轮 AI + 工具调用 · V0.5(1-2 周)

**目标**:AI 从"聊天"升级为"可执行的教练"。

#### ai/orchestrator 升级

```python
# 伪代码
def run_coach_loop(user_msg, history, athlete_ctx):
    tools = [analyze_activity, plan_week, adjust_today, get_pmc]
    msgs = build_messages(history, user_msg, athlete_ctx)
    while True:
        resp = m3.chat(msgs, tools=tools)
        if resp.tool_calls:
            for call in resp.tool_calls:
                result = execute_tool(call, athlete_ctx)
                msgs.append(tool_result(call.id, result))
            continue
        return resp.text
```

#### 新增 tools

| Tool | 输入 | 输出 |
|---|---|---|
| `analyze_activity` | activity_id | 文字分析 |
| `get_pmc` | days | 时间序列 |
| `plan_week` | goal, start_date | 7 天草稿 |
| `adjust_today` | reason | 推荐替代课程 |
| `search_library` | keywords, tag | 课程列表 |

#### 架构改进

- `ai/memory.py` — 长期记忆(用户偏好/历史决策)
- `ai/prompts/` 按角色拆:`coach_personality.md` `analyze_template.md` `plan_template.md`

#### 前端

- ChatPage 支持 tool_call 进度显示(loading card)
- 教练消息可点击"采纳建议"按钮

---

### 阶段四:多用户 + 协作 · V0.6(3-4 周)

**目标**:从"单人单机"升级为 SaaS。

#### 后端拆分

```
backend/
  core/      # 纯计算,无 IO
  api/       # FastAPI,纯转发
  ingestion/ # 独立进程,watch directory
  ai/        # 独立 worker,接队列
  storage/   # DB + 文件
```

引入中间件:
- **Postgres** 替 SQLite(`ts`/`activity` 加索引)
- **TimescaleDB** 存 `daily_metrics` hypertable
- **Redis** 做 cache + task queue
- **Celery / RQ** 处理 AI 长任务
- **Meilisearch** 全文搜索(活动/课程)

#### 多用户

- 加 `users` 表 + JWT auth
- 所有表加 `user_id`,API 强校验
- 移除 `get_or_create_athlete` 单 user 假设

#### 教练-运动员

- `coach_relationships(coach_id, athlete_id, role)`
- 教练可看多个运动员的 PMC 日历
- 课程可分享,带评论流

#### 部署

- Docker Compose:api/ai/worker/db/redis
- 前端 vite build → nginx
- iCal / ical feed 用 read-only token

---

## 4. 模块边界与代码组织

### 4.1 当前 vs 演进

```
V0.2 现状                          V0.3+ 演进
─────────────────────────────────────────────────────────────
cycling_coach/
  api/                              api/  (变薄,只做路由)
    routers/                          routers/
      activities.py                     activities.py
      athlete.py                        athlete.py
      dashboard.py  ←─ 散 ──→          dashboard.py
      coach.py                          pmc.py        ← 新
      diagnose.py                       plans.py      ← 新
      dev.py                            workouts.py   ← 新
                                         library.py    ← 新
                                         insights.py   ← 新
  core/                             core/
    metrics/                          metrics/
    profile/                          profile/
                                      pmc.py          ← 新(PMC 算法)
                                      planning/       ← 新(Period/Workout)
  ai/                               ai/
    orchestrator.py(单轮)             orchestrator.py(多轮+tools) ← 重写
    m3_client.py                      m3_client.py
    prompts/                          prompts/(多角色)
    tools/                            tools/    ← 新
                                       memory.py ← 新
  data/                              data/
    parsers/                          parsers/(加 TCX/CSV)
    sqlite/                           sqlite/(加 daily_metrics/workout_steps/...)
                                       postgres/  ← V0.6
  ingestion/                          ← V0.4 独立进程
```

### 4.2 包依赖原则

- `core/*` 不能 import `ai/*` 或 `api/*`(纯计算)
- `api/*` 可 import 任意,但只做 orchestration
- `ai/*` 只能 import `core/*` 和 `data/*` 模型
- `data/*` 是叶子节点,只 import stdlib + sqlalchemy

---

## 5. 关键技术决策

### 5.1 数据库迁移路径

```
SQLite (V0.2-V0.5)
  ↓
Postgres + TimescaleDB (V0.6)
  ↓
分区策略:
  - activities          按 month 分区
  - daily_metrics       TimescaleDB hypertable
  - workout_steps       按 workout_id 索引
  - ai_messages         按 conversation_id 索引
```

迁移工具:用 **alembic**(已经够用,不要一上来就 Liquibase)

### 5.2 前端状态管理

- Zustand 沿用(比 Redux 轻)
- 按 feature 拆 store:
  - `usePMCStore` (PMC + dashboard)
  - `useCalendarStore` (calendar + plan)
  - `useCoachStore` (chat + history)
- 不用 RTK Query,直接用 `lib/api.ts` 的 fetch wrapper(加 cache 层)

### 5.3 AI 模型

- **M3 SDK**(已接):主用
- 兜底:OpenAI-compatible 接口(已 in `openai>=1.12`)
- 关键:模型与 prompt 解耦,`ai/prompts/` 走 git,不动代码可调 prompt

### 5.4 部署策略

- V0.3-V0.5:仍是单机 app(当前形态)
- V0.6:Docker Compose 上云
- 不急着上 K8s — 阶段不匹配

---

## 6. 不要做的事(Anti-goals)

为防止 scope creep,以下暂不做:

- ❌ 移动 App(先用 PWA)
- ❌ 实时多人协作(Google Docs 式)
- ❌ 视频分析
- ❌ 设备直连(ANT+/BLE)— 走 FIT 文件导入即可
- ❌ 多语言 — 先中文,后期 i18n
- ❌ 完整 Garmin Connect 集成 — 走 .fit 文件兜底

---

## 7. 落地清单(给"现在就能开始"的 7 件事)

按 ROI 排序,先做这 7 件事,马上能拉开与"会读 FIT 的 LLM 工具"的差距:

1. **修启动器** ✅(本文档前段已完成)
2. **PMC 算法 + DailyMetric 表 + /api/pmc** — V0.3 第一刀
3. **PMC 前端图** — Recharts 加双 Y 轴,1 天能写完
4. **WorkoutStep 数据模型** — 不写业务,只把表建好
5. **AI 工具协议** — `ai/tools/base.py` 定义 tool schema,先写 1 个 example
6. **统一的 metrics 服务** — `core/metrics/service.py`,把 dashboard/athlete 里的 SQL 聚合全收敛过来
7. **alembic 引入** — 用 migration 替代当前 `Base.metadata.create_all`,为 V0.6 铺路

---

## 8. 参考资料

- TrainingPeaks PMC 算法:https://www.trainingpeaks.com/learn/articles/setting-up-your-training-peaks-accounts/
- W'bal 论文:Skiba, "A new model to predict W'"(2012)
- Coggan 经典:NP/IF/TSS 定义原文
- pnpm 11 onlyBuiltDependencies:https://pnpm.io/settings#onlybuiltdependencies
- FastAPI + SSE:https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
